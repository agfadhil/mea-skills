"""Keep project-local session storage out of Git and Trivy's own scan inputs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import test_trivy_porter as scan_tests


CLI = scan_tests.CLI
STORE = scan_tests.STORE


class LocalStateIntegrationTests(unittest.TestCase):
    fixture_setup = scan_tests.TerminalIntegrationTests.setUp
    calls = scan_tests.TerminalIntegrationTests.calls

    def setUp(self):
        self.fixture_setup()
        self.env.pop("TRIVY_PORTER_STATE_DIR", None)
        self.env["XDG_STATE_HOME"] = str(self.root / "old xdg location")
        self.state = self.project / ".trivy-porter"

    def run_cli(self, answers="", *arguments, project=None, cwd=None, expected=0):
        result = subprocess.run(
            [sys.executable, str(CLI), *arguments, "--project", str(project or self.project)],
            input=answers, text=True, capture_output=True, env=self.env,
            cwd=cwd or self.project, timeout=15,
        )
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def directory(self, project=None, state=None):
        root = str((project or self.project).resolve())
        paths = list((state or self.state).glob("*/session.json"))
        matches = [path.parent for path in paths
                   if json.loads(path.read_text(encoding="utf-8")).get("project_root") == root]
        return max(matches, key=lambda path: path.name) if matches else (state or self.state)

    def only_session(self, project=None, state=None):
        root = str((project or self.project).resolve())
        files = [path for path in (state or self.state).glob("*/session.json")
                 if json.loads(path.read_text(encoding="utf-8")).get("project_root") == root]
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text(encoding="utf-8"))

    def skip_dirs(self, argv):
        result = []
        for index, arg in enumerate(argv):
            if arg == "--skip-dirs":
                result.extend(argv[index + 1].split(","))
            elif arg.startswith("--skip-dirs="):
                result.extend(arg.split("=", 1)[1].split(","))
        return result

    def assert_state_excluded(self, argv, state=None):
        expected = self.directory(state=state).resolve()
        resolved = []
        for value in self.skip_dirs(argv):
            path = Path(value)
            resolved.append((path if path.is_absolute() else self.project / path).resolve())
        self.assertIn(expected, resolved)

    def test_default_storage_uses_terminal_cwd_and_ignores_old_xdg_default(self):
        launcher = self.root / "launcher directory"
        launcher.mkdir()
        result = self.run_cli("", "storage", cwd=launcher)
        expected = launcher / ".trivy-porter"
        self.assertIn(str(expected.resolve()), result.stdout)
        self.assertFalse(expected.exists())
        self.assertFalse((self.root / "old xdg location").exists())
        self.assertFalse(self.state.exists())

    def test_default_storage_and_sessions_are_read_only(self):
        self.env["PATH"] = ""
        self.run_cli("", "storage")
        self.run_cli("", "sessions")
        self.assertFalse(self.state.exists())

    def test_default_scan_handoff_can_be_read_by_helper_from_another_cwd(self):
        result = self.run_cli("\n\n\n")
        session = self.only_session()
        commands = [line for line in result.stdout.splitlines() if line.startswith("$trivy-porter ")]
        self.assertEqual(commands, ["$trivy-porter analyze " + session["session_id"] + " Jumlah temuan yang ingin diselesaikan: n"])
        self.assertIn("Temuan: 1", result.stdout)
        self.assertEqual(session["scan"]["result"]["finding_count"], 1)
        read = subprocess.run(
            [sys.executable, str(STORE), "read", "--project", str(self.project),
             "--state-dir", str(self.state), "--session", session["session_id"]],
            env=self.env, cwd=self.root, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout)["session_id"], session["session_id"])
        self.assertEqual(session["stage"], "awaiting_analysis")
        self.assert_state_excluded(self.calls(scans_only=True)[0]["args"])

    def test_handoff_from_another_cwd_names_the_project_only(self):
        launcher = self.root / "launcher directory"
        launcher.mkdir()
        result = self.run_cli("\n\n\n", cwd=launcher)
        state = launcher / ".trivy-porter"
        session = self.only_session(state=state)
        commands = [line for line in result.stdout.splitlines() if line.startswith("$trivy-porter ")]
        self.assertEqual(len(commands), 1)
        self.assertEqual(scan_tests.shlex.split(commands[0].removesuffix(" Jumlah temuan yang ingin diselesaikan: n")),
                         ["$trivy-porter", "analyze", session["session_id"], "--project",
                          str(self.project.resolve())])

    def test_default_cli_and_helper_share_the_same_cwd_store(self):
        self.run_cli("\n\n\n")
        session = self.only_session()
        read = subprocess.run(
            [sys.executable, str(STORE), "read", "--project", str(self.project),
             "--session", session["session_id"]],
            env=self.env, cwd=self.project, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout)["session_id"], session["session_id"])

    def test_different_launcher_cwd_does_not_change_scan_project(self):
        launcher = self.root / "launcher"
        launcher.mkdir()
        self.run_cli("\n\n\n", cwd=launcher)
        state = launcher / ".trivy-porter"
        session = self.only_session(state=state)
        self.assertEqual(session["project_root"], str(self.project.resolve()))
        self.assertEqual(self.calls(scans_only=True), [{"args": ["fs", "."], "cwd": str(self.project.resolve())}])
        self.assertFalse(self.state.exists())

    def test_explicit_and_environment_storage_still_override_local_default(self):
        environment = self.root / "environment results"
        explicit = self.root / "explicit results"
        self.env["TRIVY_PORTER_STATE_DIR"] = str(environment)
        result = self.run_cli("", "storage")
        self.assertIn(str(environment.resolve()), result.stdout)
        result = self.run_cli("", "storage", "--state-dir", str(explicit))
        self.assertIn(str(explicit.resolve()), result.stdout)
        self.assertFalse(self.state.exists())
        self.assertFalse(environment.exists())
        self.assertFalse(explicit.exists())

    def test_external_storage_preserves_the_exact_default_scan(self):
        external = self.root / "external results"
        self.run_cli("\n\n\n", "--state-dir", str(external))
        self.assertEqual(self.calls(scans_only=True), [{"args": ["fs", "."], "cwd": str(self.project.resolve())}])
        self.assertEqual(self.only_session(state=external)["scan"]["argv_redacted"], ["trivy", "fs", "."])

    def test_local_state_exclusion_preserves_user_selected_skip_dirs(self):
        self.run_cli("\n--skip-dirs\n2\nnode_modules\n\n\n")
        argv = self.calls(scans_only=True)[0]["args"]
        self.assertIn("node_modules", self.skip_dirs(argv))
        self.assert_state_excluded(argv)
        session = self.only_session()
        self.assertEqual(session["scan"]["argv_redacted"], ["trivy", *argv])

    def test_local_exclusion_preserves_inherited_environment_skip_dirs(self):
        self.env["TRIVY_SKIP_DIRS"] = "node_modules"
        self.run_cli("\n\n\n\n")
        argv = self.calls(scans_only=True)[0]["args"]
        self.assertIn("node_modules", self.skip_dirs(argv))
        self.assert_state_excluded(argv)

    def test_other_owned_partitions_are_excluded_without_skipping_unknown_folders(self):
        other = self.root / "other project"
        other.mkdir()
        created = subprocess.run(
            [sys.executable, str(STORE), "create", "--project", str(other),
             "--state-dir", str(self.state), "--from-file", "-"],
            input=json.dumps({"stage": "complete"}), env=self.env, cwd=self.project,
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        unknown = self.state / ("c" * 64)
        unknown.mkdir()
        (unknown / "application.txt").write_text("do not exclude me\n", encoding="utf-8")
        self.run_cli("\n\n\n")
        argv = self.calls(scans_only=True)[0]["args"]
        excluded = [(Path(value) if Path(value).is_absolute() else self.project / value).resolve()
                    for value in self.skip_dirs(argv)]
        self.assertIn(self.directory().resolve(), excluded)
        self.assertIn(self.directory(project=other).resolve(), excluded)
        self.assertNotIn(unknown.resolve(), excluded)

    def test_unparsed_inherited_skip_configuration_does_not_get_silently_overridden(self):
        (self.project / "trivy.yaml").write_text("skip-dirs:\n  - vendor\n", encoding="utf-8")
        result = self.run_cli("\n\n\n\n", expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(scans_only=True), [])

    def test_missing_skip_dirs_support_does_not_scan_its_own_state(self):
        self.help_file.write_text("\n".join(
            line for line in scan_tests.HELP.splitlines() if "--skip-dirs " not in line), encoding="utf-8")
        result = self.run_cli("\n\n\n", expected=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(scans_only=True), [])

    @unittest.skipUnless(shutil.which("git"), "Git is required for staging integration")
    def test_local_state_does_not_enter_git_index(self):
        subprocess.run(["git", "init", "--quiet", str(self.project)], env=self.env,
                       check=True, capture_output=True, text=True, timeout=10)
        application = self.project / "application.txt"
        application.write_text("application fixture\n", encoding="utf-8")
        ignore = self.project / ".gitignore"
        ignore.write_text("existing-ignore-rule\n", encoding="utf-8")
        self.run_cli("\n\n\n")
        subprocess.run(["git", "add", "-A"], env=self.env, cwd=self.project,
                       check=True, capture_output=True, text=True, timeout=10)
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], env=self.env,
                                cwd=self.project, check=True, capture_output=True, text=True, timeout=10)
        self.assertIn("application.txt", staged.stdout.splitlines())
        self.assertFalse(any(name.startswith(".trivy-porter/") for name in staged.stdout.splitlines()))
        self.assertEqual(ignore.read_text(encoding="utf-8"), "existing-ignore-rule\n")

    @unittest.skipUnless(shutil.which("git"), "Git is required for staging integration")
    def test_storage_root_can_be_project_without_ignoring_application_files(self):
        subprocess.run(["git", "init", "--quiet", str(self.project)], env=self.env,
                       check=True, capture_output=True, text=True, timeout=10)
        application = self.project / "application.txt"
        application.write_text("application fixture\n", encoding="utf-8")
        ignore = self.project / ".gitignore"
        ignore.write_text("existing-ignore-rule\n", encoding="utf-8")
        self.run_cli("\n\n\n", "--state-dir", str(self.project))
        argv = self.calls(scans_only=True)[0]["args"]
        self.assert_state_excluded(argv, state=self.project)
        excluded = [(Path(value) if Path(value).is_absolute() else self.project / value).resolve()
                    for value in self.skip_dirs(argv)]
        self.assertNotIn(self.project.resolve(), excluded)
        self.assertEqual(ignore.read_text(encoding="utf-8"), "existing-ignore-rule\n")
        self.assertEqual(application.read_text(encoding="utf-8"), "application fixture\n")
        subprocess.run(["git", "add", "-A"], env=self.env, cwd=self.project,
                       check=True, capture_output=True, text=True, timeout=10)
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], env=self.env,
                                cwd=self.project, check=True, capture_output=True, text=True, timeout=10)
        self.assertIn("application.txt", staged.stdout.splitlines())
        partition = self.directory(state=self.project).name + "/"
        self.assertFalse(any(name.startswith(partition) for name in staged.stdout.splitlines()))

    @unittest.skipUnless(shutil.which("git"), "Git is required for staging integration")
    def test_tracked_storage_is_rejected_without_changing_the_index(self):
        subprocess.run(["git", "init", "--quiet", str(self.project)], env=self.env,
                       check=True, capture_output=True, text=True, timeout=10)
        self.run_cli("\n\n\n")
        session = self.only_session()
        stored = self.directory() / "session.json"
        original = stored.read_bytes()
        subprocess.run(["git", "add", "-f", str(stored)], env=self.env, cwd=self.project,
                       check=True, capture_output=True, text=True, timeout=10)
        before = subprocess.run(["git", "ls-files", "--stage", "-z"], env=self.env, cwd=self.project,
                                check=True, capture_output=True, timeout=10).stdout
        scan_calls = self.calls(scans_only=True)
        result = self.run_cli("", "continue", "--session", session["session_id"], expected=None)
        self.assertNotEqual(result.returncode, 0)
        after = subprocess.run(["git", "ls-files", "--stage", "-z"], env=self.env, cwd=self.project,
                               check=True, capture_output=True, timeout=10).stdout
        self.assertEqual(before, after)
        self.assertEqual(original, stored.read_bytes())
        self.assertEqual(scan_calls, self.calls(scans_only=True))


if __name__ == "__main__":
    unittest.main()
