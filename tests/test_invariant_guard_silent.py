# -*- coding: utf-8 -*-
"""Tests for v0.12.3 invariant_guard silent-exit fast path."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "invariant_guard.py"


def _run_hook(envelope: dict, workspace: Path,
              extra_env: dict = None) -> subprocess.CompletedProcess:
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


class TestInvariantGuardSilentExit(unittest.TestCase):
    """v0.12.3 — when invariants.json missing OR empty, hook should exit
    0 with NO stdout output (Claude Code treats as default allow).
    Saves ~30 tokens × ~66 fires/session = ~2k tokens/session for
    workspaces with 0 invariants registered."""

    def setUp(self):
        self.td_obj = tempfile.TemporaryDirectory()
        self.workspace = Path(self.td_obj.name).resolve()
        (self.workspace / ".agent-toolkit").mkdir()

    def tearDown(self):
        self.td_obj.cleanup()

    def _envelope(self) -> dict:
        return {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.workspace / "feature.py"),
                "old_string": "x = 1",
                "new_string": "x = 2",
            },
            "cwd": str(self.workspace),
        }

    def test_missing_invariants_file_silent(self):
        """No invariants.json → silent exit, NO stdout."""
        result = _run_hook(self._envelope(), self.workspace)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "",
                         "Missing invariants.json must produce empty stdout "
                         "(default allow per Claude Code spec)")

    def test_empty_invariants_array_silent(self):
        """invariants.json with empty array → silent exit."""
        path = self.workspace / ".agent-toolkit" / "invariants.json"
        path.write_text(json.dumps({"invariants": []}), encoding="utf-8")
        result = _run_hook(self._envelope(), self.workspace)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "",
                         "Empty invariants array must produce empty stdout")

    def test_blocker_text_scan_triggers_fall_through(self):
        """File missing but the test makes sure the early-exit only fires
        when blocker text scan also returns False. Smoke: create empty
        dict (no blocker text) → still silent."""
        path = self.workspace / ".agent-toolkit" / "invariants.json"
        path.write_text("{}", encoding="utf-8")  # parses OK, no blocker text
        result = _run_hook(self._envelope(), self.workspace)
        self.assertEqual(result.returncode, 0)
        # Either silent (no invariants) or allow JSON — both are fine.
        # The point: not block.
        if (result.stdout or "").strip():
            payload = json.loads(result.stdout)
            self.assertNotEqual(
                payload.get("hookSpecificOutput", {}).get("permissionDecision"),
                "deny",
            )

    def test_non_supported_tool_silent(self):
        """tool_name not in SUPPORTED_TOOLS → silent exit (was _allow JSON before)."""
        envelope = {
            "tool_name": "Read",  # Not in {Edit, Write, MultiEdit, NotebookEdit}
            "tool_input": {"file_path": "x.py"},
            "cwd": str(self.workspace),
        }
        result = _run_hook(envelope, self.workspace)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "",
                         "Non-Edit/Write tool name must produce empty stdout")

    def test_disable_env_var_silent(self):
        """AGENT_TOOLKIT_DISABLE=1 → silent exit."""
        result = _run_hook(self._envelope(), self.workspace,
                           extra_env={"AGENT_TOOLKIT_DISABLE": "1"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "",
                         "DISABLE env var must produce empty stdout")

    def test_populated_invariants_still_fires(self):
        """When real invariants exist, hook should NOT silent-exit — it
        must evaluate and emit JSON allow/deny so enforcement still
        works. Regression guard for the optimization."""
        path = self.workspace / ".agent-toolkit" / "invariants.json"
        path.write_text(json.dumps({
            "invariants": [{
                "id": "TEST-1",
                "description": "test invariant",
                "applies_to": ["*.py"],
                "rules": {"must_keep_regex": [r"x\s*=\s*1"]},
                "severity": "blocker",
                "rationale": "test",
            }]
        }), encoding="utf-8")
        result = _run_hook(self._envelope(), self.workspace)
        self.assertEqual(result.returncode, 0)
        # Edit changes "x = 1" → "x = 2" → removes the must_keep pattern
        # → should DENY. JSON output must be present.
        self.assertNotEqual((result.stdout or "").strip(), "",
                            "Populated invariants must emit JSON (not silent)")
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["permissionDecision"], "deny",
            "Real invariant violation must DENY, not silent-allow"
        )


if __name__ == "__main__":
    unittest.main()
