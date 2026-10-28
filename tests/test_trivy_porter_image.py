"""Build and scan fixture images without Docker, Trivy, or network access."""

from contextlib import redirect_stdout
import importlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import textwrap
import unittest
from unittest import mock

import test_trivy_porter as fixtures


# Windows hosts build with Docker's default platform; other hosts pin linux/amd64.
BUILD_PLATFORM = [] if os.name == "nt" else ["--platform=linux/amd64"]


class LocalImageWorkflowTests(unittest.TestCase):
    fixture_setup = fixtures.TerminalIntegrationTests.setUp
    run_cli = fixtures.TerminalIntegrationTests.run_cli
    calls = fixtures.TerminalIntegrationTests.calls
    sessions = fixtures.TerminalIntegrationTests.sessions
    only_session = fixtures.TerminalIntegrationTests.only_session
    write_json_report = fixtures.TerminalIntegrationTests.write_json_report
    assert_chat_handoff = fixtures.TerminalIntegrationTests.assert_chat_handoff

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(fixtures.CLI.parent))
        try:
            cls.cli = importlib.import_module("trivy_porter")
        finally:
            sys.path.pop(0)

    def setUp(self):
        self.fixture_setup()
        self.write_json_report()
        self.docker_calls_file = self.root / "docker.jsonl"
        self.events_file = self.root / "workflow.jsonl"
        self.env.update({
            "FAKE_DOCKER_CALLS": str(self.docker_calls_file),
            "FAKE_WORKFLOW_EVENTS": str(self.events_file),
        })
        self.docker = self.bin / "docker"
        self.docker.write_text("#!" + sys.executable + "\n" + textwrap.dedent("""\
            import json
            import os
            from pathlib import Path
            import sys

            args = sys.argv[1:]
            call = {'args': args, 'cwd': os.getcwd()}
            with Path(os.environ['FAKE_DOCKER_CALLS']).open('a', encoding='utf-8') as out:
                out.write(json.dumps(call) + '\\n')
            with Path(os.environ['FAKE_WORKFLOW_EVENTS']).open('a', encoding='utf-8') as out:
                out.write(json.dumps(dict(call, tool='docker')) + '\\n')
            if args and args[0] == 'build':
                print('Fixture Docker build')
                print('INFO fixture build log', file=sys.stderr)
                sys.exit(int(os.environ.get('FAKE_DOCKER_EXIT', '0')))
            print('sha256:' + 'b' * 64)
            """), encoding="utf-8")
        self.docker.chmod(self.docker.stat().st_mode | stat.S_IXUSR)
        if os.name == "nt":
            (self.bin / "docker.cmd").write_text(
                '@"' + sys.executable + '" "' + str(self.docker) + '" %*\r\n', encoding="utf-8")

    def docker_calls(self):
        if not self.docker_calls_file.exists():
            return []
        return [json.loads(line) for line in self.docker_calls_file.read_text(encoding="utf-8").splitlines()]

    def builds(self):
        return [call for call in self.docker_calls() if call["args"][0] == "build"]

    def test_image_selection_builds_local_amd64_then_scans_only_docker_as_json(self):
        result = self.run_cli("2\n\n\n")
        self.assertEqual(self.builds(), [{
            "args": ["build", *BUILD_PLATFORM, "-t", "project-with-spaces:scan", "."],
            "cwd": str(self.project.resolve()),
        }])
        scan_call = self.calls(scans_only=True)
        self.assertEqual(scan_call, [{
            "args": ["image", "--image-src", "docker", "--format", "json", "project-with-spaces:scan"],
            "cwd": str(self.project.resolve()),
        }])
        events = [json.loads(line) for line in self.events_file.read_text(encoding="utf-8").splitlines()]
        relevant = [event["tool"] for event in events
                    if event["args"][0] == "build" or
                    (event["tool"] == "trivy" and event["args"][0] == "image" and "--help" not in event["args"])]
        self.assertEqual(relevant, ["docker", "trivy"])
        data = self.only_session()
        scan = data["scan"]
        self.assertEqual(data["stage"], "awaiting_analysis")
        self.assertEqual(scan["build"]["platform"], None if os.name == "nt" else "linux/amd64")
        self.assertEqual(scan["build"]["context"], str(self.project.resolve()))
        self.assertEqual(scan["build"]["result"]["exit_code"], 0)
        report = Path(scan["result"]["stdout_path"])
        self.assertEqual(report.name, "report.json")
        self.assertEqual(report.parent.parent, self.state.resolve())
        self.assertRegex(report.parent.name, r"^\d{8}-\d{4}-image(?:-\d+)?$")
        self.assertNotIn(data["session_id"], report.parent.name)
        self.assertTrue((report.parent / "session.json").is_file())
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["Results"][0]
                         ["Vulnerabilities"][0]["VulnerabilityID"], "CVE-2026-12345")
        self.assert_chat_handoff(result.stdout, "analyze", data["session_id"])

    def test_build_pins_amd64_except_on_windows(self):
        posix, windows = {}, {}
        self.cli.configure_local_image(posix, "app", windows=False)
        self.cli.configure_local_image(windows, "app", windows=True)
        self.assertEqual(posix["build"]["platform"], "linux/amd64")
        self.assertEqual(posix["build"]["argv_redacted"], ["docker", "build", "--platform=linux/amd64", "-t", "app:scan", "."])
        self.assertIsNone(windows["build"]["platform"])
        self.assertEqual(windows["build"]["argv_redacted"], ["docker", "build", "-t", "app:scan", "."])

    def test_local_image_preserves_scanner_and_severity_choices(self):
        self.run_cli("2\n--scanners\nvuln,secret\n\n3\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], [
            "image", "--image-src", "docker", "--format", "json", "--scanners=vuln,secret",
            "--severity", "HIGH", "project-with-spaces:scan",
        ])

    def test_required_image_source_and_json_format_cannot_be_changed_in_menu(self):
        self.run_cli("2\n--input\n--image-src\n--format\n--output\n--template\nr\n\n\n")
        self.assertEqual(self.calls(scans_only=True)[0]["args"], [
            "image", "--image-src", "docker", "--format", "json", "project-with-spaces:scan",
        ])
        self.assertEqual(self.only_session()["scan"]["target_kind"], "local_build")
        self.assertEqual(len(self.builds()), 1)

    def test_failed_build_blocks_scan_and_can_be_retried(self):
        self.env["FAKE_DOCKER_EXIT"] = "17"
        failed = self.run_cli("2\n\n\n", expected=None)
        self.assertNotEqual(failed.returncode, 0)
        data = self.only_session()
        self.assertEqual(data["stage"], "scan_failed")
        self.assertEqual(data["scan"]["build"]["result"]["exit_code"], 17)
        self.assertFalse(data["scan"].get("result"))
        self.assertEqual(self.calls(scans_only=True), [])
        self.assertEqual(list(self.state.glob("*/report.json")), [])
        self.env["FAKE_DOCKER_EXIT"] = "0"
        self.run_cli("\n", "continue", "--session", data["session_id"])
        self.assertEqual(len(self.builds()), 2)
        self.assertEqual(len(self.calls(scans_only=True)), 1)
        self.assertEqual(self.only_session()["stage"], "awaiting_analysis")

    def test_missing_docker_does_not_fall_back_to_remote_scan(self):
        self.docker.unlink()
        (self.bin / "docker.cmd").unlink(missing_ok=True)
        self.env["PATH"] = str(self.bin)
        result = self.run_cli("2\n\n\n", expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Docker", result.stdout + result.stderr)
        self.assertEqual(self.calls(scans_only=True), [])
        self.assertEqual(self.builds(), [])

    def test_failed_or_interrupted_build_removes_stale_report_and_scan_evidence(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            session = self.cli.Session(str(self.project), new=True, state_dir=str(self.state), method="image")
            previous_report = session.artifact_directory / "report.json"
            for exit_code, interrupted, expected in ((17, False, 17), (-2, True, 130)):
                with self.subTest(interrupted=interrupted):
                    previous_report.write_text('{"Results": []}', encoding="utf-8")
                    session.data["scan"]["result"] = {"stdout_path": str(previous_report), "exit_code": 0}
                    session.data["scan"]["last_scan_exit_code"] = 0
                    session.save()
                    with mock.patch.object(self.cli, "capture_process", return_value=(
                            ["", "ERROR incomplete fixture build\n"], exit_code, interrupted,
                            [False, False])) as capture:
                        with redirect_stdout(io.StringIO()):
                            result = self.cli.run_local_build(session)
                    self.assertEqual(result, expected)
                    self.assertEqual(capture.call_count, 1)
                    saved = self.only_session()
                    self.assertEqual(saved["stage"], "scan_failed")
                    self.assertEqual(saved["pending_question"], "build")
                    self.assertEqual(saved["scan"]["build"]["status"], "interrupted" if interrupted else "failed")
                    self.assertEqual(saved["scan"]["build"]["result"]["interrupted"], interrupted)
                    self.assertNotIn("result", saved["scan"])
                    self.assertNotIn("last_scan_exit_code", saved["scan"])
                    self.assertFalse(previous_report.exists())
                    self.assertEqual(self.calls(scans_only=True), [])
                    downloads = self.root / "old report download"
                    exported = self.run_cli("", "-d", "--download-dir", str(downloads), expected=None)
                    self.assertNotEqual(exported.returncode, 0)
                    self.assertFalse(list(downloads.glob("*.json")))

    def test_inherited_output_and_source_cannot_redirect_the_local_json_report(self):
        redirect = self.project / "unexpected-output.json"
        self.env.update(TRIVY_OUTPUT=str(redirect), TRIVY_FORMAT="template", TRIVY_INPUT="wrong.tar",
                        TRIVY_IMAGE_SRC="remote")
        self.run_cli("2\n\n\n\n")
        args = self.calls(scans_only=True)[0]["args"]
        self.assertEqual(args[1:5], ["--image-src", "docker", "--format", "json"])
        self.assertIn("--input=", args)
        self.assertIn("--output=", args)
        self.assertFalse(redirect.exists())
        data = self.only_session()
        self.assertEqual(data["scan"]["result"]["format"], "json")
        self.assertEqual(Path(data["scan"]["result"]["stdout_path"]).name, "report.json")

    def test_invalid_json_is_not_presented_as_a_valid_image_report(self):
        self.stdout_file.write_text("not a Trivy JSON report", encoding="utf-8")
        result = self.run_cli("2\n\n\n", expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.only_session()["stage"], "scan_failed")
        self.assertEqual(list(self.state.glob("*/report.json")), [])

    def test_nonfinite_numbers_are_rejected_without_creating_json_reports(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                before = {data["session_id"] for data in self.sessions()}
                self.stdout_file.write_text('{"Results": [], "SchemaVersion": ' + constant + '}', encoding="utf-8")
                result = self.run_cli("2\n\n\n", expected=None)
                self.assertNotEqual(result.returncode, 0)
                created = [data for data in self.sessions() if data["session_id"] not in before]
                self.assertEqual(len(created), 1)
                self.assertEqual(created[0]["stage"], "scan_failed")
                self.assertEqual(list(self.state.glob("*/report.json")), [])

    def test_truncated_json_is_not_presented_as_a_complete_report(self):
        self.stdout_file.write_text('{"Results": [], "padding": "' + "x" * (4 * 1024 * 1024) + '"}', encoding="utf-8")
        result = self.run_cli("2\n\n\n", expected=None)
        self.assertNotEqual(result.returncode, 0)
        data = self.only_session()
        self.assertEqual(data["stage"], "scan_failed")
        self.assertTrue(data["scan"]["result"]["truncated"])
        self.assertEqual(list(self.state.glob("*/report.json")), [])

    def test_sanitized_json_exports_without_building_or_rescanning(self):
        marker = self.write_json_report()
        self.run_cli("2\n\n\n")
        data = self.only_session()
        contents = Path(data["scan"]["result"]["stdout_path"]).read_text(encoding="utf-8")
        self.assertNotIn(marker, contents + json.dumps(data))
        report = json.loads(contents)
        self.assertNotIn("Metadata", report)
        secret = report["Results"][0]["Secrets"][0]
        self.assertNotIn("Match", secret)
        self.assertNotIn("Code", secret)
        before = self.calls(), self.docker_calls()
        downloads = self.root / "download folder"
        self.run_cli("", "-d", "--download-dir", str(downloads))
        exported = list(downloads.glob("*.json"))
        self.assertEqual(len(exported), 1)
        raw = exported[0].read_text(encoding="utf-8")
        payload = json.loads(raw)
        self.assertEqual(payload["session"]["session_id"], data["session_id"])
        self.assertNotIn(marker, raw)
        self.assertIn("CVE-2026-12345", raw)
        self.assertEqual((self.calls(), self.docker_calls()), before)

    def test_project_name_metacharacters_are_normalized_without_shell_execution(self):
        project = self.root / "UPPER App;$(touch SHOULD_NOT_EXIST)"
        project.mkdir()
        self.run_cli("2\n\n\n", project=project)
        build = self.builds()[0]
        self.assertEqual(build["cwd"], str(project.resolve()))
        tag = build["args"][build["args"].index("-t") + 1]
        self.assertRegex(tag, r"^[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*:scan$")
        self.assertEqual(self.calls(scans_only=True)[0]["args"][-1], tag)
        self.assertFalse((project / "SHOULD_NOT_EXIST").exists())
        self.assertFalse((self.project / "SHOULD_NOT_EXIST").exists())

    def test_docker_valid_periods_and_underscores_in_project_name_are_preserved(self):
        project = self.root / "my.app_service"
        project.mkdir()
        self.run_cli("2\n\n\n", project=project)
        self.assertEqual(self.builds()[0]["args"], [
            "build", *BUILD_PLATFORM, "-t", "my.app_service:scan", ".",
        ])
        self.assertEqual(self.calls(scans_only=True)[0]["args"][-1], "my.app_service:scan")


if __name__ == "__main__":
    unittest.main()
