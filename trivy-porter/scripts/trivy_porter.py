#!/usr/bin/env python3
"""Local Trivy menus and durable, manual handoff to the editor's AI chat."""

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import uuid

import report_transfer
import session_store as store


CAPTURE_LIMIT = 4 * 1024 * 1024
UPLOAD_PROMPT = (
    "$trivy-porter Analisis laporan JSON terlampir, jelaskan temuannya dan rekomendasi perbaikannya.\n"
    "\n"
    "Perbaiki terlebih dahulu dengan jumlah temuan: n"
)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
FLAG_LINE = re.compile(r"^\s+(?:-\w,\s+)?--([\w-]+)(?:\s+(\w+))?\s{2,}(.*)$")
VALUE_TYPES = {"string", "strings", "stringArray", "int", "ints", "uint", "float", "float64", "duration"}
NO_SCAN_FLAGS = {"help", "version", "download-db-only", "download-java-db-only", "generate-default-config", "reset", "clear-cache"}
CREDENTIAL_FLAGS = {"password", "password-stdin", "registry-token", "token", "custom-headers", "username"}
COVERAGE_ENV = {"TRIVY_SEVERITY", "TRIVY_SCANNERS", "TRIVY_PKG_TYPES", "TRIVY_IGNORE_UNFIXED",
                "TRIVY_SKIP_DIRS", "TRIVY_SKIP_FILES", "TRIVY_IGNORE_STATUS", "TRIVY_TABLE_MODE",
                "TRIVY_FORMAT", "TRIVY_OUTPUT", "TRIVY_CONFIG", "TRIVY_IGNOREFILE"}
SENSITIVE_NAME = re.compile(r"password|token|secret|credential|authorization|api[_-]?key|private[_-]?key", re.I)
SECRET_ASSIGNMENT = re.compile(
    r'''(?i)(password|token|secret|authorization|api[_-]?key|private[_-]?key)\s*[=:]\s*(?:"(?:[^"\\]|\\.)*(?:"|$)|'(?:[^'\\]|\\.)*(?:'|$)|\S+)'''
)


class Cancelled(Exception):
    pass


class CliError(Exception):
    pass


def ask(message):
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise Cancelled() from exc


def choice(message, options, default="1"):
    print("\n" + message)
    for key, label in options:
        print(f"{key}. {label}")
    while True:
        value = ask(f"Pilihan [{default}]: ") or default
        if value == "default":
            value = default
        if value == "0":
            raise Cancelled()
        if value in dict(options):
            return value
        print("Pilihan tidak valid. Masukkan nomor yang ditampilkan (0 = batal).")


def literal(value):
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CliError("Nilai tidak boleh memuat karakter kontrol.")
    if re.search(r"://[^/\s]*@", value) or SECRET_ASSIGNMENT.search(value):
        raise CliError("Jangan masukkan kredensial ke argumen/sesi; gunakan autentikasi terkonfigurasi atau environment.")
    return value


def strip_terminal_controls(text):
    text = re.sub(r"\x1b\].*?(?:\x07|\x1b\\|$)", "", text, flags=re.S)
    text = re.sub(r"\x1b[P^_].*?(?:\x1b\\|$)", "", text, flags=re.S)
    text = ANSI.sub("", text)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)


def scrub(text):
    text = strip_terminal_controls(text)
    for key, value in os.environ.items():
        if key.startswith("TRIVY_") and SENSITIVE_NAME.search(key) and len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(https?://|redis://)[^/\s@]+@", r"\1[REDACTED]@", text)
    return SECRET_ASSIGNMENT.sub(lambda match: match.group(1) + "=[REDACTED]", text)


def probe(argv, cwd):
    try:
        result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CliError(f"Tidak dapat menjalankan {argv[0]}: {exc}") from exc
    if result.returncode:
        raise CliError(f"Pemeriksaan {argv[0]} gagal (exit {result.returncode}): {scrub(result.stderr)[:2000]}")
    return result.stdout


def discover_flags(help_text):
    """Read Cobra help, including inline and multiline allowed-value lists."""
    flags = {}
    current = None
    for line in ANSI.sub("", help_text).splitlines():
        match = FLAG_LINE.match(line)
        if match:
            name, kind, description = match.groups()
            if kind not in VALUE_TYPES:
                if kind:
                    description = kind + " " + description
                kind = "bool"
            current = {"name": name, "type": kind, "description": description, "details": []}
            flags[name] = current
        elif current and line.startswith(" ") and line.strip():
            current["details"].append(line.strip())
        else:
            current = None
    for spec in flags.values():
        text = " ".join([spec["description"], *spec.pop("details")])
        values = []
        inline = re.search(r"\(allowed values:\s*([^)]*)\)", text, re.I)
        if inline:
            values = [item.strip().strip('\"\'') for item in inline.group(1).split(",")]
        elif re.search(r"allowed values:", text, re.I):
            tail = re.split(r"allowed values:", text, flags=re.I)[1]
            values = re.findall(r"(?:^|\s)-\s+([\w.-]+)", tail.split("(default")[0])
        spec["values"] = [item for item in values if item]
        spec["help"] = text
    if not flags:
        raise CliError("Format --help Trivy tidak dikenali; tidak ada scan yang dijalankan.")
    return flags


def command_display(argv):
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


class Session:
    def __init__(self, project, session_id=None, new=False, state_dir=None):
        self.root, self.base, self.directory = store.project_context(project, state_dir)
        ensure_untracked_storage(self.directory)
        if new:
            self.data = store.create_data({
                "origin": "terminal", "stage": "configuring", "pending_question": "method",
                "scan": {"method": None, "target": None, "cwd": self.root, "severity": "ALL",
                         "explicit_flags": [], "argv_redacted": [], "last_scan_complete": False},
                "baseline": {}, "findings": [], "batches": [], "batch_request": None,
                "last_report": None,
            }, self.root, self.base, self.directory)
        else:
            self.data = store.read(SimpleNamespace(session=session_id), self.root, self.directory)

    def save(self):
        self.data = store.save_data(self.data, self.data["session_id"], self.root, self.base, self.directory)

    def handoff(self):
        print(f"\nSesi: {self.data['session_id']} (tahap: {self.data['stage']})")
        print(f"Project: {self.root}")
        print(f"Folder sesi: {self.directory}")
        print("Kembali ke chat Codex/agent di editor, lalu kirim:")
        print(command_display(["/trivy-porter", "continue", self.data["session_id"], "--project", self.root,
                               "--state-dir", str(self.base)]))
        print("Tidak ada pesan yang dikirim otomatis ke chat.")

    def terminal_command(self):
        return command_display(["trivy-porter", "continue", "--session", self.data["session_id"],
                                "--project", self.root, "--state-dir", str(self.base)])


def select_session(project, session_id, state_dir=None):
    if session_id:
        return Session(project, session_id, state_dir=state_dir)
    root, base, directory = store.project_context(project, state_dir)
    sessions = store.load_sessions(directory, root)
    if not sessions:
        raise CliError("Belum ada sesi untuk folder ini. Jalankan trivy-porter untuk scan baru.")
    if len(sessions) == 1:
        return Session(root, sessions[0]["session_id"], state_dir=str(base))
    options = [(str(index), f"{data['session_id']} — {data['stage']} — {data['updated_at']}")
               for index, data in enumerate(sessions, 1)]
    selected = choice("Pilih sesi yang ingin dilanjutkan:", options)
    return Session(root, sessions[int(selected) - 1]["session_id"], state_dir=str(base))


def ensure_untracked_storage(directory):
    """A local ignore rule cannot protect files that are already in the index."""
    git = shutil.which("git")
    if not git:
        return
    parent = directory
    while not parent.is_dir():
        parent = parent.parent
    result = subprocess.run([git, "rev-parse", "--show-toplevel"], cwd=parent,
                            capture_output=True, text=True, check=False)
    if result.returncode:
        return
    repository = Path(result.stdout.strip()).resolve()
    try:
        relative = directory.relative_to(repository).as_posix()
    except ValueError:
        return
    tracked = subprocess.run([git, "ls-files", "-z", "--", f":(literal){relative}"], cwd=repository,
                             capture_output=True, check=False)
    if tracked.returncode or tracked.stdout:
        raise CliError("Folder sesi sudah dilacak Git atau index tidak dapat diperiksa. Pilih --state-dir lain; CLI tidak mengubah index Anda.")


def manage_storage(args):
    root, base, directory = store.project_context(args.project, args.state_dir)
    print(f"Project: {root}")
    print(f"Root penyimpanan: {base}")
    print(f"Folder sesi project: {directory}")
    if args.action == "storage":
        print("Status: " + ("sudah ada" if directory.is_dir() else "belum dibuat"))
        return 0
    if args.action == "sessions":
        sessions = store.load_sessions(directory, root)
        if not sessions:
            print("Belum ada sesi tersimpan untuk project ini pada lokasi tersebut.")
        for data in sessions:
            print(f"{data['session_id']}  {data['stage']}  diperbarui {data['updated_at']}")
        return 0
    if not args.session and not args.all_sessions:
        raise CliError("Pilih sesi dengan clean --session ID, atau seluruh sesi project ini dengan clean --all.")
    plan = store.cleanup_plan(root, str(base), args.session, args.all_sessions)
    if not plan["sessions"]:
        print("Tidak ada sesi yang perlu dibersihkan.")
        return 0
    print(f"\nAkan menghapus {len(plan['sessions'])} sesi dan {len(plan['files'])} file tersimpan:")
    for item in plan["files"]:
        print(f"- {directory / item['name']}")
    print("Riwayat sesi yang dihapus tidak dapat dilanjutkan. File aplikasi dan output Trivy pilihan pengguna tidak termasuk.")
    while True:
        answer = ask("Hapus file di atas? [y/N]: ").lower()
        if answer in {"", "n", "no", "tidak", "0"}:
            print("Pembersihan dibatalkan. Tidak ada file dihapus.")
            return 0
        if answer in {"y", "yes", "ya"}:
            break
        print("Masukkan y untuk menghapus atau N untuk membatalkan.")
    deleted = store.delete_sessions(plan)
    print(f"Selesai: {len(deleted)} file sesi dihapus.")
    return 0


def set_flag(scan, name, value):
    scan["explicit_flags"] = [item for item in scan["explicit_flags"] if item["name"] != name]
    if value is not None:
        scan["explicit_flags"].append({"name": name, "value": value})


def flag_value(scan, name, fallback=None):
    return next((item["value"] for item in scan["explicit_flags"] if item["name"] == name), fallback)


def collect_target(session, archive=False):
    while True:
        value = ask("Path archive image: " if archive else "Image reference (contoh alpine:3.22): ")
        try:
            literal(value)
            if not value or value.startswith("-"):
                raise CliError("Target wajib diisi dan tidak boleh dimulai dengan '-'.")
            if archive:
                target = Path(value).expanduser()
                if not target.is_absolute():
                    target = Path(session.root) / target
                if not target.is_file():
                    raise CliError("Archive harus menunjuk file yang sudah ada.")
                value = str(target.resolve())
            session.data["scan"]["target"] = value
            session.data["scan"]["target_kind"] = "archive" if archive else "image"
            return
        except CliError as exc:
            print(exc)


def collect_value(spec):
    name, kind, values = spec["name"], spec["type"], spec["values"]
    print(f"\n--{name}: {spec['help']}")
    if kind == "bool":
        answer = choice("Nilai boolean:", [("1", "Default — jangan tambahkan flag"),
                                                ("2", "Aktifkan secara eksplisit"), ("3", "Nonaktifkan secara eksplisit")])
        return {"1": None, "2": "true", "3": "false"}[answer]
    if values:
        print("1. Default — jangan tambahkan flag")
        for index, value in enumerate(values, 2):
            print(f"{index}. {value}")
        multiple = kind in {"strings", "stringArray", "ints"}
        while True:
            answer = ask("Pilihan (boleh beberapa, pisahkan koma) [1]: " if multiple else "Pilihan [1]: ") or "1"
            if answer in {"1", "default"}:
                return None
            if answer == "0":
                raise Cancelled()
            parts = [part.strip() for part in answer.split(",")]
            selected = []
            for part in parts:
                if part.isdecimal() and 2 <= int(part) < len(values) + 2:
                    selected.append(values[int(part) - 2])
                elif part in values:
                    selected.append(part)
                else:
                    break
            else:
                if multiple or len(selected) == 1:
                    return ",".join(dict.fromkeys(selected))
            print("Pilihan tidak valid; default tidak boleh digabung dengan nilai eksplisit.")
    answer = choice("Nilai flag:", [("1", "Default — jangan tambahkan flag"), ("2", "Masukkan nilai custom")])
    if answer == "1":
        return None
    while True:
        value = ask("Nilai (literal; tanpa ekspansi shell): ")
        try:
            literal(value)
            if kind in {"int", "uint", "ints"}:
                for part in value.split(",") if kind == "ints" else [value]:
                    if not re.fullmatch(r"[+-]?\d+", part) or (kind == "uint" and int(part) < 0):
                        raise CliError("Masukkan bilangan bulat yang sesuai tipe flag.")
            if kind in {"float", "float64"} and not math.isfinite(float(value)):
                raise CliError("Masukkan angka finite.")
            if kind == "duration" and not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?(?:ns|us|µs|μs|ms|s|m|h))+|0", value):
                raise CliError("Durasi tidak valid; contoh: 30s atau 5m0s.")
            return value
        except (CliError, ValueError) as exc:
            print(f"Nilai tidak valid: {exc}")


def configure(session, trivy):
    data = session.data
    if data["pending_question"] == "method":
        method = choice("Metode scan yang ingin digunakan?", [("1", "fs — folder kerja saat ini (default)"), ("2", "image — container image")])
        data["scan"]["method"] = "fs" if method == "1" else "image"
        data["scan"]["target"] = "." if method == "1" else None
        data["pending_question"] = "flags" if method == "1" else "target_kind"
        session.save()
    scan = session.data["scan"]
    method = scan["method"]
    version = probe([trivy, "--version"], session.root)
    flags = discover_flags(probe([trivy, method, "--help"], session.root))
    scan["trivy_version"] = scrub(version)
    for item in scan["explicit_flags"]:
        if item["name"] not in flags:
            raise CliError(f"--{item['name']} tidak tersedia pada Trivy saat ini; konfigurasi sesi perlu diperiksa.")
    if session.data["pending_question"] == "target_kind":
        kind = choice("Sumber image:", [("1", "Image reference (default)"), ("2", "Archive lokal — --input")])
        session.data["pending_question"] = "archive" if kind == "2" else "image"
        session.save()
    if session.data["pending_question"] in {"archive", "image"}:
        if session.data["pending_question"] == "archive" and "input" not in flags:
            raise CliError("Trivy ini tidak mendukung --input untuk image.")
        collect_target(session, session.data["pending_question"] == "archive")
        session.data["pending_question"] = "flags"
        session.save()
    names = sorted(name for name in flags if name not in {"severity", "scanners"})
    if "scanners" in flags:
        names.insert(0, "scanners")
    page = 0
    while session.data["pending_question"] in {"flags", "flag_value"}:
        scan = session.data["scan"]
        if session.data["pending_question"] == "flags":
            print("\nKustomisasi scan:")
            print("1. " + ("Selesai — gunakan pilihan saat ini" if scan["explicit_flags"] else "Default — tanpa flag opsional"))
            for index in range(page * 12, min((page + 1) * 12, len(names))):
                name = names[index]
                suffix = " [gunakan environment/autentikasi]" if name in CREDENTIAL_FLAGS else ""
                print(f"{index + 2}. --{name} — {flags[name]['description']}{suffix}")
            print("n/p = halaman berikut/sebelumnya; --nama = pilih langsung; r = reset; 0 = batal")
            answer = ask("Pilihan [1]: ") or "1"
            if answer in {"1", "default"}:
                if flag_value(scan, "format") == "template" and flag_value(scan, "template") is None:
                    print("Format template memerlukan --template; pilih nilainya terlebih dahulu.")
                    continue
                session.data["pending_question"] = "severity"
                session.save()
                break
            if answer == "0":
                raise Cancelled()
            if answer in {"n", "p"}:
                page = (page + (1 if answer == "n" else -1)) % max(1, (len(names) + 11) // 12)
                continue
            if answer == "r":
                scan["explicit_flags"] = []
                session.save()
                continue
            name = answer[2:] if answer.startswith("--") else answer
            if answer.isdecimal() and 2 <= int(answer) <= len(names) + 1:
                name = names[int(answer) - 2]
            if name not in flags or name == "severity":
                print("Flag tidak tersedia untuk metode ini; severity ditanyakan terpisah.")
                continue
            if name in NO_SCAN_FLAGS:
                print("Flag ini tidak menghasilkan findings scan. Pilih flag scan lain.")
                continue
            if name in CREDENTIAL_FLAGS:
                print("Gunakan autentikasi terkonfigurasi/environment sebelum menjalankan CLI; nilai kredensial tidak disimpan.")
                continue
            if name == "input":
                session.data["pending_question"] = "archive"
                session.save()
                collect_target(session, True)
                session.data["pending_question"] = "flags"
                session.save()
                continue
            session.data["pending_flag"] = name
            session.data["pending_question"] = "flag_value"
            session.save()
        name = session.data["pending_flag"]
        value = collect_value(flags[name])
        if name == "format" and value in {"cyclonedx", "spdx", "spdx-json", "github"}:
            print("Format ini membatasi jenis data/finding dalam laporan. Agent akan menilai cakupannya; output kosong bukan bukti nol finding.")
        if name == "format" and value not in {None, "table", "json"}:
            print("Format custom ini tidak disalin ke sesi agent. Artifact asli mengikuti pilihan Anda; agent akan menjelaskan jika bukti kurang.")
        set_flag(session.data["scan"], name, value)
        session.data.pop("pending_flag", None)
        session.data["pending_question"] = "flags"
        session.save()
    if session.data["pending_question"] == "severity":
        answer = choice("Kategori severity yang ingin ditampilkan:", [("1", "Seluruh kategori — tanpa --severity (default)"),
                        ("2", "CRITICAL"), ("3", "HIGH"), ("4", "MEDIUM"), ("5", "LOW")])
        session.data["scan"]["severity"] = {"1": "ALL", "2": "CRITICAL", "3": "HIGH", "4": "MEDIUM", "5": "LOW"}[answer]
        session.data["pending_question"] = "scan"
        session.save()
    return flags


def scan_argv(scan):
    argv = ["trivy", scan["method"]]
    if scan.get("target_kind") == "archive":
        argv.extend(["--input", scan["target"]])
    for item in scan["explicit_flags"]:
        argv.append(f"--{item['name']}={item['value']}")
    if scan.get("inherited_skip_dirs") is not None:
        argv.append(f"--skip-dirs={scan['inherited_skip_dirs']}")
    for path in scan.get("managed_state_exclusions", []):
        encoded = io.StringIO()
        csv.writer(encoded, lineterminator="").writerow([path])
        argv.append("--skip-dirs=" + encoded.getvalue())
    if scan["severity"] != "ALL":
        argv.extend(["--severity", scan["severity"]])
    if scan.get("target_kind") != "archive":
        argv.append(scan["target"])
    return argv


def file_hash(path):
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inherited_settings(session):
    scan = session.data["scan"]
    env = {key: scrub(value) for key, value in os.environ.items() if key in COVERAGE_ENV}
    config = flag_value(scan, "config", os.environ.get("TRIVY_CONFIG", "trivy.yaml"))
    ignore = flag_value(scan, "ignorefile", os.environ.get("TRIVY_IGNOREFILE", ".trivyignore"))
    files = {}
    secret_config = flag_value(scan, "secret-config", os.environ.get("TRIVY_SECRET_CONFIG", "trivy-secret.yaml"))
    for name in (config, ignore, secret_config):
        if not name:
            continue
        candidate = Path(name).expanduser()
        if not candidate.is_absolute():
            candidate = Path(session.root) / candidate
        if candidate.is_file():
            files[str(candidate.resolve())] = file_hash(candidate)
    config_path = Path(config).expanduser() if config else None
    if config_path is not None and not config_path.is_absolute():
        config_path = Path(session.root) / config_path
    return {"files": files, "config_file": str(config_path.resolve()) if config_path is not None and config_path.is_file() else None,
            "coverage_environment": env,
            "environment_names": sorted(key for key in os.environ if key.startswith("TRIVY_")),
            "requires_agent_review": bool(files or env)}


def baseline(project, settings):
    filenames = {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
                 "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "requirements.txt", "poetry.lock", "uv.lock",
                 "pyproject.toml", "Gemfile", "Gemfile.lock", "composer.json", "composer.lock", "Dockerfile"}
    hashes = {name: file_hash(Path(project) / name) for name in filenames if (Path(project) / name).is_file()}
    hashes.update(settings["files"])
    head = None
    if shutil.which("git"):
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            head = result.stdout.strip()
    return {"git_head": head, "relevant_file_hashes": hashes}


def sanitize_json(raw):
    """Whitelist report fields: never carry image environment, matches or code snippets."""
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("Results"), list):
        raise ValueError("Not a Trivy findings report")
    result = {key: data[key] for key in ("SchemaVersion", "ArtifactName", "ArtifactType") if key in data}
    fields = {
        "Vulnerabilities": ("VulnerabilityID", "PkgName", "InstalledVersion", "FixedVersion", "Severity", "Title", "PrimaryURL", "Status", "PkgPath"),
        "Misconfigurations": ("ID", "AVDID", "Type", "Title", "Severity", "Status", "Message", "PrimaryURL"),
        "Secrets": ("RuleID", "Category", "Severity", "Title", "StartLine", "EndLine"),
        "Licenses": ("Severity", "Category", "PkgName", "FilePath", "Name", "Confidence", "Link"),
    }
    result["Results"] = []
    result["omitted_fields"] = sorted(set(data) - set(result) - {"Results"})
    for item in data["Results"]:
        if not isinstance(item, dict):
            continue
        clean = {key: item[key] for key in ("Target", "Class", "Type", "MisconfSummary") if key in item}
        for key, allowed in fields.items():
            if key in item and isinstance(item[key], list):
                clean[key] = [{field: finding[field] for field in allowed if field in finding}
                              for finding in item[key] if isinstance(finding, dict)]
        if "Crypto" in item or "CryptoAssets" in item:
            clean["omitted_crypto_details"] = True
        omitted = sorted(set(item) - set(clean))
        if omitted:
            clean["omitted_fields"] = omitted
        result["Results"].append(clean)
    result["porter_note"] = "Sanitized subset. Source snippets, secret matches, package details and image metadata omitted."
    def scrub_fields(value):
        if isinstance(value, str):
            return scrub(value)
        if isinstance(value, list):
            return [scrub_fields(item) for item in value]
        if isinstance(value, dict):
            return {key: scrub_fields(item) for key, item in value.items()}
        return value

    return json.dumps(scrub_fields(result), ensure_ascii=False, indent=2) + "\n"


def sanitize_table(raw):
    # Detailed secret output is free text and can contain multiline source code.
    # Keep only metadata from those sections. Custom/unrecognized output fails closed.
    lines = strip_terminal_controls(raw).splitlines()
    if not any(re.search(r"Report Summary|Total:|Secrets:|[│┌┐└┘]", line) for line in lines):
        return "[Output nonstandar tidak disimpan; gunakan hasil/format yang dipilih untuk analisis lokal.]\n"
    output = []
    secret_section = False
    for index, line in enumerate(lines):
        if index + 1 < len(lines) and re.fullmatch(r"={3,}", lines[index + 1].strip()):
            secret_section = bool(re.search(r"\(secrets?\)|secret", line, re.I))
        if re.match(r"\s*Secrets:\s*\d", line):
            secret_section = True
        if secret_section:
            finding = re.match(r"\s*(UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL):\s*([\w.-]+)", line)
            if finding:
                output.append(f"{finding[1]}: {finding[2]} [secret match/source omitted]")
            elif re.search(r"\(secrets?\)|^\s*(?:Secrets|Total):", line, re.I):
                output.append(line)
            continue
        # Source lines in misconfiguration reports can also expose credentials.
        if re.match(r"\s*(?:[│|>]\s*)?\d+\s+", line):
            output.append("[source line omitted]")
            continue
        output.append(line)
    return scrub("\n".join(output)) + "\n"


def sanitized_report(raw, output_format, truncated=False):
    if truncated:
        return "[Output melebihi batas tangkapan; tidak disimpan untuk menghindari potongan rahasia/JSON.]\n"
    try:
        return sanitize_json(raw)
    except (ValueError, TypeError):
        if output_format not in {"table", "auto"}:
            return "[Format custom/non-JSON tidak disalin ke sesi; perlu tinjau artifact pilihan pengguna secara lokal.]\n"
        return sanitize_table(raw)


def sanitize_stderr(raw):
    # Retain diagnostic prefixes only. Debug payloads, continuation lines and arbitrary
    # server responses are not a safe log format for secret-bearing scan inputs.
    lines = []
    for line in ANSI.sub("", raw).splitlines():
        match = re.search(r"\b(INFO|WARN|ERROR|FATAL)\b(.*)", line)
        if match:
            message = scrub(match[2])
            # A diagnostic may embed source text or a quoted server response.
            message = re.sub(r'"(?:[^"\\]|\\.)*"', '"[quoted value omitted]"', message)
            lines.append(match[1] + message)
    return "\n".join(lines) + ("\n" if lines else "[Tidak ada diagnostic standar tersimpan.]\n")


def capture_process(argv, cwd):
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def drain(stream, index):
        with stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                remaining = CAPTURE_LIMIT - len(buffers[index])
                buffers[index].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated[index] = True

    readers = [threading.Thread(target=drain, args=(stream, index), daemon=True)
               for index, stream in enumerate((process.stdout, process.stderr))]
    for reader in readers:
        reader.start()
    interrupted = False
    try:
        process.wait()
    except KeyboardInterrupt:
        interrupted = True
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    finally:
        for reader in readers:
            reader.join()
    return [buffer.decode("utf-8", errors="replace") for buffer in buffers], process.returncode, interrupted, truncated


def write_artifact(path, text):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def output_file(scan, project):
    value = flag_value(scan, "output", os.environ.get("TRIVY_OUTPUT"))
    if not value or "://" in value:
        return None
    target = Path(value).expanduser()
    return target if target.is_absolute() else Path(project) / target


def output_identity(path):
    if path is None or not path.is_file():
        return None
    info = path.stat()
    return (info.st_mtime_ns, info.st_size, info.st_ino)


def report_format(scan, settings):
    selected = flag_value(scan, "format", os.environ.get("TRIVY_FORMAT"))
    if selected:
        return selected
    # stdlib has no YAML parser. Never mistake a template/SARIF inherited from an
    # unparsed config for a table just because its text contains table markers.
    return "inherited" if settings["config_file"] else "auto"


def state_exclusions(session):
    if session.data["scan"]["method"] != "fs":
        return []
    paths = []
    for partition in store.managed_partitions(session.base, session.directory):
        try:
            relative = partition.relative_to(Path(session.root)).as_posix()
        except ValueError:
            continue
        # Trivy treats skip paths as globs. Refuse ambiguous literal names rather
        # than excluding unrelated application paths through a wildcard match.
        if any(char in relative for char in "*?[]\\"):
            raise CliError("Path sesi mengandung karakter glob. Gunakan --state-dir di luar target scan atau path tanpa karakter glob.")
        paths.append(relative)
    return paths


def run_scan(session, trivy, supported_flags=None):
    settings = inherited_settings(session)
    scan = session.data["scan"]
    exclusions = state_exclusions(session)
    scan["managed_state_exclusions"] = exclusions
    scan["inherited_skip_dirs"] = None
    if exclusions:
        flags = supported_flags if supported_flags is not None else discover_flags(probe([trivy, "fs", "--help"], session.root))
        if "skip-dirs" not in flags or flags["skip-dirs"]["type"] != "strings":
            raise CliError("Trivy ini tidak mendukung pengecualian folder sesi dengan --skip-dirs. Pilih --state-dir di luar target scan.")
        explicit_skip = flag_value(scan, "skip-dirs")
        inherited_skip = os.environ.get("TRIVY_SKIP_DIRS")
        if explicit_skip is None and inherited_skip:
            scan["inherited_skip_dirs"] = literal(inherited_skip)
        elif explicit_skip is None and settings["config_file"]:
            print("\nPengecualian sesi lokal memerlukan --skip-dirs. Daftar skip-dirs dari file konfigurasi belum dipastikan; CLI tidak akan menimpanya.")
            choice("Periksa konfigurasi, lalu masukkan seluruh daftar --skip-dirs yang ingin dipakai:",
                   [("1", "Kembali ke kustomisasi flags (default)"), ("0", "Batal; gunakan penyimpanan di luar target scan")])
            session.data["pending_question"] = "flags"
            session.save()
            return None
        print("\nFolder sesi otomatis dikecualikan dari scan filesystem:")
        for path in exclusions:
            print(f"- {path}")
    output_format = report_format(scan, settings)
    previous = scan.get("inherited_settings")
    if settings["requires_agent_review"] and previous != settings:
        print("\nScan mewarisi pengaturan berikut; default menu tidak menonaktifkannya:")
        for filename in settings["files"]:
            print(f"- File konfigurasi/ignore: {filename} (isi perlu ditinjau agent)")
        for name, value in settings["coverage_environment"].items():
            print(f"- {name}={value}")
        print("Cakupan aktual mengikuti precedence Trivy, termasuk filter/ignore. Tidak diklaim seluruh cakupan.")
        if output_format == "inherited":
            print("Format dari file konfigurasi belum dipastikan. Hanya JSON Trivy yang dikenali dapat disalin ke sesi; pilih --format table/json secara eksplisit bila diperlukan.")
        answer = choice("Gunakan pengaturan warisan ini?", [("1", "Gunakan dan catat untuk ditinjau agent (default)"),
                        ("2", "Kembali ke kustomisasi flags"), ("0", "Batal; periksa konfigurasi terlebih dahulu")])
        if answer == "2":
            session.data["pending_question"] = "flags"
            session.save()
            return None
    scan["inherited_settings"] = settings
    scan["credential_sources"] = [name for name in settings["environment_names"] if SENSITIVE_NAME.search(name)]
    scan["configuration_fingerprint"] = settings["files"]
    scan["argv_redacted"] = scan_argv(scan)
    scan["last_scan_at"] = store.timestamp()
    scan["last_scan_complete"] = None
    session.data["baseline"] = baseline(session.root, settings)
    session.data["pending_question"] = "scan_running"
    session.save()
    scan = session.data["scan"]
    argv = list(scan["argv_redacted"])
    argv[0] = trivy
    print(f"\nMenjalankan: {command_display(scan['argv_redacted'])}", flush=True)
    print("Menunggu Trivy; hasil yang sudah disanitasi ditampilkan setelah proses berakhir.", flush=True)
    destination = output_file(scan, session.root)
    before = output_identity(destination)
    raw, exit_code, interrupted, truncated = capture_process(argv, session.root)
    source = "stdout"
    if destination is not None:
        if output_identity(destination) != before and destination.is_file():
            with destination.open("rb") as handle:
                payload = handle.read(CAPTURE_LIMIT + 1)
            raw[0] = payload[:CAPTURE_LIMIT].decode("utf-8", errors="replace")
            truncated[0] = len(payload) > CAPTURE_LIMIT
            source = str(destination.resolve())
        else:
            raw[0] = ""
            source = "output artifact absent or unchanged; requires review"
    stdout = sanitized_report(raw[0], output_format, truncated[0])
    stderr = sanitize_stderr(raw[1])
    run_id = uuid.uuid4().hex
    prefix = f"{session.data['session_id']}.{run_id}"
    stdout_path = session.directory / f"{prefix}.stdout.txt"
    stderr_path = session.directory / f"{prefix}.stderr.txt"
    write_artifact(stdout_path, stdout)
    write_artifact(stderr_path, stderr)
    scan["last_scan_exit_code"] = exit_code
    scan["result"] = {"stdout_path": str(stdout_path), "stderr_path": str(stderr_path),
                      "exit_code": exit_code, "interrupted": interrupted, "truncated": any(truncated),
                      "format": output_format, "source": source, "sanitized": True, "run_id": run_id}
    session.data["stage"] = "awaiting_analysis"
    session.data["pending_question"] = None
    session.save()
    print("\n" + stdout)
    if raw[1]:
        print(stderr)
    print(f"Trivy selesai: exit {exit_code}" + (" (terinterupsi)" if interrupted else ""))
    print("Hasil perlu dianalisis di chat; exit code saja tidak membuktikan scan lengkap atau nol finding.")
    session.handoff()
    return 130 if interrupted else exit_code if exit_code >= 0 else 1


def git_preparation_pending(data):
    batches = data.get("batches", [])
    if not batches:
        return False
    preparation = batches[-1].get("git_preparation") or {}
    if preparation.get("pending_substep"):
        return True
    if any(preparation.get(field) in {"pending", "blocked", "failed"}
           for field in ("status", "staging_status", "generation_status")):
        return True
    if preparation.get("generation_status") in {"generated", "skipped_empty"}:
        return preparation.get("staging_status") not in {None, "staged", "skipped_empty"}
    return preparation.get("status") not in {"generated", "skipped_empty"}


def continue_session(session):
    data = session.data
    print(f"\nSesi {data['session_id']}: {data['stage']}")
    if data["stage"] == "complete":
        print("Sesi selesai. Jalankan trivy-porter tanpa continue untuk scan baru.")
        return 0
    if data["stage"] in {"awaiting_analysis", "batch_in_progress"} or git_preparation_pending(data):
        session.handoff()
        return 0
    if data["stage"] in {"awaiting_batch", "paused"}:
        if (data.get("batch_request") or {}).get("status") == "pending":
            print("Pilihan batch sudah tersimpan; lanjutkan di chat sebelum membuat pilihan lain.")
            session.handoff()
            return 0
        actionable = [item for item in data.get("findings", []) if item.get("status") in {"pending", "unverified"}]
        if not actionable:
            print("Tidak ada finding actionable tersimpan. Agent perlu meninjau status/blocker.")
            session.handoff()
            return 0
        print(f"Finding pending/unverified: {len(actionable)}")
        while True:
            answer = ask("Berapa finding yang ingin ditangani pada batch ini? [1]: ") or "1"
            if answer == "default":
                answer = "1"
            if re.fullmatch(r"[0-9]+", answer) and int(answer) > 0:
                break
            print("Masukkan bilangan bulat positif, misalnya 1 atau 3.")
        data["batch_request"] = {"id": uuid.uuid4().hex, "count": int(answer),
                                 "submitted_at": store.timestamp(), "status": "pending"}
        data["pending_question"] = None
        session.save()
        print(f"Pilihan {int(answer)} finding disimpan. Belum ada file aplikasi yang diubah.")
        session.handoff()
        return 0
    return None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Menu Trivy lokal; analisis/perbaikan dilanjutkan manual melalui chat editor.")
    parser.add_argument("action", nargs="?", choices=["continue", "storage", "sessions", "clean"],
                        help="continue: lanjutkan; storage: lihat lokasi; sessions: daftar sesi; clean: bersihkan sesi.")
    parser.add_argument("--project", default=".", help="Folder project yang discan (default: cwd terminal).")
    parser.add_argument("--session", help="ID sesi untuk continue, clean, atau --download; continue tanpa ID menampilkan pilihan bila perlu.")
    parser.add_argument("--state-dir", help="Folder sesi (default: .trivy-porter di cwd; mengalahkan TRIVY_PORTER_STATE_DIR).")
    parser.add_argument("--all", dest="all_sessions", action="store_true", help="clean: seluruh sesi untuk project ini saja.")
    shortcuts = parser.add_mutually_exclusive_group()
    shortcuts.add_argument("--clean", action="store_true", help="Hapus seluruh folder .trivy-porter di cwd, tanpa pertanyaan tambahan.")
    shortcuts.add_argument("--download", action="store_true", help="Ekspor laporan sesi terbaru ke folder Downloads untuk diunggah ke agent.")
    shortcuts.add_argument("--prompt", action="store_true", help="Cetak prompt untuk disalin ke chat bersama laporan JSON; ganti n dengan jumlah temuan.")
    parser.add_argument("--download-dir", help="Folder tujuan --download (default: ~/Downloads).")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    session = None
    try:
        if args.download_dir is not None and not args.download:
            raise CliError("--download-dir hanya digunakan bersama --download.")
        if (args.clean or args.download or args.prompt) and args.action:
            raise CliError("--clean/--download/--prompt tidak digabung dengan subcommand lain.")
        if args.session and args.action not in {"continue", "clean"} and not args.download:
            raise CliError("--session digunakan bersama continue, clean, atau --download.")
        if args.all_sessions and args.action != "clean":
            raise CliError("--all hanya digunakan bersama clean.")
        if args.all_sessions and args.session:
            raise CliError("Pilih salah satu: --session ID atau --all.")
        if args.prompt:
            print(UPLOAD_PROMPT)
            return 0
        print("Trivy Porter — terminal (0 pada menu = batal; Ctrl+C untuk membatalkan input)")
        if args.clean:
            if args.state_dir is not None or args.session or args.all_sessions:
                raise CliError("--clean hanya menghapus .trivy-porter lokal; untuk lokasi lain gunakan clean --session ID atau clean --all.")
            if Path(args.project).expanduser().resolve(strict=True) != Path.cwd().resolve():
                raise CliError("Jalankan --clean dari folder project tersebut; --project tidak memindahkan target pembersihan lokal.")
            target, removed = report_transfer.clean_local_store()
            print(f"Folder dihapus seluruhnya: {target}" if removed else f"Tidak ada folder yang perlu dihapus: {target}")
            return 0
        if args.download:
            output, session_id = report_transfer.download_report(
                args.project, args.state_dir, args.session, args.download_dir,
                scrub, sanitized_report, sanitize_stderr)
            print(f"Sesi diekspor: {session_id}")
            print(f"File siap diunggah ke agent AI: {output}")
            return 0
        if args.action in {"storage", "sessions", "clean"}:
            return manage_storage(args)
        if args.action == "continue":
            session = select_session(args.project, args.session, args.state_dir)
            result = continue_session(session)
            if result is not None:
                return result
        trivy = shutil.which("trivy")
        if not trivy:
            raise CliError("Trivy belum tersedia di PATH. Pasang Trivy terlebih dahulu; CLI tidak memasangnya otomatis.")
        if session is None:
            session = Session(args.project, new=True, state_dir=args.state_dir)
        if session.data["stage"] == "scan_failed" or session.data.get("pending_question") == "scan_running":
            choice("Scan sebelumnya gagal/tidak diketahui hasilnya. Jalankan ulang dengan pilihan tersimpan?",
                   [("1", "Jalankan ulang (default)"), ("0", "Batal")])
            session.data["stage"] = "configuring"
            session.data["pending_question"] = "scan"
            session.save()
        while True:
            supported_flags = configure(session, trivy)
            result = run_scan(session, trivy, supported_flags)
            if result is not None:
                return result
    except (Cancelled, KeyboardInterrupt):
        print("\nDibatalkan. Tidak ada jawaban default yang dikirim otomatis.")
        if session is not None:
            print(f"Pilihan yang sudah dijawab tersimpan. Lanjutkan: {session.terminal_command()}")
        return 130
    except (CliError, store.StoreError, OSError, ValueError) as exc:
        print(f"Error: {scrub(str(exc))}", file=sys.stderr)
        if session is not None:
            print(f"Sesi tersimpan: {session.data['session_id']}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
