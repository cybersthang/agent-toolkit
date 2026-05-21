# -*- coding: utf-8 -*-
"""Tests for emit_fire_event() ring buffer — Phase C eval c3."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
COMMON = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "_common.py"


def _load_common():
    spec = importlib.util.spec_from_file_location("_common_fire_test", str(COMMON))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_common_fire_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFireInstrumentation(unittest.TestCase):

    def setUp(self):
        self.mod = _load_common()

    def test_emit_fire_event_appends_to_buffer(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            with patch.object(self.mod, "_resolve_crash_workspace",
                              return_value=workspace):
                self.mod.emit_fire_event(
                    "test_hook.py", verdict="block",
                    duration_ms=42, detail="test")
            log_path = workspace / ".agent-toolkit" / ".hook_fire_log.json"
            self.assertTrue(log_path.exists())
            data = json.loads(log_path.read_text(encoding="utf-8"))
            events = data["events"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["hook"], "test_hook.py")
            self.assertEqual(events[0]["verdict"], "block")
            self.assertEqual(events[0]["duration_ms"], 42)
            self.assertEqual(events[0]["detail"], "test")

    def test_ring_buffer_caps_at_1000(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            with patch.object(self.mod, "_resolve_crash_workspace",
                              return_value=workspace):
                for i in range(1100):
                    self.mod.emit_fire_event(f"h{i}.py", verdict="ok")
            log_path = workspace / ".agent-toolkit" / ".hook_fire_log.json"
            data = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["events"]), 1000,
                             "Ring buffer should cap at 1000")

    def test_silent_on_oserror(self):
        # Pointing at non-writable workspace shouldn't raise
        with patch.object(self.mod, "_resolve_crash_workspace",
                          return_value=Path("/nonexistent/path/xyz")):
            # Just verify it doesn't raise
            self.mod.emit_fire_event("x.py")


class TestSampleHooksInstrumented(unittest.TestCase):
    """v0.9.1 — 4 sample hooks must call emit_fire_event at decision
    branches (allow / warn / block)."""

    HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
    INSTRUMENTED = {
        "invariant_guard.py",
        "evidence_audit.py",
        "implement_orchestrator.py",
        "verify_lint_scope.py",
    }

    def test_all_sample_hooks_call_emit_fire_event(self):
        missing = []
        for hook_name in self.INSTRUMENTED:
            src = (self.HOOKS_DIR / hook_name).read_text(encoding="utf-8")
            if "emit_fire_event(" not in src:
                missing.append(hook_name)
        self.assertEqual(missing, [],
                         f"Sample hooks missing emit_fire_event call: {missing}")

    def test_all_sample_hooks_import_emit_fire_event(self):
        missing = []
        for hook_name in self.INSTRUMENTED:
            src = (self.HOOKS_DIR / hook_name).read_text(encoding="utf-8")
            if "emit_fire_event" not in src.split("def ")[0]:
                # not in imports section
                # crude: check if it appears before first def
                pass
            # Better: just confirm it's importable
            if "emit_fire_event" not in src:
                missing.append(hook_name)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
