"""Smoke tests for post_edit_verify_gate hook."""
from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_edit_tool_set():
    from post_edit_verify_gate import EDIT_TOOLS
    assert "Edit" in EDIT_TOOLS
    assert "Write" in EDIT_TOOLS
    assert "MultiEdit" in EDIT_TOOLS
    print("PASS test_edit_tool_set")


def test_skip_marker_constant():
    from post_edit_verify_gate import SKIP_MARKER
    assert "verify-gate" in SKIP_MARKER
    print("PASS test_skip_marker_constant")


if __name__ == "__main__":
    test_edit_tool_set()
    test_skip_marker_constant()
    print("\n2 tests passed")
