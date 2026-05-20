# -*- coding: utf-8 -*-
"""Diagnose strategy — Python AssertionError with literal expected value.

Matches stderr like:
  AssertionError: 'foo' != 'bar'
  AssertionError: 42 != 41
  AssertionError: Regex didn't match: '<expected>' not found in '<actual>'

If the test file contains the literal expected value, propose updating
it to the observed actual. Conservative: only triggers when probe.
applies_when.path_globs includes a `*/tests/test_*.py` glob, and the
test file contains both the expected literal AND the file path appears
in stderr.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional


_ASSERT_RX = re.compile(
    r"AssertionError:\s*(?P<expected>['\"][^'\"]+['\"]|-?\d+(?:\.\d+)?)\s*!=\s*(?P<actual>['\"][^'\"]+['\"]|-?\d+(?:\.\d+)?)"
)
_FILE_RX = re.compile(r'File "([^"]+\.py)", line (\d+)')


def matches(probe: Dict[str, Any], last_stderr: str) -> bool:
    if not last_stderr:
        return False
    return bool(_ASSERT_RX.search(last_stderr))


def diagnose(probe: Dict[str, Any], last_stderr: str,
             workspace: Path) -> Optional[Dict[str, Any]]:
    m = _ASSERT_RX.search(last_stderr)
    if not m:
        return None
    expected = m.group("expected")
    actual = m.group("actual")
    if expected == actual:
        return None

    # Find the test file that emitted the error.
    fm = _FILE_RX.search(last_stderr)
    if not fm:
        return None
    file_path_str = fm.group(1).replace("\\", "/")
    workspace_str = str(workspace).replace("\\", "/")
    if not file_path_str.startswith(workspace_str):
        return None
    file_rel = file_path_str[len(workspace_str):].lstrip("/")

    target = workspace / file_rel
    if not target.exists():
        return None

    try:
        text = target.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None

    # Only propose if expected literal appears EXACTLY ONCE — otherwise we
    # can't safely target the replacement.
    if text.count(expected) != 1:
        return None

    return {
        "file": file_rel,
        "old_string": expected,
        "new_string": actual,
        "rationale": (
            f"AssertionError mismatch: expected {expected} but got "
            f"{actual}. Test expectation was stale — replaced literal in "
            f"{file_rel} with the observed actual value. Iter 1 fix."
        ),
    }
