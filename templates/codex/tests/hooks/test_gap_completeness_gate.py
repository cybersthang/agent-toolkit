"""Smoke tests for gap_completeness_gate hook.
Tests: gap emission parsing, defer marker, stale auto-expire.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_capture_new_gap_from_response():
    """G1 - description pattern → new gap with status=open."""
    from gap_completeness_gate import _capture_new_gap_emissions
    state = {"version": 1, "gaps": []}
    text = "Found issues:\nG1 — first problem here\nG2 — second issue"
    result = _capture_new_gap_emissions(state, text)
    gaps = result["gaps"]
    assert len(gaps) == 2, f"Expected 2 gaps, got {len(gaps)}"
    assert gaps[0]["id"] == "G1"
    assert gaps[0]["status"] == "open"
    print("PASS test_capture_new_gap_from_response")


def test_stale_auto_expire():
    """Open gap older than STALE_TTL → status flipped to stale."""
    from gap_completeness_gate import _apply_resolution_markers, STALE_TTL_SECONDS
    old_ts = int(time.time()) - STALE_TTL_SECONDS - 100
    state = {"gaps": [{"id": "G1", "surfaced_ts": old_ts, "status": "open",
                       "desc": "old", "resolution_ts": None,
                       "resolution_reason": None}]}
    result = _apply_resolution_markers(state, "")
    assert result["gaps"][0]["status"] == "stale"
    print("PASS test_stale_auto_expire")


def test_defer_marker_flips_status():
    """gap-defer: G1 <reason> → status=deferred."""
    from gap_completeness_gate import _apply_resolution_markers
    state = {"gaps": [{"id": "G1", "surfaced_ts": int(time.time()),
                       "status": "open", "desc": "x", "resolution_ts": None,
                       "resolution_reason": None}]}
    result = _apply_resolution_markers(
        state, "gap-defer: G1 next sprint priority")
    assert result["gaps"][0]["status"] == "deferred"
    print("PASS test_defer_marker_flips_status")


if __name__ == "__main__":
    test_capture_new_gap_from_response()
    test_stale_auto_expire()
    test_defer_marker_flips_status()
    print("\n3 tests passed")
