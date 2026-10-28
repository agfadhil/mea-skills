"""Scan progress bar, finding counts, and the clean-scan message."""

import copy
import importlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "trivy-porter" / "scripts"
SUMMARY = """Report Summary

┌───────────────────┬──────┬─────────────────┬─────────┐
│ Target            │ Type │ Vulnerabilities │ Secrets │
├───────────────────┼──────┼─────────────────┼─────────┤
│ package-lock.json │ npm  │ {vulnerabilities}               │    -    │
└───────────────────┴──────┴─────────────────┴─────────┘
Legend:
- '-': Not scanned
- '0': Clean (no security findings detected)
"""
NOT_SCANNED = """Report Summary

┌────────┬──────┬─────────────────┬─────────┐
│ Target │ Type │ Vulnerabilities │ Secrets │
├────────┼──────┼─────────────────┼─────────┤
│   -    │  -   │        -        │    -    │
└────────┴──────┴─────────────────┴─────────┘
"""


class TtyBuffer(io.StringIO):
    def isatty(self):
        return True


def load(name):
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.pop(0)


class ProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = load("terminal_output")
        cls.porter = load("trivy_porter")

    def test_frames_keep_a_constant_width_and_bounce_the_block(self):
        frames = [self.output.progress_frame("Memindai", tick, 0) for tick in range(40)]
        self.assertEqual({len(frame) for frame in frames}, {len(frames[0])})
        self.assertTrue(all(frame.count("###") == 1 and frame.count("#") == 3 for frame in frames))
        self.assertIn("[###", frames[0])
        self.assertIn("###]", frames[17])
        self.assertEqual(self.output.progress_frame("Memindai", 34, 0), frames[0])
        self.assertTrue(self.output.progress_frame("Memindai", 0, 12.9).endswith(" 12s"))

    def run_sleep(self, stdout, label="Memindai"):
        with patch.object(sys, "stdout", stdout), patch.dict("os.environ", {"TERM": "xterm"}):
            return self.porter.capture_process([sys.executable, "-c", "import time; time.sleep(0.6)"],
                                               str(SCRIPTS), label)

    def test_terminal_shows_a_bar_and_clears_it_afterwards(self):
        stdout = TtyBuffer()
        _, code, interrupted, _ = self.run_sleep(stdout)
        written = stdout.getvalue()
        self.assertEqual((code, interrupted), (0, False))
        self.assertIn("\rMemindai [", written)
        self.assertIn("###", written)
        self.assertTrue(written.endswith("\r"))
        self.assertEqual(written.rsplit("\r", 2)[1].strip(), "")

    def test_a_terminal_reporting_zero_columns_still_gets_whole_frames(self):
        stdout = TtyBuffer()
        with patch.object(self.porter.shutil, "get_terminal_size", return_value=__import__("os").terminal_size((0, 0))):
            self.run_sleep(stdout)
        self.assertIn("\rMemindai [###", stdout.getvalue())

    def test_pipes_and_dumb_terminals_get_no_bar(self):
        pipe = io.StringIO()
        self.run_sleep(pipe)
        self.assertEqual(pipe.getvalue(), "")
        dumb = TtyBuffer()
        with patch.object(sys, "stdout", dumb), patch.dict("os.environ", {"TERM": "dumb"}):
            self.porter.capture_process([sys.executable, "-c", "pass"], str(SCRIPTS), "Memindai")
        self.assertEqual(dumb.getvalue(), "")


class FindingCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.porter = load("trivy_porter")

    def count(self, raw, truncated=False):
        return self.porter.count_findings(raw, truncated)

    def test_json_counts_every_finding_kind(self):
        raw = json.dumps({"Results": [
            {"Target": "a", "Vulnerabilities": [{}, {}], "Secrets": [{}]},
            {"Target": "b", "Misconfigurations": [{}], "Licenses": [{}]}, {"Target": "c"}]})
        self.assertEqual(self.count(raw), 5)

    def test_json_with_scanned_targets_and_no_findings_is_zero(self):
        self.assertEqual(self.count(json.dumps({"Results": [{"Target": "package-lock.json", "Class": "lang-pkgs"}]})), 0)

    def test_nothing_scanned_is_unknown_not_clean(self):
        self.assertIsNone(self.count(json.dumps({"SchemaVersion": 2})))
        self.assertIsNone(self.count(json.dumps({"Results": []})))
        self.assertIsNone(self.count(NOT_SCANNED))
        self.assertIsNone(self.count(""))
        self.assertIsNone(self.count("not a report"))

    def test_table_summary_distinguishes_clean_from_not_scanned(self):
        self.assertEqual(self.count(SUMMARY.format(vulnerabilities="0")), 0)
        self.assertEqual(self.count(SUMMARY.format(vulnerabilities="3")), 3)

    def test_truncated_output_is_never_counted(self):
        self.assertIsNone(self.count(SUMMARY.format(vulnerabilities="0"), truncated=True))


class CleanMessageTests(unittest.TestCase):
    MESSAGE = "wah sudah clean nih.. saatnya main game yak.."

    @classmethod
    def setUpClass(cls):
        cls.output = load("terminal_output")

    def setUp(self):
        self.data = {"session_id": "a" * 32, "stage": "awaiting_analysis", "scan": {
            "method": "fs", "target": ".", "severity": "ALL", "explicit_flags": [],
            "result": {"exit_code": 0, "interrupted": False, "truncated": False, "finding_count": 0}}}

    def render(self):
        return self.output.render_handoff(self.data, "/p", "/p/.trivy-porter", "$trivy-porter analyze x",
                                          columns=100, is_tty=False, environment={})

    def test_zero_findings_show_the_count_and_the_message(self):
        rendered = self.render()
        self.assertIn("Temuan: 0", rendered)
        # Like "SALIN KE CHAT": a plain label line, last, after the final panel.
        self.assertTrue(rendered.endswith("╯\n\n" + self.MESSAGE + "\n"))
        self.assertEqual(rendered.count(self.MESSAGE), 1)

    def test_findings_show_the_count_without_the_message(self):
        self.data["scan"]["result"]["finding_count"] = 4
        rendered = self.render()
        self.assertIn("Temuan: 4", rendered)
        self.assertNotIn(self.MESSAGE, rendered)

    def test_unknown_count_shows_neither(self):
        del self.data["scan"]["result"]["finding_count"]
        rendered = self.render()
        self.assertNotIn("Temuan:", rendered)
        self.assertNotIn(self.MESSAGE, rendered)

    def test_message_needs_an_unfiltered_complete_scan(self):
        cases = {
            "severity filter": lambda d: d["scan"].update(severity="CRITICAL"),
            "ignore-unfixed": lambda d: d["scan"].update(explicit_flags=[{"name": "ignore-unfixed", "value": True}]),
            "inherited ignore files": lambda d: d["scan"].update(inherited_settings={"requires_agent_review": True}),
            "nonzero exit": lambda d: d["scan"]["result"].update(exit_code=1),
            "interrupted": lambda d: d["scan"]["result"].update(interrupted=True),
            "truncated": lambda d: d["scan"]["result"].update(truncated=True),
        }
        for name, change in cases.items():
            with self.subTest(name):
                data = copy.deepcopy(self.data)
                change(data)
                self.data, original = data, self.data
                try:
                    self.assertNotIn(self.MESSAGE, self.render())
                finally:
                    self.data = original


if __name__ == "__main__":
    unittest.main()
