"""Smoke tests for debug_sentry hook."""
from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_strong_traceback_pattern_matches():
    from debug_sentry import _matches, DEFAULT_PATTERNS
    text = 'Traceback (most recent call last):\n  File "x.py", line 5\nTypeError: foo'
    strong, weak = _matches(text, DEFAULT_PATTERNS)
    assert len(strong) >= 1, f"Expected strong match. strong={strong}"
    print("PASS test_strong_traceback_pattern_matches")


def test_weak_only_without_traceback_context_skipped():
    """Bare exception name in plain prose → no match (no traceback context)."""
    from debug_sentry import _matches, DEFAULT_PATTERNS
    text = "Pattern matches: TypeError, AttributeError detected in code review."
    strong, weak = _matches(text, DEFAULT_PATTERNS)
    assert len(weak) == 0, f"Expected 0 weak hits without context. weak={weak}"
    print("PASS test_weak_only_without_traceback_context_skipped")


def test_skip_marker_detection():
    from debug_sentry import _has_skip_marker
    assert _has_skip_marker("debug-sentry: skip false positive") is True
    assert _has_skip_marker("nothing here") is False
    print("PASS test_skip_marker_detection")


if __name__ == "__main__":
    test_strong_traceback_pattern_matches()
    test_weak_only_without_traceback_context_skipped()
    test_skip_marker_detection()
    print("\n3 tests passed")
