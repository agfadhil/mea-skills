"""Exercise explicit local cleanup and portable reports using temporary files."""

import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import test_trivy_porter as scan_tests


CLI = scan_tests.CLI
STORE = scan_tests.STORE


class QuickCommandsIntegrationTests(unittest.TestCase):
    setUp = scan_tests.TerminalIntegrationTests.setUp
    run_cli = scan_tests.TerminalIntegrationTests.run_cli
    calls = scan_tests.TerminalIntegrationTests.calls
    create_session = scan_tests.TerminalIntegrationTests.create_session

    def directory(self, state=None, project=None):
        project_root = str((project or self.project).resolve())
        return (state or self.state) / hashlib.sha256(project_root.encode("utf-8")).hexdigest()

    def save(self, session, state=None, project=None):
        result = subprocess.run(
            [sys.executable, str(STORE), "save", "--project", str(project or self.project),
             "--state-dir", str(state or self.state), "--session", session["session_id"], "--from-file", "-"],
            input=json.dumps(session), text=True, capture_output=True, env=self.env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def report_session(self, state=None, **fields):
        selected_state = state or self.state
        with patch.dict(self.env, {"TRIVY_PORTER_STATE_DIR": str(selected_state)}):
            session = self.create_session("awaiting_analysis", **fields)
        partition = self.directory(state=selected_state)
        prefix = session["session_id"] + "." + "a" * 32
        stdout = partition / (prefix + ".stdout.txt")
        stderr = partition / (prefix + ".stderr.txt")
        stdout.write_text(scan_tests.TABLE, encoding="utf-8")
        stderr.write_text("INFO fixture scan completed\n", encoding="utf-8")
        session["scan"]["result"] = {
            "stdout_path": str(stdout.resolve()), "stderr_path": str(stderr.resolve()),
            "exit_code": 0, "interrupted": False, "truncated": False,
            "format": "table", "source": "stdout", "sanitized": True,
        }
        session["scan"]["last_scan_complete"] = None
        return self.save(session, state=selected_state)

    def exported(self, directory):
        files = sorted(directory.glob("trivy-porter-report-*.json"))
        self.assertEqual(len(files), 1)
        return files[0], json.loads(files[0].read_text(encoding="utf-8"))

    def test_clean_removes_the_entire_local_folder_without_a_prompt(self):
        local = self.project / ".trivy-porter"
        session = self.report_session(state=local)
        (local / "unknown" / "nested").mkdir(parents=True)
        (local / "unknown" / "nested" / "notes.txt").write_text("delete this too", encoding="utf-8")
        (local / "foreign.json").write_text("not session metadata", encoding="utf-8")
        application = self.project / "application.txt"
        application.write_text("keep application", encoding="utf-8")
        raw_output = self.project / "chosen raw output.json"
        raw_output.write_text("keep raw output", encoding="utf-8")
        # The flag deliberately targets local storage, even with an env override.
        external = self.report_session()
        result = self.run_cli("", "--clean")
        self.assertFalse(local.exists())
        self.assertEqual(application.read_text(encoding="utf-8"), "keep application")
        self.assertEqual(raw_output.read_text(encoding="utf-8"), "keep raw output")
        self.assertTrue((self.directory() / (external["session_id"] + ".json")).is_file())
        self.assertNotIn("[y/N]", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_clean_missing_local_folder_is_a_read_only_success(self):
        self.run_cli("", "--clean")
        self.assertFalse((self.project / ".trivy-porter").exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(self.calls(), [])

    def test_windows_clean_unlocks_and_closes_handles_before_renaming_storage(self):
        local = self.project.resolve() / ".trivy-porter"
        self.report_session(state=local)
        scripts = str(CLI.parent)
        sys.path.insert(0, scripts)
        try:
            transfer = importlib.import_module("report_transfer")
        finally:
            sys.path.remove(scripts)

        operations = []

        def locking(fd, operation, length):
            self.assertEqual(length, 1)
            self.assertTrue(stat.S_ISREG(os.fstat(fd).st_mode))
            operations.append((fd, operation))

        fake_msvcrt = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
        windows_os = SimpleNamespace(**{**vars(os), "name": "nt"})
        real_rename = Path.rename

        def rename_after_handle_closed(path, destination):
            self.assertEqual(path, local)
            self.assertEqual([operation for _fd, operation in operations], [1, 2])
            self.assertEqual(operations[0][0], operations[1][0])
            with self.assertRaises(OSError):
                os.fstat(operations[0][0])
            return real_rename(path, destination)

        with patch.object(transfer, "os", windows_os), patch.dict(sys.modules, {"msvcrt": fake_msvcrt}):
            with patch.object(Path, "cwd", return_value=self.project), patch.object(Path, "rename", rename_after_handle_closed):
                target, removed = transfer.clean_local_store()
        self.assertEqual(target, local)
        self.assertTrue(removed)
        self.assertFalse(local.exists())
        self.assertEqual(self.calls(), [])

    @unittest.skipIf(os.name == "nt", "Fixture symlinks may require Windows privileges")
    def test_clean_refuses_a_linked_root_and_never_follows_nested_links(self):
        external = self.root / "external-folder"
        external.mkdir()
        sentinel = external / "sentinel.txt"
        sentinel.write_text("keep outside", encoding="utf-8")
        local = self.project / ".trivy-porter"
        local.symlink_to(external, target_is_directory=True)
        result = self.run_cli("", "--clean", expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(local.is_symlink())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep outside")
        local.unlink()
        local.mkdir()
        (local / "linked-child").symlink_to(external, target_is_directory=True)
        self.run_cli("", "--clean")
        self.assertFalse(local.exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep outside")

    def test_clean_refuses_saved_active_work(self):
        local = self.project / ".trivy-porter"
        for stage, pending in (("batch_in_progress", None), ("configuring", "scan_running")):
            with self.subTest(stage=stage):
                with patch.dict(self.env, {"TRIVY_PORTER_STATE_DIR": str(local)}):
                    session = self.create_session(stage, pending_question=pending)
                result = self.run_cli("", "--clean", expected=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((self.directory(state=local) / (session["session_id"] + ".json")).is_file())

    def test_quick_command_conflicts_do_not_delete_or_scan(self):
        local = self.project / ".trivy-porter"
        local.mkdir()
        sentinel = local / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        combinations = [
            ["--clean", "--download"], ["--clean", "--session", "a" * 32],
            ["--clean", "--all"], ["--clean", "--state-dir", str(self.state)],
            ["--clean", "continue"], ["--download", "sessions"],
        ]
        for args in combinations:
            with self.subTest(args=args):
                result = self.run_cli("", *args, expected=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(sentinel.is_file())
        other = self.root / "different-project"
        other.mkdir()
        result = self.run_cli("", "--clean", project=other, expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(sentinel.is_file())
        self.assertEqual(self.calls(), [])

    def test_download_writes_a_private_self_contained_json_without_running_trivy(self):
        session = self.report_session()
        destination = self.root / "visible downloads"
        result = self.run_cli("", "--download", "--download-dir", str(destination))
        filename, packet = self.exported(destination)
        self.assertEqual(packet["export_format"], "trivy-porter-report")
        self.assertEqual(packet["schema_version"], 1)
        self.assertTrue(packet["exported_at"])
        self.assertEqual(packet["session"]["session_id"], session["session_id"])
        self.assertEqual(packet["session"]["revision"], session["revision"])
        self.assertIsNone(packet["session"]["scan"]["last_scan_complete"])
        self.assertIn("CVE-2026-12345", packet["scan_output"]["stdout"])
        self.assertIn("INFO", packet["scan_output"]["stderr"])
        self.assertIn(str(filename.resolve()), result.stdout)
        self.assertEqual(self.calls(), [])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(filename.stat().st_mode), 0o600)
        shutil.rmtree(self.state)
        self.assertIn("CVE-2026-12345", filename.read_text(encoding="utf-8"))

    def test_download_chooses_latest_updated_report_and_skips_unscanned_configuration(self):
        first = self.report_session()
        second = self.report_session()
        first["last_report"] = "A newer batch report on the earlier session"
        first = self.save(first)
        self.create_session("configuring", pending_question="method")
        destination = self.root / "downloads"
        self.run_cli("", "--download", "--download-dir", str(destination))
        _filename, packet = self.exported(destination)
        self.assertEqual(packet["session"]["session_id"], first["session_id"])
        self.assertNotEqual(packet["session"]["session_id"], second["session_id"])

    def test_download_supports_explicit_session_and_never_overwrites_a_prior_export(self):
        first = self.report_session()
        self.report_session()
        destination = self.root / "downloads"
        args = ["--download", "--session", first["session_id"], "--download-dir", str(destination)]
        self.run_cli("", *args)
        filename, packet = self.exported(destination)
        before = filename.read_bytes()
        self.run_cli("", *args)
        self.assertEqual(len(list(destination.glob("trivy-porter-report-*.json"))), 2)
        self.assertEqual(filename.read_bytes(), before)
        self.assertEqual(packet["session"]["session_id"], first["session_id"])

    def test_download_respects_explicit_storage_and_export_survives_full_cleanup(self):
        local = self.project / ".trivy-porter"
        session = self.report_session(state=local)
        destination = self.root / "downloads"
        self.run_cli("", "--download", "--state-dir", str(local), "--download-dir", str(destination))
        filename, packet = self.exported(destination)
        self.assertEqual(packet["session"]["session_id"], session["session_id"])
        self.run_cli("", "--clean")
        self.assertFalse(local.exists())
        self.assertTrue(filename.is_file())

    def test_download_refuses_missing_or_outside_artifacts_without_exporting(self):
        session = self.report_session()
        original = Path(session["scan"]["result"]["stdout_path"])
        original.unlink()
        destination = self.root / "downloads"
        result = self.run_cli("", "--download", "--download-dir", str(destination), expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(destination.glob("*.json")), [])
        external = self.root / "external-sensitive.txt"
        external.write_text("do not read this", encoding="utf-8")
        session["scan"]["result"]["stdout_path"] = str(external)
        self.save(session)
        result = self.run_cli("", "--download", "--download-dir", str(destination), expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(destination.glob("*.json")), [])
        self.assertNotIn("do not read this", result.stdout + result.stderr)

    @unittest.skipIf(os.name == "nt", "Fixture symlinks may require Windows privileges")
    def test_download_does_not_follow_artifact_symlinks(self):
        session = self.report_session()
        stdout = Path(session["scan"]["result"]["stdout_path"])
        stdout.unlink()
        external = self.root / "outside.txt"
        external.write_text("PRIVATE_EXTERNAL_FIXTURE", encoding="utf-8")
        stdout.symlink_to(external)
        destination = self.root / "downloads"
        result = self.run_cli("", "--download", "--download-dir", str(destination), expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PRIVATE_EXTERNAL_FIXTURE", result.stdout + result.stderr)
        self.assertEqual(list(destination.glob("*.json")), [])

    def test_download_rechecks_secret_source_and_session_metadata_redaction(self):
        marker = "PRIVATE_PORTER_FIXTURE_123456789"
        session = self.report_session(findings=[{
            "id": "F001", "scanner": "secret", "severity": "HIGH", "RuleID": "fixture-rule",
            "Match": marker, "Code": {"Lines": [{"Content": marker}]},
            "description": 'password="first ' + marker + '"',
        }])
        session["scan"]["argv_redacted"] = ["trivy", "fs", "--token", marker, "."]
        session["scan"]["explicit_flags"] = [{"name": "password", "value": marker}]
        session["scan"]["metadata"] = {"registry_token": marker}
        session = self.save(session)
        stdout = Path(session["scan"]["result"]["stdout_path"])
        stdout.write_text(scan_tests.TABLE + "\nsecrets.env (secrets)\n===================\n"
                          "Total: 1 (HIGH: 1)\nHIGH: fixture-rule\n1 [ API_KEY=" + marker + "\n", encoding="utf-8")
        destination = self.root / "downloads"
        self.run_cli("", "--download", "--download-dir", str(destination))
        filename, packet = self.exported(destination)
        self.assertNotIn(marker, filename.read_text(encoding="utf-8"))
        self.assertIn("CVE-2026-12345", packet["scan_output"]["stdout"])

    def test_download_default_uses_home_downloads_without_touching_real_home(self):
        self.report_session()
        scripts = str(CLI.parent)
        sys.path.insert(0, scripts)
        try:
            porter = importlib.import_module("trivy_porter")
        finally:
            sys.path.remove(scripts)
        fake_home = self.root / "fake-home"
        with patch.dict(os.environ, self.env, clear=True), patch("pathlib.Path.home", return_value=fake_home):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = porter.main(["--download", "--project", str(self.project), "--state-dir", str(self.state)])
        self.assertEqual(result, 0)
        self.exported(fake_home / "Downloads")

    def test_download_with_no_report_does_not_create_an_export_directory(self):
        self.create_session("configuring", pending_question="method")
        destination = self.root / "downloads"
        result = self.run_cli("", "--download", "--download-dir", str(destination), expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(destination.exists())
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
