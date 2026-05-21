# -*- coding: utf-8 -*-
"""Tests for hook_health.py aggregator — Phase C eval c1."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
TOOL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "hook_health.py"


def _load():
    spec = importlib.util.spec_from_file_location("_hh", str(TOOL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestHookHealth(unittest.TestCase):

    def setUp(self):
        self.mod = _load()

    def test_empty_logs_green_health(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            report = self.mod.aggregate(workspace, window=50)
            self.assertEqual(report["health"], "green")
            self.assertEqual(report["fires_total"], 0)
            self.assertEqual(report["crashes_total"], 0)

    def test_aggregate_fires_per_hook(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            events = [
                {"ts": 1, "hook": "evidence_audit.py", "verdict": "block"},
                {"ts": 2, "hook": "evidence_audit.py", "verdict": "ok"},
                {"ts": 3, "hook": "verify_lint.py", "verdict": "ok",
                 "duration_ms": 50},
                {"ts": 4, "hook": "verify_lint.py", "verdict": "ok",
                 "duration_ms": 100},
            ]
            (workspace / ".agent-toolkit" / ".hook_fire_log.json").write_text(
                json.dumps({"events": events}), encoding="utf-8",
            )
            report = self.mod.aggregate(workspace)
            self.assertEqual(report["fires_total"], 4)
            self.assertEqual(report["fires_per_hook"]["evidence_audit.py"], 2)
            self.assertEqual(report["fires_per_hook"]["verify_lint.py"], 2)
            self.assertEqual(report["avg_duration_ms_per_hook"]["verify_lint.py"], 75)

    def test_crash_log_yellow_health(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            import time
            (workspace / ".agent-toolkit" / ".hook_crash_log.json").write_text(
                json.dumps({"events": [
                    {"ts": int(time.time()), "hook": "x.py",
                     "exc_type": "RuntimeError", "exc_msg": "boom"},
                ]}), encoding="utf-8",
            )
            report = self.mod.aggregate(workspace)
            self.assertIn(report["health"], ("yellow", "red"))
            self.assertEqual(report["crashes_total"], 1)

    def test_markdown_render(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            report = self.mod.aggregate(workspace)
            md = self.mod.render_markdown(report)
            self.assertIn("Hook health", md)
            self.assertIn("Status:", md)

    def test_spec_first_guard_activity_aggregated(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            (workspace / ".agent-toolkit" / ".spec_first_guard_log.json").write_text(
                json.dumps({"events": [
                    {"ts": 1, "kind": "warn"},
                    {"ts": 2, "kind": "warn"},
                    {"ts": 3, "kind": "bypass"},
                ]}), encoding="utf-8",
            )
            report = self.mod.aggregate(workspace)
            self.assertEqual(report["spec_first_guard"]["warns"], 2)
            self.assertEqual(report["spec_first_guard"]["bypasses"], 1)


if __name__ == "__main__":
    unittest.main()
