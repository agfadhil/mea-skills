"""Check the terminal/chat boundary without changing live session files."""

import copy
import importlib
from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "trivy-porter" / "scripts"


class HandoffRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS))
        try:
            cls.output = importlib.import_module("terminal_output")
        finally:
            sys.path.pop(0)

    def setUp(self):
        self.session_id = "a" * 32
        self.project = "/workspace/project with spaces/" + "application/" * 6
        self.state = self.project + ".trivy-porter"
        self.command = ("$trivy-porter analyze " + self.session_id + " --project '" +
                        self.project + "' --state-dir '" + self.state + "' Jumlah temuan yang ingin diselesaikan: n")
        self.data = {
            "session_id": self.session_id,
            "stage": "awaiting_analysis",
            "scan": {
                "method": "fs", "target": ".", "severity": "ALL",
                "last_scan_complete": None,
                "result": {"exit_code": 0, "interrupted": False, "truncated": False},
            },
        }

    def render(self, **options):
        return self.output.render_handoff(self.data, self.project, self.state,
                                          self.command, **options)

    def test_long_copy_command_is_a_single_raw_line_at_every_terminal_width(self):
        for width in (32, 52, 80):
            with self.subTest(width=width):
                rendered = self.render(columns=width, is_tty=True,
                                       environment={"TERM": "xterm-256color"})
                lines = rendered.splitlines()
                commands = [line for line in lines if line.startswith("$trivy-porter ")]
                self.assertEqual(commands, [self.command])
                self.assertGreater(len(self.command), width)
                self.assertNotIn("\x1b", commands[0])
                self.assertIn("\x1b[", rendered)

    def test_piped_and_no_color_output_do_not_emit_ansi_controls(self):
        for is_tty, environment in ((False, {}), (True, {"NO_COLOR": ""}),
                                    (True, {"TERM": "dumb"})):
            with self.subTest(is_tty=is_tty, environment=environment):
                rendered = self.render(columns=52, is_tty=is_tty, environment=environment)
                self.assertNotIn("\x1b", rendered)
                self.assertEqual([line for line in rendered.splitlines()
                                  if line.startswith("$trivy-porter ")], [self.command])

    def test_analysis_handoff_explains_count_project_and_cleanup(self):
        rendered = self.render(columns=200, is_tty=False, environment={})
        panel, _, after = rendered.partition("SALIN KE CHAT")
        # The notes follow the raw command as bullets, outside the panel.
        for note in ("0 = semua item", "Tambahkan --project PATH", "Kirim secara manual"):
            self.assertNotIn(note, panel)
            self.assertIn("  • " + note if note != "0 = semua item" else note, after)
        self.assertIn("Exit code saja", panel)
        # The --prompt tip sits right under the "open chat" heading, inside the first panel.
        heading = "Buka chat pada proyek ini, lalu salin perintah di bawah."
        self.assertIn(heading, panel)
        self.assertGreater(panel.index("trivy-porter --prompt"), panel.index(heading))
        self.assertNotIn("trivy-porter --prompt", after)
        self.assertIn("fyi lagi:", after)
        self.assertIn("trivy-porter --clean", after)
        self.assertTrue(after.rstrip().endswith("╯"))
        self.data["stage"] = "batch_in_progress"
        later = self.render(columns=200, is_tty=False, environment={}).replace(self.command, "")
        self.assertNotIn("Jumlah temuan", later)
        self.assertNotIn("fyi:\n", later)

    def test_severity_focus_hint_only_when_every_severity_was_scanned_and_scope_is_open(self):
        hint = "--severity:CRITICAL"
        _, _, after = self.render(columns=200).partition("SALIN KE CHAT")
        self.assertIn(hint, after)
        cases = {
            "filtered scan": lambda d: d["scan"].update(severity="HIGH"),
            "zero findings": lambda d: d["scan"]["result"].update(finding_count=0),
            "recovery": lambda d: d.update(stage="batch_in_progress", batch_request={"status": "pending"}),
            "no pending request": lambda d: d.update(stage="awaiting_batch"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                original, self.data = self.data, copy.deepcopy(self.data)
                try:
                    change(self.data)
                    self.assertNotIn(hint, self.render(columns=200))
                finally:
                    self.data = original
        self.data.update(stage="awaiting_batch", batch_request={"status": "pending"})
        self.assertIn(hint, self.render(columns=200))

    def test_rendering_preserves_scan_evidence_and_exposes_the_saved_exit_status(self):
        self.data["scan"]["result"].update(exit_code=7, interrupted=True, truncated=True)
        before = copy.deepcopy(self.data)
        rendered = self.render(columns=80, is_tty=False, environment={})
        self.assertEqual(self.data, before)
        self.assertIsNone(self.data["scan"]["last_scan_complete"])
        self.assertRegex(rendered, r"\b7\b")


if __name__ == "__main__":
    unittest.main()
