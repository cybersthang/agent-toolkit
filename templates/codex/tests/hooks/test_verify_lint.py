"""Smoke tests for verify_lint hook."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_extract_slug_from_verify_report_header():
    from verify_lint import _extract_spec_slug
    text = "## Verify Report — my-feature-slug\nstatus: PASS"
    slug = _extract_spec_slug(text)
    assert slug == "my-feature-slug", f"Got {slug}"
    print("PASS test_extract_slug_from_verify_report_header")


def test_extract_slug_returns_none_without_match():
    from verify_lint import _extract_spec_slug
    assert _extract_spec_slug("plain text no report") is None
    print("PASS test_extract_slug_returns_none_without_match")


if __name__ == "__main__":
    test_extract_slug_from_verify_report_header()
    test_extract_slug_returns_none_without_match()
    print("\n2 tests passed")
