"""Exercise the terminal/chat handoff without scanning a real project."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "trivy-porter" / "scripts" / "trivy_porter.py"
STORE = ROOT / "trivy-porter" / "scripts" / "session_store.py"

HELP = """Scan a target

Usage:
  trivy {method} [flags] TARGET

Scan Flags:
      --scanners strings         scanners (allowed values: vuln,misconfig,secret,license) (default [vuln,secret])
      --skip-dirs strings        skip directories
      --ignore-unfixed           report only fixed vulnerabilities
      --exit-code int            exit code when findings exist
      --timeout duration         scan timeout (default 5m0s)
      --parallel int             parallel workers (default 5)
      --pkg-types strings        package types (allowed values: os,library) (default [os,library])
      --severity strings         severities (allowed values: UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL)
      --format string            format (allowed values: table,json,template,sarif) (default "table")
      --output string            output path
      --input string             input archive
      --token string             authentication token
      --password strings         registry password
      --username strings         registry username
      --download-db-only         update database without a scan
      --generate-default-config  write default config
      --config string            config path (default "trivy.yaml")
  -h, --help                     show help
  -v, --version                  show version
"""

TABLE = """Report Summary
┌───────────────────┬──────┬─────────────────┐
│ Target            │ Type │ Vulnerabilities │
├───────────────────┼──────┼─────────────────┤
│ package-lock.json │ npm  │ 1               │
└───────────────────┴──────┴─────────────────┘

package-lock.json (npm)
=======================
Total: 1 (UNKNOWN: 0, LOW: 0, MEDIUM: 0, HIGH: 1, CRITICAL: 0)
┌─────────┬────────────────┬──────────┬───────────────────┬───────────────┐
│ Library │ Vulnerability  │ Severity │ Installed Version │ Fixed Version │
├─────────┼────────────────┼──────────┼───────────────────┼───────────────┤
│ example │ CVE-2026-12345 │ HIGH     │ 1.0.0             │ 1.0.1         │
└─────────┴────────────────┴──────────┴───────────────────┴───────────────┘
"""


class TerminalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trivy-porter-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.state = self.root / "state"
        self.calls_file = self.root / "calls.jsonl"
        self.stdout_file = self.root / "scan.stdout"
        self.stderr_file = self.root / "scan.stderr"
        self.help_file = self.root / "help.txt"
        self.stdout_file.write_text(TABLE, encoding="utf-8")
        self.stderr_file.write_text("INFO scan completed\n", encoding="utf-8")
        self.help_file.write_text(HELP, encoding="utf-8")
        fake = self.bin / "trivy"
        fake.write_text(
            "#!" + sys.executable + "\n" + textwrap.dedent("""\
                import json
                import os
                from pathlib import Path
                import sys

                args = sys.argv[1:]
                with Path(os.environ['FAKE_TRIVY_CALLS']).open('a', encoding='utf-8') as out:
                    out.write(json.dumps({'args': args, 'cwd': os.getcwd()}) + '\\n')
                if args == ['--version']:
                    print('Version: 0.76.1')
                elif '--help' in args:
                    help_text = Path(os.environ['FAKE_TRIVY_HELP']).read_text(encoding='utf-8').replace('{method}', args[0])
                    if args[0] == 'fs':
                        help_text = '\\n'.join(line for line in help_text.splitlines() if '--input ' not in line)
                    print(help_text)
                else:
                    report = Path(os.environ['FAKE_TRIVY_STDOUT']).read_text(encoding='utf-8')
                    destination = None
                    for index, arg in enumerate(args):
                        if arg == '--output' and index + 1 < len(args):
                            destination = args[index + 1]
                        elif arg.startswith('--output='):
                            destination = arg.split('=', 1)[1]
                    if destination:
                        Path(destination).write_text(report, encoding='utf-8')
                    else:
                        sys.stdout.write(report)
                    sys.stderr.write(Path(os.environ['FAKE_TRIVY_STDERR']).read_text(encoding='utf-8'))
                    sys.exit(int(os.environ.get('FAKE_TRIVY_EXIT', '0')))
                """),
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        if os.name == "nt":
            (self.bin / "trivy.cmd").write_text(
                '@"' + sys.executable + '" "' + str(fake) + '" %*\r\n', encoding="utf-8")
        # Do not inherit developer Trivy filters or credentials into this fixture.
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("TRIVY_") and not key.startswith("FAKE_TRIVY_")}
        self.env.update({
            "PATH": str(self.bin) + os.pathsep + self.env.get("PATH", ""),
            "TRIVY_PORTER_STATE_DIR": str(self.state),
            "FAKE_TRIVY_CALLS": str(self.calls_file),
            "FAKE_TRIVY_STDOUT": str(self.stdout_file),
            "FAKE_TRIVY_STDERR": str(self.stderr_file),
            "FAKE_TRIVY_HELP": str(self.help_file),
            "PYTHONDONTWRITEBYTECODE": "1",
        })

    def run_cli(self, answers="", *arguments, project=None, expected=0):
        result = subprocess.run(
            [sys.executable, str(CLI), *arguments, "--project", str(project or self.project)],
            input=answers, text=True, capture_output=True, env=self.env,
            cwd=self.project, timeout=15,
        )
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def calls(self, scans_only=False):
        if not self.calls_file.exists():
            return []
        calls = [json.loads(line) for line in self.calls_file.read_text(encoding="utf-8").splitlines()]
        if scans_only:
            calls = [item for item in calls if item["args"] != ["--version"] and "--help" not in item["args"]]
        return calls

    def sessions(self, project=None):
        project = str((project or self.project).resolve())
        directory = self.state / hashlib.sha256(project.encode("utf-8")).hexdigest()
        return [json.loads(file.read_text(encoding="utf-8")) for file in sorted(directory.glob("*.json"))]

    def only_session(self):
        sessions = self.sessions()
        self.assertEqual(len(sessions), 1)
        return sessions[0]

    def assert_chat_handoff(self, output, action, session_id):
        arguments = [action, session_id, "--project", str(self.project.resolve()),
                     "--state-dir", str(self.state.resolve())]
        expected = "$trivy-porter " + (subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments))
        commands = [line for line in output.splitlines() if line.startswith("$trivy-porter ")]
        self.assertEqual(commands, [expected])
        if os.name != "nt":
            self.assertEqual(shlex.split(commands[0]), ["$trivy-porter", *arguments])

    def create_session(self, stage, **fields):
        payload = {
            "stage": stage, "pending_question": None, "origin": "terminal",
            "scan": {"method": "fs", "target": ".", "cwd": str(self.project.resolve()),
                     "argv_redacted": ["trivy", "fs", "."], "severity": "ALL",
                     "explicit_flags": [], "last_scan_complete": True},
            "findings": [], "batches": [], "baseline": {}, "last_report": None, **fields,
        }
        result = subprocess.run(
            [sys.executable, str(STORE), "create", "--project", str(self.project), "--from-file", "-"],
            input=json.dumps(payload), text=True, capture_output=True, env=self.env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_default_scan_preserves_exact_arguments_and_hands_off(self):
        result = self.run_cli("\n\n\n")
        self.assertEqual(self.calls(scans_only=True), [{"args": ["fs", "."], "cwd": str(self.project.resolve())}])
        session = self.only_session()
        self.assertEqual(session["stage"], "awaiting_analysis")
        self.assertEqual(session["scan"]["argv_redacted"], ["trivy", "fs", "."])
        self.assertIsNone(session["scan"]["last_scan_complete"])
        self.assertEqual(session["scan"]["result"]["exit_code"], 0)
        self.assert_chat_handoff(result.stdout, "analyze", session["session_id"])
        for name in ("stdout_path", "stderr_path"):
            artifact = Path(session["scan"]["result"][name])
            self.assertTrue(artifact.is_file())
            self.assertTrue(artifact.resolve().is_relative_to(self.state.resolve()))
            self.assertFalse(artifact.resolve().is_relative_to(self.project.resolve()))
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)
        output = Path(session["scan"]["result"]["stdout_path"]).read_text(encoding="utf-8")
        self.assertIn("CVE-2026-12345", output)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_nonzero_scan_is_preserved_for_agent_interpretation(self):
        self.env["FAKE_TRIVY_EXIT"] = "7"
        self.run_cli("\n\n\n", expected=None)
        session = self.only_session()
        self.assertEqual(session["stage"], "awaiting_analysis")
        self.assertEqual(session["scan"]["result"]["exit_code"], 7)
        self.assertIsNone(session["scan"]["last_scan_complete"])

    def test_continue_after_scan_does_not_rescan_or_choose_batch(self):
        self.run_cli("\n\n\n")
        before = self.only_session()
        calls = self.calls(scans_only=True)
        result = self.run_cli("", "continue", "--session", before["session_id"])
        self.assertEqual(self.calls(scans_only=True), calls)
        after = self.only_session()
        self.assertEqual(after["stage"], "awaiting_analysis")
        self.assertIsNone(after.get("batch_request"))
        self.assert_chat_handoff(result.stdout, "analyze", before["session_id"])

    def test_saved_table_artifacts_do_not_contain_secret_source(self):
        marker = "PRIVATE_FIXTURE_SECRET_123456789"
        self.stdout_file.write_text(TABLE + "\nsettings.env (secrets)\n"
                                    "======================\nTotal: 1 (HIGH: 1)\n"
                                    "HIGH: generic-api-key (Generic API Key)\n"
                                    "settings.env:11\n11 [ API_KEY=" + marker + "\n",
                                    encoding="utf-8")
        self.run_cli("\n\n\n")
        session = self.only_session()
        self.assertNotIn(marker, json.dumps(session))
        for name in ("stdout_path", "stderr_path"):
            self.assertNotIn(marker, Path(session["scan"]["result"][name]).read_text(encoding="utf-8"))

    def test_eof_never_submits_a_default_or_starts_scan(self):
        self.run_cli("", expected=None)
        self.assertEqual(self.calls(scans_only=True), [])
        for session in self.sessions():
            self.assertEqual(session["stage"], "configuring")
            self.assertIsNone(session.get("batch_request"))

    def test_severity_selection_is_exact_not_cumulative(self):
        self.run_cli("\n\n3\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--severity", "HIGH", "."])

    def test_image_reference_metacharacters_are_literal(self):
        image = "repo/image:tag; touch SHOULD_NOT_EXIST"
        self.run_cli("2\n\n" + image + "\n\n\n")
        args = self.calls(scans_only=True)[0]["args"]
        self.assertEqual(args, ["image", image])
        self.assertFalse((self.project / "SHOULD_NOT_EXIST").exists())

    def test_image_archive_requires_no_dummy_image_reference(self):
        archive = self.project / "local image.tar"
        archive.write_bytes(b"fake fixture archive")
        self.run_cli("2\n2\n" + str(archive) + "\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["image", "--input", str(archive.resolve())])

    def test_scanners_menu_keeps_explicit_multiple_choices(self):
        self.run_cli("\n--scanners\n1,2\n2,4,2\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--scanners=vuln,secret", "."])
        self.assertEqual(self.only_session()["scan"]["explicit_flags"],
                         [{"name": "scanners", "value": "vuln,secret"}])

    def test_flag_names_and_values_come_from_current_method_help(self):
        custom_help = HELP.replace("vuln,misconfig,secret,license", "vuln,secret,future-scanner")
        custom_help += "      --future-mode string       new mode (allowed values: narrow,wide)\n"
        self.help_file.write_text(custom_help, encoding="utf-8")
        self.run_cli("\n--scanners\nfuture-scanner\n--future-mode\nwide\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"],
                         ["fs", "--scanners=future-scanner", "--future-mode=wide", "."])

    def test_multiline_allowed_values_are_discovered(self):
        custom_help = HELP.replace(
            "scanners (allowed values: vuln,misconfig,secret,license) (default [vuln,secret])",
            "scanners\n                                    Allowed values:\n"
            "                                      - vuln\n                                      - secret\n"
            "                                      - future-scanner\n                                     (default [vuln,secret])",
        )
        self.help_file.write_text(custom_help, encoding="utf-8")
        self.run_cli("\n--scanners\n2,4\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"],
                         ["fs", "--scanners=vuln,future-scanner", "."])

    def test_custom_string_value_is_one_literal_argument(self):
        value = "cache $(touch SHOULD_NOT_EXIST); & another folder"
        self.run_cli("\n--skip-dirs\n2\n" + value + "\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--skip-dirs=" + value, "."])
        self.assertFalse((self.project / "SHOULD_NOT_EXIST").exists())

    def test_boolean_false_remains_an_explicit_override(self):
        self.run_cli("\n--ignore-unfixed\n3\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--ignore-unfixed=false", "."])

    def test_integer_and_duration_values_are_validated_before_scan(self):
        self.run_cli("\n--parallel\n2\n1.5\n3\n--timeout\n2\n1x\n1m30s\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"],
                         ["fs", "--parallel=3", "--timeout=1m30s", "."])

    def test_default_flag_value_omits_only_that_flag(self):
        self.run_cli("\n--ignore-unfixed\n2\n--scanners\n1\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--ignore-unfixed=true", "."])

    def test_reset_custom_flags_preserves_explicit_archive_target(self):
        archive = self.project / "image.tar"
        archive.write_bytes(b"fixture archive")
        self.run_cli("2\n2\n" + str(archive) + "\n--scanners\n2\nr\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["image", "--input", str(archive.resolve())])

    def test_non_scan_credential_and_other_method_flags_do_not_execute(self):
        self.run_cli("\n--download-db-only\n--generate-default-config\n--help\n--version\n"
                     "--password\n--token\n--input\n--not-a-real-flag\n--severity\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "."])

    def test_flag_value_checkpoint_resumes_without_reasking_method(self):
        self.run_cli("\n--skip-dirs\n", expected=130)
        session = self.only_session()
        self.assertEqual(session["pending_question"], "flag_value")
        self.assertEqual(session["pending_flag"], "skip-dirs")
        self.assertEqual(self.calls(scans_only=True), [])
        self.run_cli("2\nnode_modules\n\n\n", "continue", "--session", session["session_id"])
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--skip-dirs=node_modules", "."])
        self.assertEqual(self.only_session()["stage"], "awaiting_analysis")

    def test_severity_checkpoint_resumes_without_reasking_flags(self):
        self.run_cli("\n\n", expected=130)
        session = self.only_session()
        self.assertEqual(session["pending_question"], "severity")
        self.run_cli("3\n", "continue", "--session", session["session_id"])
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--severity", "HIGH", "."])

    def test_inherited_config_requires_answer_and_is_not_overridden(self):
        config = self.project / "trivy.yaml"
        original = "severity:\n  - HIGH\nignore-unfixed: true\n"
        config.write_text(original, encoding="utf-8")
        self.run_cli("\n\n\n", expected=130)
        session = self.only_session()
        self.assertEqual(session["pending_question"], "scan")
        self.assertEqual(self.calls(scans_only=True), [])
        self.run_cli("\n", "continue", "--session", session["session_id"])
        updated = self.only_session()
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "."])
        self.assertTrue(updated["scan"]["inherited_settings"]["requires_agent_review"])
        self.assertIn(str(config.resolve()), updated["scan"]["configuration_fingerprint"])
        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def write_json_report(self, title="An example vulnerability"):
        marker = "PRIVATE_FIXTURE_SECRET_123456789"
        data = {
            "SchemaVersion": 2, "ArtifactName": "local-image:tag", "ArtifactType": "container_image",
            "Metadata": {"ImageConfig": {"Config": {"Env": ["PASSWORD=" + marker]}}},
            "Results": [{"Target": "fixture", "Class": "lang-pkgs", "Type": "npm",
                         "Vulnerabilities": [{"VulnerabilityID": "CVE-2026-12345", "PkgName": "example",
                                              "InstalledVersion": "1.0.0", "FixedVersion": "1.0.1",
                                              "Severity": "HIGH", "Title": title}],
                         "Secrets": [{"RuleID": "generic-api-key", "Severity": "HIGH", "Title": "API Key",
                                      "StartLine": 11, "EndLine": 11, "Match": marker,
                                      "Code": {"Lines": [{"Number": 11, "Content": "API_KEY=" + marker}]}}]}],
        }
        self.stdout_file.write_text(json.dumps(data), encoding="utf-8")
        return marker

    def test_json_redaction_preserves_findings_and_omits_secret_source_and_metadata(self):
        marker = self.write_json_report()
        self.run_cli("\n--format\njson\n\n\n")
        session = self.only_session()
        raw = Path(session["scan"]["result"]["stdout_path"]).read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertNotIn(marker, raw + json.dumps(session))
        self.assertNotIn("Metadata", data)
        finding = data["Results"][0]
        self.assertEqual(finding["Vulnerabilities"][0]["VulnerabilityID"], "CVE-2026-12345")
        self.assertEqual(finding["Secrets"][0]["RuleID"], "generic-api-key")
        self.assertNotIn("Match", finding["Secrets"][0])
        self.assertNotIn("Code", finding["Secrets"][0])

    def test_quoted_secret_values_with_spaces_are_fully_removed(self):
        marker = "PRIVATE_FIXTURE_SUFFIX_123456789"
        self.stdout_file.write_text(TABLE + '\npassword="first ' + marker + '"\n', encoding="utf-8")
        result = self.run_cli("\n\n\n")
        artifact = Path(self.only_session()["scan"]["result"]["stdout_path"]).read_text(encoding="utf-8")
        self.assertNotIn(marker, artifact + result.stdout)

    def test_terminal_escape_payloads_are_not_saved_or_printed(self):
        marker = "U0FGRV9NQVJLRVI="
        self.stdout_file.write_text(TABLE + "\n\x1b]52;c;" + marker + "\x07\n", encoding="utf-8")
        result = self.run_cli("\n\n\n")
        artifact = Path(self.only_session()["scan"]["result"]["stdout_path"]).read_text(encoding="utf-8")
        self.assertNotIn(marker, artifact + result.stdout)
        self.assertNotIn("\x1b", artifact + result.stdout)

    def test_inherited_custom_output_cannot_spoof_a_table(self):
        marker = "PRIVATE_FIXTURE_BARE_SECRET_123456789"
        (self.project / "trivy.yaml").write_text("format: template\n", encoding="utf-8")
        self.stdout_file.write_text("Report Summary\n" + marker + "\n", encoding="utf-8")
        result = self.run_cli("\n\n\n\n")
        scan = self.only_session()["scan"]
        self.assertEqual(scan["result"]["format"], "inherited")
        artifact = Path(scan["result"]["stdout_path"]).read_text(encoding="utf-8")
        self.assertNotIn(marker, artifact + result.stdout)
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "."])

    def test_inherited_settings_can_return_to_explicit_format_choice(self):
        (self.project / "trivy.yaml").write_text("format: template\n", encoding="utf-8")
        self.run_cli("\n\n\n2\n--format\ntable\n\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], ["fs", "--format=table", "."])
        self.assertEqual(self.only_session()["scan"]["result"]["format"], "table")

    def test_credential_environment_values_are_not_persisted(self):
        marker = "PRIVATE_REGISTRY_PASSWORD_FIXTURE"
        self.env["TRIVY_PASSWORD"] = marker
        self.stderr_file.write_text("INFO request password=" + marker + "\n", encoding="utf-8")
        self.run_cli("\n\n\n")
        session = self.only_session()
        self.assertNotIn(marker, json.dumps(session))
        for name in ("stdout_path", "stderr_path"):
            self.assertNotIn(marker, Path(session["scan"]["result"][name]).read_text(encoding="utf-8"))

    def test_json_redaction_does_not_break_json_when_scrubbing_string_value(self):
        marker = self.write_json_report(title="token=PRIVATE_FIXTURE_SECRET_123456789")
        self.run_cli("\n--format\njson\n\n\n")
        session = self.only_session()
        raw = Path(session["scan"]["result"]["stdout_path"]).read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertNotIn(marker, raw)
        self.assertEqual(data["Results"][0]["Vulnerabilities"][0]["VulnerabilityID"], "CVE-2026-12345")

    def test_explicit_output_file_is_used_as_report_source(self):
        marker = self.write_json_report()
        self.run_cli("\n--format\njson\n--output\n2\nscan result.json\n\n\n")
        session = self.only_session()
        self.assertEqual(self.calls(scans_only=True)[0]["args"],
                         ["fs", "--format=json", "--output=scan result.json", "."])
        self.assertEqual(session["scan"]["result"]["source"], str((self.project / "scan result.json").resolve()))
        raw = Path(session["scan"]["result"]["stdout_path"]).read_text(encoding="utf-8")
        self.assertNotIn(marker, raw)
        self.assertIn("CVE-2026-12345", raw)

    def test_batch_count_is_positive_integer_with_fresh_request(self):
        session = self.create_session("awaiting_batch", findings=[{"id": "F001", "status": "pending"}])
        result = self.run_cli("0\n-1\n1.5\nwat\n3\n", "continue", "--session", session["session_id"])
        updated = self.only_session()
        request = updated["batch_request"]
        self.assertEqual(request["count"], 3)
        self.assertEqual(request["status"], "pending")
        self.assertTrue(request["id"])
        self.assertTrue(request["submitted_at"])
        self.assertEqual(self.calls(scans_only=True), [])
        self.assertEqual(list(self.project.iterdir()), [])
        self.assert_chat_handoff(result.stdout, "continue", session["session_id"])

    def test_enter_submits_one_finding(self):
        session = self.create_session("awaiting_batch", findings=[{"id": "F001", "status": "pending"}])
        self.run_cli("\n", "continue", "--session", session["session_id"])
        self.assertEqual(self.only_session()["batch_request"]["count"], 1)

    def test_eof_at_batch_question_does_not_submit_one(self):
        session = self.create_session("awaiting_batch", findings=[{"id": "F001", "status": "pending"}])
        self.run_cli("", "continue", "--session", session["session_id"], expected=130)
        self.assertIsNone(self.only_session().get("batch_request"))

    def test_existing_pending_request_is_not_replaced_or_reused(self):
        session = self.create_session(
            "awaiting_batch", findings=[{"id": "F001", "status": "pending"}],
            batch_request={"id": "saved-request", "count": 2, "submitted_at": "2026-10-22T00:00:00Z", "status": "pending"},
        )
        result = self.run_cli("9\n", "continue", "--session", session["session_id"])
        self.assertEqual(self.only_session()["batch_request"], session["batch_request"])
        self.assert_chat_handoff(result.stdout, "continue", session["session_id"])

    def test_consumed_request_needs_fresh_number_after_report(self):
        session = self.create_session(
            "paused", findings=[{"id": "F002", "status": "pending"}],
            batches=[{"git_preparation": {"status": "generated", "generation_status": "generated"}}],
            batch_request={"id": "old-request", "count": 8, "submitted_at": "2026-10-22T00:00:00Z", "status": "consumed"},
        )
        self.run_cli("2\n", "continue", "--session", session["session_id"])
        request = self.only_session()["batch_request"]
        self.assertEqual(request["count"], 2)
        self.assertEqual(request["status"], "pending")
        self.assertNotEqual(request["id"], "old-request")

    def test_interrupted_batch_and_pending_git_never_get_new_count(self):
        for stage, git in (("batch_in_progress", {}), ("paused", {"status": "blocked", "generation_status": "blocked"})):
            with self.subTest(stage=stage):
                session = self.create_session(
                    stage, findings=[{"id": "F001", "status": "in_progress"}],
                    batches=[{"git_preparation": git}],
                )
                result = self.run_cli("7\n", "continue", "--session", session["session_id"])
                updated = next(item for item in self.sessions() if item["session_id"] == session["session_id"])
                self.assertIsNone(updated.get("batch_request"))
                self.assert_chat_handoff(result.stdout, "continue", session["session_id"])

    def test_pending_git_substep_or_generation_blocker_prevents_new_batch(self):
        for git in ({"status": "generated", "pending_substep": "staging"},
                    {"status": "generated", "generation_status": "blocked"}):
            with self.subTest(git=git):
                session = self.create_session(
                    "paused", findings=[{"id": "F002", "status": "pending"}],
                    batches=[{"git_preparation": git}],
                )
                self.run_cli("4\n", "continue", "--session", session["session_id"])
                updated = next(item for item in self.sessions() if item["session_id"] == session["session_id"])
                self.assertIsNone(updated.get("batch_request"))

    def test_complete_session_never_creates_request(self):
        session = self.create_session("complete")
        self.run_cli("6\n", "continue", "--session", session["session_id"])
        self.assertIsNone(self.only_session().get("batch_request"))

    def test_ambiguous_sessions_require_an_actual_choice(self):
        self.create_session("awaiting_batch", findings=[{"id": "F001", "status": "pending"}])
        self.create_session("awaiting_batch", findings=[{"id": "F002", "status": "pending"}])
        self.run_cli("", "continue", expected=None)
        self.assertTrue(all(item.get("batch_request") is None for item in self.sessions()))
        self.assertEqual(self.calls(scans_only=True), [])

    def test_session_cannot_be_loaded_from_a_different_project(self):
        session = self.create_session("awaiting_batch", findings=[{"id": "F001", "status": "pending"}])
        other = self.root / "other-project"
        other.mkdir()
        self.run_cli("2\n", "continue", "--session", session["session_id"], project=other, expected=None)
        self.assertIsNone(self.only_session().get("batch_request"))
        self.assertEqual(self.sessions(other), [])

    def test_session_store_rejects_stale_revision(self):
        session = self.create_session("awaiting_batch")
        args = [sys.executable, str(STORE), "save", "--project", str(self.project),
                "--session", session["session_id"], "--from-file", "-"]
        first = subprocess.run(args, input=json.dumps(session), text=True, capture_output=True, env=self.env, timeout=10)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = subprocess.run(args, input=json.dumps(session), text=True, capture_output=True, env=self.env, timeout=10)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(self.only_session()["revision"], session["revision"] + 1)


if __name__ == "__main__":
    unittest.main()
