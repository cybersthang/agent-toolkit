"""Smoke tests for git_guardrails hook."""
from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_dangerous_pattern_git_commit():
    from git_guardrails import _DANGEROUS_PATTERNS
    patterns = [label for _, label in _DANGEROUS_PATTERNS]
    assert "git commit" in patterns
    assert "git push" in patterns
    print("PASS test_dangerous_pattern_git_commit")


def test_skip_token_constants():
    from git_guardrails import SKIP_TOKEN_REL, SKIP_TOKEN_TTL_SECONDS
    assert ".skip_git_guard_next.json" in SKIP_TOKEN_REL
    assert SKIP_TOKEN_TTL_SECONDS == 600
    print("PASS test_skip_token_constants")


if __name__ == "__main__":
    test_dangerous_pattern_git_commit()
    test_skip_token_constants()
    print("\n2 tests passed")
