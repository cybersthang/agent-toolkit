# -*- coding: utf-8 -*-
"""Unit tests for the 3 seed gap_fix diagnose strategies."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSE_DIR = TOOLKIT_ROOT / "templates" / "codex" / "gap_fix_diagnose"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(
        f"_diag_{path.stem}", str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"_diag_{path.stem}"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPythonAssertionMismatch(unittest.TestCase):

    def setUp(self):
        self.mod = _load(DIAGNOSE_DIR / "python_assertion_mismatch.py")

    def test_matches_assertion_pattern(self):
        stderr = "  AssertionError: 'foo' != 'bar'"
        self.assertTrue(self.mod.matches({}, stderr))

    def test_no_match_on_other_errors(self):
        self.assertFalse(self.mod.matches({}, "ValueError: something else"))

    def test_no_match_empty_stderr(self):
        self.assertFalse(self.mod.matches({}, ""))

    def test_diagnose_proposes_patch_when_literal_unique(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            test_file = workspace / "tests" / "test_x.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text(
                "def test_y(self):\n"
                "    self.assertEqual(answer, 'foo')\n",
                encoding="utf-8",
            )
            stderr = (
                f'  File "{test_file}", line 2, in test_y\n'
                f"    self.assertEqual(answer, 'foo')\n"
                f"AssertionError: 'foo' != 'bar'\n"
            )
            patch = self.mod.diagnose({}, stderr, workspace)
            self.assertIsNotNone(patch)
            self.assertEqual(patch["file"], "tests/test_x.py")
            self.assertEqual(patch["old_string"], "'foo'")
            self.assertEqual(patch["new_string"], "'bar'")


class TestRegexPatternMismatch(unittest.TestCase):

    def setUp(self):
        self.mod = _load(DIAGNOSE_DIR / "regex_pattern_mismatch.py")

    def test_matches_log_assertion_refute(self):
        stderr = ("[falsify] REFUTED: stdout did not match 'foo.*bar'\n"
                  "stdout sample: foo X bar Y")
        self.assertTrue(self.mod.matches({}, stderr))

    def test_no_match_other_stderr(self):
        self.assertFalse(self.mod.matches({}, "[falsify] PROVEN: all good"))

    def test_diagnose_relaxes_regex_in_probes_json(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            probes_path = workspace / ".agent-toolkit" / "acceptance-probes.json"
            probes_path.write_text(
                '{"probes": [{"id": "x", "falsification": {"runner": '
                '{"expected_stdout_regex": "old-strict-pattern"}}}]}',
                encoding="utf-8",
            )
            probe = {
                "id": "x",
                "falsification": {
                    "runner": {"expected_stdout_regex": "old-strict-pattern"},
                },
            }
            stderr = (
                "[falsify] REFUTED: stdout did not match 'old-strict-pattern'\n"
                "[falsify] stdout sample: actual line was different"
            )
            patch = self.mod.diagnose(probe, stderr, workspace)
            self.assertIsNotNone(patch)
            self.assertIn("expected_stdout_regex", patch["new_string"])
            self.assertIn("old-strict-pattern", patch["old_string"])


class TestPlaywrightSelectorZero(unittest.TestCase):

    def setUp(self):
        self.mod = _load(DIAGNOSE_DIR / "playwright_selector_zero.py")

    def test_matches_selector_zero(self):
        stderr = "Error: locator.click: selector resolved to 0 elements"
        self.assertTrue(self.mod.matches({}, stderr))

    def test_no_match_other_playwright_errors(self):
        self.assertFalse(self.mod.matches({}, "Error: timeout 30000ms"))

    def test_diagnose_skips_handwritten_script(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            spec_rel = ".agent-toolkit/scripts/probes/handwritten.py"
            spec_file = workspace / spec_rel
            spec_file.parent.mkdir(parents=True)
            spec_file.write_text(
                "# Hand-written probe script (no auto-gen marker).\n"
                "import time\n",
                encoding="utf-8",
            )
            probe = {"falsification": {"runner": {"spec_file": spec_rel}}}
            stderr = "selector resolved to 0 elements"
            patch = self.mod.diagnose(probe, stderr, workspace)
            self.assertIsNone(patch)

    def test_diagnose_annotates_auto_generated_script(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            spec_rel = ".agent-toolkit/scripts/probes/auto.py"
            spec_file = workspace / spec_rel
            spec_file.parent.mkdir(parents=True)
            spec_file.write_text(
                "# Auto-generated probe script for `probe-x`.\n"
                "def main():\n"
                "    with sync_playwright() as p:\n"
                "        page = ctx.new_page()\n"
                "        try:\n"
                "        _login(page)\n",
                encoding="utf-8",
            )
            probe = {"falsification": {"runner": {"spec_file": spec_rel}}}
            stderr = "selector resolved to 0 elements"
            patch = self.mod.diagnose(probe, stderr, workspace)
            self.assertIsNotNone(patch)
            self.assertIn("NEED SELECTOR REVIEW", patch["new_string"])


if __name__ == "__main__":
    unittest.main()
