#!/usr/bin/env python3
"""Manage Trivy Porter session JSON in a configurable store, using only stdlib.

The helper stores state; it never scans, changes dependencies, or redacts data.
Callers must remove credentials and secret snippets before submitting JSON.
"""

import argparse
import copy
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from types import SimpleNamespace
import uuid


STAGES = {
    "configuring", "scan_failed", "awaiting_analysis", "awaiting_batch", "batch_in_progress",
    "paused", "complete",
}
SCHEMA_VERSION = 1
MANAGED = {"schema_version", "project_root", "session_id", "revision", "created_at", "updated_at"}
SESSION_ID = re.compile(r"[0-9a-f]{32}\Z")
PARTITION_ID = re.compile(r"[0-9a-f]{64}\Z")
RUN_DIRECTORY = re.compile(r"[0-9]{8}-[0-9]{4}-(?:fs|image|scan)(?:-[1-9][0-9]*)?\Z")
STORAGE_IGNORE = "# Trivy Porter session storage\n*\n"
# Earlier Windows releases wrote the marker in text mode, translating it to CRLF; that storage is not migrated.
LEGACY_STORAGE_IGNORE = STORAGE_IGNORE.replace("\n", "\r\n").encode("utf-8")
LEGACY_STORAGE_HINT = ("Session storage was created by an older Trivy Porter release and is no longer supported. "
                       "Run `trivy-porter --clean` from the project folder to remove .trivy-porter, then run "
                       "`trivy-porter` to scan again.")


class StoreError(Exception):
    pass


def linked(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def project_context(project, state_dir=None):
    try:
        root = Path(project).expanduser().resolve(strict=True)
    except OSError as exc:
        raise StoreError(f"Cannot resolve project directory: {exc}") from exc
    if not root.is_dir():
        raise StoreError("--project must name an existing directory.")
    if state_dir is not None and not str(state_dir).strip():
        raise StoreError("--state-dir must not be empty.")
    override = state_dir if state_dir is not None else os.environ.get("TRIVY_PORTER_STATE_DIR")
    if override:
        base = Path(override).expanduser().resolve()
    else:
        base = (Path.cwd() / ".trivy-porter").resolve()
    key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    return str(root), base, base / key


def validate_id(session_id):
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        raise StoreError("Session ID must be the 32-character hexadecimal ID returned by create.")


def validate_payload(data):
    if not isinstance(data, dict):
        raise StoreError("Session JSON must be an object.")
    if not isinstance(data.get("stage"), str) or data["stage"] not in STAGES:
        raise StoreError("stage must be one of: " + ", ".join(sorted(STAGES)))


def reject_constant(value):
    raise StoreError(f"Non-JSON numeric constant is not permitted: {value}")


def read_json(path, validate=True):
    try:
        if str(path) == "-":
            data = json.load(sys.stdin, parse_constant=reject_constant)
        else:
            with Path(path).open(encoding="utf-8") as handle:
                data = json.load(handle, parse_constant=reject_constant)
    except (OSError, ValueError) as exc:
        raise StoreError(f"Cannot read session JSON: {exc}") from exc
    if validate:
        validate_payload(data)
    return data


def read_stored(path, project_root):
    if linked(path) or not path.is_file():
        raise StoreError(f"Session is not a regular file: {path.name}")
    data = read_json(path)
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise StoreError(f"Unsupported stored schema_version; expected {SCHEMA_VERSION}: {path.name}")
    if data.get("project_root") != project_root or (path.name != "session.json" and data.get("session_id") != path.stem):
        raise StoreError(f"Stored session identity does not match its project or filename: {path.name}")
    validate_id(data.get("session_id"))
    if type(data.get("revision")) is not int or data["revision"] < 1:
        raise StoreError(f"Stored session has an invalid revision: {path.name}")
    if not all(isinstance(data.get(key), str) and data[key] for key in ("created_at", "updated_at")):
        raise StoreError(f"Stored session has missing timestamps: {path.name}")
    return data


def owned_directory(path):
    if linked(path) or not path.is_dir():
        return False
    marker = path / ".gitignore"
    if linked(marker) or not marker.is_file():
        return False
    size = marker.stat().st_size
    if size == len(LEGACY_STORAGE_IGNORE) and marker.read_bytes() == LEGACY_STORAGE_IGNORE:
        raise StoreError(LEGACY_STORAGE_HINT)
    return size == len(STORAGE_IGNORE.encode("utf-8")) and marker.read_bytes() == STORAGE_IGNORE.encode("utf-8")


def session_paths(directory, project_root):
    """Discover readable folders and the original project-hash layout."""
    base = directory.parent
    if not base.exists():
        return []
    if linked(base) or not base.is_dir() or linked(directory):
        raise StoreError("Project state path must be a directory, not a symlink.")
    paths = []
    if directory.exists():
        if not directory.is_dir():
            raise StoreError("Project state path must be a directory.")
        paths.extend(path for path in directory.glob("*.json") if SESSION_ID.fullmatch(path.stem))
    for folder in base.iterdir():
        if not RUN_DIRECTORY.fullmatch(folder.name) or not owned_directory(folder):
            continue
        path = folder / "session.json"
        if not path.exists() and not linked(path):
            continue
        # Shared custom roots can contain sessions for more than one project.
        if linked(path) or not path.is_file():
            raise StoreError("Session metadata must be a regular file.")
        data = read_json(path, validate=False)
        if isinstance(data, dict) and data.get("project_root") == project_root:
            paths.append(path)
    return paths


def load_sessions(directory, project_root):
    sessions = [read_stored(path, project_root) for path in session_paths(directory, project_root)]
    identifiers = [item["session_id"] for item in sessions]
    if len(set(identifiers)) != len(identifiers):
        raise StoreError("Duplicate stored session IDs; inspect storage before continuing.")
    return sorted(sessions, key=lambda item: (item["created_at"], item["session_id"]), reverse=True)


def session_path(session_id, project_root, directory):
    validate_id(session_id)
    candidates = []
    for path in session_paths(directory, project_root):
        data = read_stored(path, project_root)
        if data["session_id"] == session_id:
            candidates.append(path)
    if len(candidates) != 1:
        raise StoreError("Session was not found for this project, or its ID is duplicated.")
    return candidates[0]


def session_directory(data, base, directory):
    """Return the actual folder while project_context retains its legacy key."""
    if directory.parent != base:
        raise StoreError("Session storage context does not match its root.")
    return session_path(data["session_id"], data["project_root"], directory).parent


def summary(data):
    return {key: data[key] for key in ("session_id", "stage", "revision", "created_at", "updated_at")}


def ensure_storage_ignore(directory):
    """Ignore only this managed partition, even when the chosen root is an app."""
    path = directory / ".gitignore"
    if linked(path) or (path.exists() and not path.is_file()):
        raise StoreError("Storage .gitignore must be a regular file.")
    if path.exists():
        content = path.read_bytes()
        if content == LEGACY_STORAGE_IGNORE:
            raise StoreError(LEGACY_STORAGE_HINT)
        if content != STORAGE_IGNORE.encode("utf-8"):
            raise StoreError("Storage .gitignore differs from the managed rule; inspect it before saving sessions.")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    # newline="" keeps LF on Windows so owned_directory recognizes the marker byte for byte.
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(STORAGE_IGNORE)
        handle.flush()
        os.fsync(handle.fileno())


def managed_partitions(base, current):
    """Only marker-owned folders are excluded, never an entire custom root."""
    if not base.is_dir():
        return []
    return sorted(path for path in base.iterdir()
                  if (PARTITION_ID.fullmatch(path.name) or RUN_DIRECTORY.fullmatch(path.name)
                      or path.name == ".locks") and owned_directory(path))


def cleanup_plan(project, state_dir=None, session_id=None, all_sessions=False):
    """Preview only helper-owned session files; never follow saved output paths."""
    if bool(session_id) == bool(all_sessions):
        raise StoreError("Choose exactly one of --session ID or --all.")
    project_root, base, directory = project_context(project, state_dir)
    if session_id:
        data = read(SimpleNamespace(session=session_id), project_root, directory)
        sessions = [data]
    else:
        sessions = load_sessions(directory, project_root)
    files = []
    for data in sessions:
        if data["stage"] == "batch_in_progress" or data.get("pending_question") in {"scan_running", "build_running"}:
            raise StoreError(f"Session {data['session_id']} has an active scan/build/batch. Finish or recover it before cleanup.")
        sid = data["session_id"]
        metadata = session_path(sid, project_root, directory)
        folder = metadata.parent
        pattern = re.compile(rf"{sid}(?:\.[0-9a-f]{{32}})?\.(?:stdout|stderr)\.txt\Z")
        readable = {"report.json", "scan.stdout.txt", "scan.stderr.txt", "build.stdout.txt", "build.stderr.txt"}
        candidates = [metadata]
        candidates.extend(path for path in folder.iterdir()
                          if pattern.fullmatch(path.name) or (metadata.name == "session.json" and path.name in readable))
        for path in candidates:
            if linked(path) or not path.is_file():
                raise StoreError(f"Cleanup refuses non-regular session files: {path.name}")
            info = path.lstat()
            files.append({"name": path.relative_to(base).as_posix(),
                          "identity": [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]})
    return {"project_root": project_root, "state_root": str(base), "directory": str(base),
            "session_id": session_id, "all_sessions": all_sessions,
            "sessions": [summary(data) for data in sessions],
            "files": sorted(files, key=lambda item: item["name"])}


def delete_sessions(plan):
    """Delete an unchanged preview after the caller has obtained confirmation."""
    if not plan["sessions"]:
        return []
    root, base, directory = project_context(plan["project_root"], plan["state_root"])
    with project_lock(base, directory):
        current = cleanup_plan(root, str(base), plan["session_id"], plan["all_sessions"])
        if current != plan:
            raise StoreError("Session/files changed after the preview. Review a fresh cleanup plan before deleting.")
        # Keep metadata until artifacts are removed. Never remove the shared lock
        # or recursively remove a folder that could contain another writer's files.
        deleted = []
        for item in sorted(plan["files"], key=lambda item: (item["name"].endswith(".json"), item["name"])):
            path = base / item["name"]
            path.unlink()
            deleted.append(str(path))
        return deleted


@contextmanager
def project_lock(base, directory):
    if linked(base) or linked(directory):
        raise StoreError("State directories must not be symlinks.")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    locks = base / ".locks"
    if linked(locks):
        raise StoreError("Storage lock directory must not be a symlink.")
    locks.mkdir(mode=0o700, exist_ok=True)
    os.chmod(locks, 0o700)
    lock_path = locks / "store.lock"
    with ExitStack() as handles:
        handles.enter_context(file_lock(lock_path))
        ensure_storage_ignore(locks)
        # Older helpers synchronize legacy JSON through this existing project
        # folder; use the same lock when updating those sessions.
        if directory.is_dir():
            handles.enter_context(file_lock(directory / ".lock"))
        yield


@contextmanager
def file_lock(lock_path):
    if linked(lock_path) or (lock_path.exists() and not lock_path.is_file()):
        raise StoreError("Storage lock must be a regular file.")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    with os.fdopen(fd, "r+b") as handle:
        os.chmod(lock_path, 0o600)
        if os.name == "nt":
            import msvcrt
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_atomic(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".session-", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create(args, project_root, base, directory):
    return create_data(read_json(args.from_file), project_root, base, directory)


def create_data(payload, project_root, base, directory):
    """Create from an in-memory payload, using the same checks as the JSON CLI."""
    data = copy.deepcopy(payload)
    validate_payload(data)
    supplied = MANAGED.intersection(data)
    if supplied:
        raise StoreError("create input must omit helper-managed fields: " + ", ".join(sorted(supplied)))
    with project_lock(base, directory):
        session_id = uuid.uuid4().hex
        while any(item["session_id"] == session_id for item in load_sessions(directory, project_root)):
            session_id = uuid.uuid4().hex
        scan = data.get("scan") if isinstance(data.get("scan"), dict) else {}
        action = scan.get("method") if scan.get("method") in {"fs", "image"} else "scan"
        label = datetime.now().astimezone().strftime("%Y%m%d-%H%M-") + action
        number = 1
        while True:
            folder = base / (label if number == 1 else label + "-" + str(number))
            try:
                folder.mkdir(mode=0o700)
                break
            except FileExistsError:
                number += 1
        ensure_storage_ignore(folder)
        now = timestamp()
        data.update(schema_version=SCHEMA_VERSION, project_root=project_root, session_id=session_id, revision=1,
                    created_at=now, updated_at=now)
        write_atomic(folder / "session.json", data)

    return data


def read(args, project_root, directory):
    if args.session:
        validate_id(args.session)
        return read_stored(session_path(args.session, project_root, directory), project_root)
    sessions = load_sessions(directory, project_root)
    if not sessions:
        raise StoreError("No saved sessions for this project.")
    if len(sessions) != 1:
        choices = "\n".join(
            f"  {item['session_id']}  stage={item['stage']}  updated={item['updated_at']}"
            for item in sessions
        )
        raise StoreError("Multiple sessions exist; choose --session ID:\n" + choices)
    return sessions[0]


def save(args, project_root, base, directory):
    return save_data(read_json(args.from_file), args.session, project_root, base, directory)


def save_data(payload, session_id, project_root, base, directory):
    """Save a complete payload; stale revisions are rejected for every caller."""
    validate_id(session_id)
    data = copy.deepcopy(payload)
    validate_payload(data)
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise StoreError(f"Unsupported input schema_version; expected {SCHEMA_VERSION} from read.")
    if data.get("project_root") != project_root:
        raise StoreError("Input project_root does not match --project.")
    if data.get("session_id") != session_id:
        raise StoreError("Input session_id does not match --session.")
    if type(data.get("revision")) is not int or data["revision"] < 1:
        raise StoreError("save input must include the positive integer revision returned by read.")
    with project_lock(base, directory):
        path = session_path(session_id, project_root, directory)
        current = read_stored(path, project_root)
        if data["revision"] != current["revision"]:
            raise StoreError(
                f"Stale revision: input={data['revision']}, current={current['revision']}. Read again before saving."
            )
        if "created_at" in data and data["created_at"] != current["created_at"]:
            raise StoreError("created_at is immutable and maintained by the helper.")
        data.update(created_at=current["created_at"], updated_at=timestamp(),
                    revision=current["revision"] + 1)
        write_atomic(path, data)
    return data


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "list", "read", "save"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--project", required=True, help="Existing project directory; canonicalized before storage.")
        sub.add_argument("--state-dir", help="Storage root; overrides TRIVY_PORTER_STATE_DIR and the default.")
        if command in {"create", "save"}:
            sub.add_argument("--from-file", required=True, help="JSON input file, or - for stdin.")
        if command in {"read", "save"}:
            sub.add_argument("--session", required=command == "save", help="ID returned by create.")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        project_root, base, directory = project_context(args.project, args.state_dir)
        if args.command == "create":
            result = create(args, project_root, base, directory)
        elif args.command == "list":
            result = [summary(data) for data in load_sessions(directory, project_root)]
        elif args.command == "read":
            result = read(args, project_root, directory)
        else:
            result = save(args, project_root, base, directory)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (StoreError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
