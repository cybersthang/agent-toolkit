# -*- coding: utf-8 -*-
"""Tests for loc_delta_tracker.py PostToolUse hook — v0.12.0."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "loc_delta_tracker.py"


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


class TestLocDeltaTracker(unittest.TestCase):

    def setUp(self):
        self.td_obj = tempfile.TemporaryDirectory()
        self.workspace = Path(self.td_obj.name).resolve()
        (self.workspace / ".agent-toolkit").mkdir()

    def tearDown(self):
        self.td_obj.cleanup()

    def test_small_edit_silent_but_logged(self):
        target = self.workspace / "feature.py"
        target.write_text("def x():\n    return 1\n", encoding="utf-8")
        envelope = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(target),
                "old_string": "return 1",
                "new_string": "return 2",
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual(result.stdout.strip(), "", "Small edit → no warn")
        # Event still logged
        log = self.workspace / ".agent-toolkit" / ".hook_loc_log.json"
        self.assertTrue(log.exists())
        data = json.loads(log.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["events"]), 1)

    def test_large_added_warns(self):
        target = self.workspace / "feature.py"
        big_content = "\n".join(f"line_{i} = {i}" for i in range(250))
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": big_content,
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertIn("loc-budget", result.stdout)
        self.assertIn("250 LOC", result.stdout)

    def test_test_file_exempt(self):
        target = self.workspace / "tests" / "test_huge.py"
        target.parent.mkdir()
        big_content = "\n".join(f"def test_{i}(): pass" for i in range(300))
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": big_content,
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual(result.stdout.strip(), "",
                         "Test files exempt from LOC budget")

    def test_config_override_threshold(self):
        cfg = self.workspace / ".agent-toolkit" / "loc_budget.json"
        cfg.write_text(json.dumps({"per_turn_added_warn": 50}), encoding="utf-8")
        target = self.workspace / "feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "\n".join(f"x = {i}" for i in range(80)),
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertIn("loc-budget", result.stdout)
        self.assertIn("80 LOC", result.stdout)

    def test_disable_env_var(self):
        target = self.workspace / "feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "\n".join(f"x = {i}" for i in range(500)),
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope, extra_env={"AGENT_TOOLKIT_DISABLE": "1"})
        self.assertEqual(result.stdout.strip(), "")

    def test_disabled_in_config(self):
        cfg = self.workspace / ".agent-toolkit" / "loc_budget.json"
        cfg.write_text(json.dumps({"enabled": False}), encoding="utf-8")
        target = self.workspace / "feature.py"
        envelope = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "\n".join(f"x = {i}" for i in range(500)),
            },
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope)
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
