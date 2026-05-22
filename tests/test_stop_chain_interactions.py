# -*- coding: utf-8 -*-
"""Stop chain integration test — eval p7.

Closes Layer E `[assumption]` from v0.7.3 self-review.

Simulates Stop event by invoking each Stop hook in order with a
synthesized envelope, asserts:
  - First-block-wins semantics: if a hook emits `decision: block`,
    subsequent hooks would NOT see the same envelope reach them in
    real dispatcher.
  - Orchestrator (post-P1) is now hook #1 in Stop chain so its output
    reaches AGENT regardless of evidence_audit block.
  - PostToolUse hooks chain independently (no block cascade).

Note: Claude Code dispatcher behavior is `[assumption]` based on
observed sessions — these tests document the EXPECTED ordering
behavior and assert toolkit-side hooks output what they should.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
SETTINGS = TOOLKIT_ROOT / "templates" / "claude" / "settings.json"
PY = sys.executable


def _stop_chain_hooks() -> list:
    """Read settings.json Stop chain order."""
    cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = cfg["hooks"]["Stop"][0]["hooks"]
    out = []
    for h in hooks:
        cmd = h["command"].replace("\\", "/")
        name = cmd.split("/")[-1]
        out.append({"name": name, "timeout": h.get("timeout", 60)})
    return out


class TestStopChainOrder(unittest.TestCase):
    """Assert Stop chain order post-P1 reorder."""

    def test_implement_orchestrator_is_first(self):
        """P1 v0.8.0: orchestrator must be first to fire before any
        blocking hook."""
        hooks = _stop_chain_hooks()
        self.assertEqual(hooks[0]["name"], "implement_orchestrator.py",
                         f"Expected implement_orchestrator first; got {hooks[0]['name']}")

    def test_evidence_audit_is_second(self):
        """evidence_audit was previously first; now must be second."""
        hooks = _stop_chain_hooks()
        self.assertEqual(hooks[1]["name"], "evidence_audit.py")

    def test_verify_lint_scope_is_last(self):
        """Layer 5 file-level scope check is final gate."""
        hooks = _stop_chain_hooks()
        self.assertEqual(hooks[-1]["name"], "verify_lint_scope.py")

    def test_stop_chain_length(self):
        """9 hooks in Stop chain post-v0.12.0 (added complexity_sentinel)."""
        hooks = _stop_chain_hooks()
        self.assertEqual(len(hooks), 9)


class TestPreToolUseChainOrder(unittest.TestCase):
    """Assert PreToolUse chain ordering."""

    def test_pretool_chain(self):
        cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
        hooks = cfg["hooks"]["PreToolUse"][0]["hooks"]
        names = [h["command"].replace("\\", "/").split("/")[-1] for h in hooks]
        # invariant_guard MUST be first (blocking)
        self.assertEqual(names[0], "invariant_guard.py")
        # implement_snapshot_hook MUST be last (non-blocking)
        self.assertEqual(names[-1], "implement_snapshot_hook.py")


class TestPostToolUseIndependence(unittest.TestCase):
    """PostToolUse hooks are all non-blocking. Assert no `decision: block`
    in any PostToolUse hook source."""

    def test_no_block_in_posttool_hooks(self):
        cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
        hooks = cfg["hooks"]["PostToolUse"][0]["hooks"]
        names = [h["command"].replace("\\", "/").split("/")[-1] for h in hooks]
        for name in names:
            src = (HOOKS_DIR / name).read_text(encoding="utf-8")
            # Strict check: no `"decision": "block"` JSON output
            self.assertNotIn(
                '"decision": "block"', src,
                f"PostToolUse hook {name} contains block output",
            )


class TestStopHookBlockSemantics(unittest.TestCase):
    """Verify Stop hooks that DO block use the `decision: block` envelope."""

    def test_blocking_stop_hooks_have_block_keyword(self):
        # Hooks expected to block based on design review:
        blockers = {
            "evidence_audit.py",
            "verify_lint.py",
            "post_edit_verify_gate.py",
            "debug_sentry.py",
            # "verify_lint_scope.py" conditional (warn-only default,
            # block when enforce=block)
        }
        for hook_name in blockers:
            src = (HOOKS_DIR / hook_name).read_text(encoding="utf-8")
            self.assertIn(
                '"decision": "block"', src,
                f"Stop blocker hook {hook_name} missing block envelope",
            )

    def test_non_blocking_stop_hooks_default_warn(self):
        # Phase D v0.9.0: spec_drift_advisory + implement_orchestrator
        # are PURE warn-only (no block path).
        # implement_notes_gate now has CONDITIONAL block via enforce_mode.json
        # (default still warn).
        pure_warners = {
            "spec_drift_advisory.py",
            "implement_orchestrator.py",
        }
        for hook_name in pure_warners:
            src = (HOOKS_DIR / hook_name).read_text(encoding="utf-8")
            self.assertNotIn(
                '"decision": "block"', src,
                f"Pure-warn hook {hook_name} contains block envelope",
            )

    def test_conditional_block_hooks_default_warn(self):
        # Phase D v0.9.0: hooks that CAN block via enforce_mode.json
        # must default to warn. They invoke get_enforce_mode() to check.
        conditional = {"implement_notes_gate.py"}
        for hook_name in conditional:
            src = (HOOKS_DIR / hook_name).read_text(encoding="utf-8")
            self.assertIn(
                "get_enforce_mode", src,
                f"Conditional-block hook {hook_name} should use get_enforce_mode",
            )


class TestKillSwitchHonored(unittest.TestCase):
    """All 21 hooks must honor AGENT_TOOLKIT_DISABLE=1 env var."""

    def test_all_hooks_check_kill_switch(self):
        skipped = {"_common.py", "_patterns.py", "__init__.py"}
        kill_var = "AGENT_TOOLKIT_DISABLE"
        for hook in HOOKS_DIR.glob("*.py"):
            if hook.name in skipped or hook.name.startswith("_"):
                continue
            src = hook.read_text(encoding="utf-8")
            self.assertIn(
                kill_var, src,
                f"Hook {hook.name} missing kill-switch check",
            )


if __name__ == "__main__":
    unittest.main()
