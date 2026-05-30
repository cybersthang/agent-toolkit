# -*- coding: utf-8 -*-
"""Tests for reuse_probe.py PreToolUse hook — v0.12.0.

Uses subprocess pattern (not module-load) because reuse_probe.py calls
wrap_utf8_stdio() at module init, which corrupts pytest's stdout capture
when loaded directly.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "reuse_probe.py"


def _run_hook(envelope: dict, extra_env: dict = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        env=env,
    )


class TestReuseProbe(unittest.TestCase):

    def setUp(self):
        self.td_obj = tempfile.TemporaryDirectory()
        self.workspace = Path(self.td_obj.name).resolve()
        (self.workspace / ".agent-toolkit").mkdir()

    def tearDown(self):
        self.td_obj.cleanup()

    def test_no_collision_silent(self):
        target = self.workspace / "new_feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "def brand_new_unique_name_xyz():\n    return 1\n",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual(result.returncode, 0)
        self.assertEqual((result.stdout or "").strip(), "",
                         "No collision → no output")

    def test_collision_emits_citation(self):
        existing = self.workspace / "utils.py"
        existing.write_text("def parse_iso_date(s):\n    return s\n",
                            encoding="utf-8")
        target = self.workspace / "feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "def parse_iso_date(s):\n    return None\n",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual(result.returncode, 0)
        self.assertIn("reuse-probe", result.stdout)
        self.assertIn("parse_iso_date", result.stdout)
        self.assertIn("utils.py", result.stdout)

    def test_skip_test_file(self):
        existing = self.workspace / "utils.py"
        existing.write_text("def foo():\n    return 1\n", encoding="utf-8")
        target = self.workspace / "tests" / "test_feature.py"
        target.parent.mkdir(parents=True)
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "def foo():\n    return 99\n",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual((result.stdout or "").strip(), "",
                         "Test files exempt from reuse probe")

    def test_skip_private_function(self):
        existing = self.workspace / "utils.py"
        existing.write_text("def _helper():\n    return 1\n", encoding="utf-8")
        target = self.workspace / "feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "def _helper():\n    return 2\n",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual((result.stdout or "").strip(), "",
                         "Private functions (leading _) exempt")

    def test_disable_env_var(self):
        existing = self.workspace / "utils.py"
        existing.write_text("def foo():\n    return 1\n", encoding="utf-8")
        target = self.workspace / "feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "def foo():\n    return 2\n",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope, extra_env={"AGENT_TOOLKIT_DISABLE": "1"})
        self.assertEqual((result.stdout or "").strip(), "",
                         "DISABLE env var silences hook")

    def test_non_py_file_skipped(self):
        existing = self.workspace / "utils.py"
        existing.write_text("def foo():\n    return 1\n", encoding="utf-8")
        target = self.workspace / "doc.md"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "def foo(): pass\n",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual((result.stdout or "").strip(), "", ".md files exempt")

    def test_class_collision_detected(self):
        existing = self.workspace / "models.py"
        existing.write_text("class UserCard:\n    pass\n", encoding="utf-8")
        target = self.workspace / "feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "class UserCard:\n    pass\n",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertIn("class UserCard", result.stdout)


if __name__ == "__main__":
    unittest.main()
