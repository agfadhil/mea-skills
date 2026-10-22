"""Exercise configurable storage and narrowly scoped cleanup in temporary state."""

import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import test_trivy_porter as scan_tests


CLI = scan_tests.CLI
STORE = scan_tests.STORE


class StorageIntegrationTests(unittest.TestCase):
    # Reuse fixture plumbing without inheriting the scan test methods.
    setUp = scan_tests.TerminalIntegrationTests.setUp
    run_cli = scan_tests.TerminalIntegrationTests.run_cli
    create_session = scan_tests.TerminalIntegrationTests.create_session
    sessions = scan_tests.TerminalIntegrationTests.sessions
    only_session = scan_tests.TerminalIntegrationTests.only_session

    def directory(self, project=None, state=None):
        root = str((project or self.project).resolve())
        return (state or self.state) / hashlib.sha256(root.encode("utf-8")).hexdigest()

    def session_file(self, session, project=None, state=None):
        return self.directory(project, state) / (session["session_id"] + ".json")

    def artifact(self, session, suffix="stdout.txt", run="a" * 32):
        filename = session["session_id"] + "." + run + "." + suffix
        path = self.directory() / filename
        path.write_text("sanitized fixture\n", encoding="utf-8")
        return path

    def test_storage_displays_resolved_paths_without_creating_directories(self):
        self.env["PATH"] = ""
        result = self.run_cli("", "storage")
        self.assertIn(str(self.state.resolve()), result.stdout)
        self.assertIn(str(self.directory().resolve()), result.stdout)
        self.assertFalse(self.state.exists())

    def test_sessions_lists_only_current_project_without_trivy(self):
        session = self.create_session("complete")
        self.env["PATH"] = ""
        result = self.run_cli("", "sessions")
        self.assertIn(session["session_id"], result.stdout)
        self.assertIn("complete", result.stdout)
        other = self.root / "different project"
        other.mkdir()
        result = self.run_cli("", "sessions", project=other)
        self.assertNotIn(session["session_id"], result.stdout)
        self.assertFalse(self.directory(other).exists())

    def test_explicit_state_dir_overrides_environment_and_is_shared_with_helper(self):
        explicit = self.root / "visible scan results"
        result = self.run_cli("\n\n\n", "--state-dir", str(explicit))
        stored = list(self.directory(state=explicit).glob("*.json"))
        self.assertEqual(len(stored), 1)
        self.assertFalse(self.state.exists())
        session = json.loads(stored[0].read_text(encoding="utf-8"))
        self.assertIn("--state-dir", result.stdout)
        self.assertIn(str(explicit.resolve()), result.stdout)
        read = subprocess.run(
            [sys.executable, str(STORE), "read", "--project", str(self.project),
             "--state-dir", str(explicit), "--session", session["session_id"]],
            text=True, capture_output=True, env=self.env, timeout=10,
        )
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout)["session_id"], session["session_id"])

    def test_explicit_state_dir_works_for_helper_creation_and_cli_listing(self):
        explicit = self.root / "visible results"
        created = subprocess.run(
            [sys.executable, str(STORE), "create", "--project", str(self.project),
             "--state-dir", str(explicit), "--from-file", "-"],
            input=json.dumps({"stage": "complete"}), text=True, capture_output=True,
            env=self.env, timeout=10,
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        session = json.loads(created.stdout)
        result = self.run_cli("", "sessions", "--state-dir", str(explicit))
        self.assertIn(session["session_id"], result.stdout)
        self.assertFalse(self.state.exists())

    def test_relative_storage_path_resolves_from_terminal_working_directory(self):
        result = self.run_cli("", "storage", "--state-dir", "scan results")
        expected = (self.project / "scan results").resolve()
        self.assertIn(str(expected), result.stdout)
        self.assertFalse(expected.exists())

    @unittest.skipIf(os.name == "nt", "POSIX permission modes are not portable to Windows")
    def test_existing_custom_root_permissions_are_preserved(self):
        self.state.mkdir()
        self.state.chmod(0o755)
        session = self.create_session("complete")
        self.assertTrue(self.session_file(session).exists())
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.directory().stat().st_mode), 0o700)

    def test_clean_requires_explicit_session_or_all_scope(self):
        session = self.create_session("complete")
        self.run_cli("y\n", "clean", expected=None)
        self.assertTrue(self.session_file(session).exists())

    def test_clean_default_no_and_eof_keep_session_and_artifacts(self):
        session = self.create_session("complete")
        artifact = self.artifact(session)
        original = self.session_file(session).read_bytes()
        for answer in ("\n", "", "n\n"):
            with self.subTest(answer=answer):
                self.run_cli(answer, "clean", "--session", session["session_id"], expected=None)
                self.assertEqual(self.session_file(session).read_bytes(), original)
                self.assertTrue(artifact.exists())

    def test_clean_selected_session_removes_known_artifacts_only(self):
        selected = self.create_session("complete")
        other = self.create_session("complete")
        stdout = self.artifact(selected)
        stderr = self.artifact(selected, "stderr.txt")
        legacy = self.directory() / (selected["session_id"] + ".stdout.txt")
        legacy.write_text("legacy sanitized fixture\n", encoding="utf-8")
        other_artifact = self.artifact(other)
        unrelated = self.directory() / "notes.txt"
        unrelated.write_text("keep me", encoding="utf-8")
        unrelated_json = self.directory() / "notes.json"
        unrelated_json.write_text("not a session payload", encoding="utf-8")
        malformed = self.directory() / (selected["session_id"] + ".not-a-run-id.stdout.txt")
        malformed.write_text("keep unknown name", encoding="utf-8")
        result = self.run_cli("y\n", "clean", "--session", selected["session_id"])
        self.assertIn(str(stdout), result.stdout)
        self.assertFalse(self.session_file(selected).exists())
        self.assertFalse(stdout.exists())
        self.assertFalse(stderr.exists())
        self.assertFalse(legacy.exists())
        self.assertTrue(self.session_file(other).exists())
        self.assertTrue(other_artifact.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(unrelated_json.read_text(encoding="utf-8"), "not a session payload")
        self.assertTrue(malformed.exists())

    def test_clean_does_not_follow_user_output_or_artifact_paths(self):
        external = self.project / "user selected report.json"
        external.write_text("keep report", encoding="utf-8")
        session = self.create_session(
            "complete", scan={"result": {"stdout_path": str(external), "stderr_path": str(external)}})
        artifact = self.artifact(session)
        self.run_cli("y\n", "clean", "--session", session["session_id"])
        self.assertFalse(self.session_file(session).exists())
        self.assertFalse(artifact.exists())
        self.assertEqual(external.read_text(encoding="utf-8"), "keep report")

    def test_clean_all_is_limited_to_current_project_partition(self):
        first = self.create_session("complete")
        second = self.create_session("paused")
        current_files = [self.session_file(first), self.session_file(second), self.artifact(first), self.artifact(second)]
        other = self.root / "other project"
        other.mkdir()
        created = subprocess.run(
            [sys.executable, str(STORE), "create", "--project", str(other), "--from-file", "-"],
            input=json.dumps({"stage": "complete"}), text=True, capture_output=True,
            env=self.env, timeout=10,
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        other_session = json.loads(created.stdout)
        self.run_cli("y\n", "clean", "--all")
        self.assertTrue(all(not path.exists() for path in current_files))
        self.assertTrue(self.session_file(other_session, project=other).exists())

    def test_clean_rejects_another_projects_session_id(self):
        session = self.create_session("complete")
        other = self.root / "other project"
        other.mkdir()
        self.run_cli("y\n", "clean", "--session", session["session_id"], project=other, expected=None)
        self.assertTrue(self.session_file(session).exists())

    def test_clean_refuses_active_scan_or_batch(self):
        for stage, pending in (("batch_in_progress", None), ("configuring", "scan_running")):
            with self.subTest(stage=stage):
                session = self.create_session(stage, pending_question=pending)
                artifact = self.artifact(session)
                result = self.run_cli("y\n", "clean", "--session", session["session_id"], expected=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(self.session_file(session).exists())
                self.assertTrue(artifact.exists())

    @unittest.skipIf(os.name == "nt", "Creating fixture symlinks can require Windows privileges")
    def test_cleanup_never_follows_an_artifact_symlink(self):
        session = self.create_session("complete")
        external = self.root / "outside-state.txt"
        external.write_text("never delete this", encoding="utf-8")
        link = self.directory() / (session["session_id"] + "." + "b" * 32 + ".stdout.txt")
        link.symlink_to(external)
        self.run_cli("y\n", "clean", "--session", session["session_id"], expected=None)
        self.assertEqual(external.read_text(encoding="utf-8"), "never delete this")

    def test_sessions_and_cleanup_do_not_create_a_missing_state_root(self):
        self.run_cli("", "sessions")
        self.assertFalse(self.state.exists())
        self.run_cli("y\n", "clean", "--all", expected=None)
        self.assertFalse(self.state.exists())

    def test_cleanup_rejects_a_session_changed_after_preview(self):
        session = self.create_session("complete")
        artifact = self.artifact(session)
        scripts = str(CLI.parent)
        sys.path.insert(0, scripts)
        try:
            porter = importlib.import_module("trivy_porter")
        finally:
            sys.path.remove(scripts)

        def change_before_answer(_prompt):
            root, base, directory = porter.store.project_context(self.project)
            changed = json.loads(self.session_file(session).read_text(encoding="utf-8"))
            changed["last_report"] = "changed after cleanup preview"
            porter.store.save_data(changed, session["session_id"], root, base, directory)
            return "y"

        with patch.dict(os.environ, self.env, clear=True), patch("builtins.input", side_effect=change_before_answer):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = porter.main(["clean", "--project", str(self.project), "--session", session["session_id"]])
        self.assertNotEqual(result, 0)
        self.assertTrue(self.session_file(session).exists())
        self.assertTrue(artifact.exists())
        updated = json.loads(self.session_file(session).read_text(encoding="utf-8"))
        self.assertEqual(updated["revision"], session["revision"] + 1)


if __name__ == "__main__":
    unittest.main()
