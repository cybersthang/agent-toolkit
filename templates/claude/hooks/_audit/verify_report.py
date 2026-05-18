"""Verify Report probe-spread check (ADR-007 Bước 3 enforcement).

When the agent emits a Verify Report, all probes for that report MUST
travel in ONE assistant message (multiple `tool_use` blocks in parallel).
Splitting probes across N messages breaks point-in-time snapshot — by
the time probe N runs, DB state has drifted from probe 1.

Override: agent can write `(sequential — depends on #N-1)` in the report
to declare a legitimate ordering dependency. Otherwise BLOCK with re-emit
directive.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .claim_audit import EVIDENCE_BASH_SUBSTRINGS


# BUG-FIX B1 (2026-05-17): Verify Report header matcher must be case-insensitive
# + tolerant of single/double hash + the inline header form `Verify Report —`
# (no leading hash) which the verify-feature SKILL template also uses.
VERIFY_REPORT_HEADER_RE = re.compile(
    r"(?:#+\s*|^\s*)verify\s*report\b",
    re.IGNORECASE | re.UNICODE | re.MULTILINE,
)
SEQUENTIAL_OVERRIDE_RE = re.compile(
    r"sequential\s*[-—]\s*depends\s*on", re.IGNORECASE | re.UNICODE,
)


def verify_report_probe_spread(turn: List[Dict[str, Any]], text: str) -> Optional[str]:
    """Return a block-reason string if the Verify Report's probes are
    spread across > 1 assistant message without a `sequential — depends on`
    override. Returns None when the rule does not apply.

    Conditions to flag:
      - Response text matches /#+\\s*verify\\s*report/i (case-insensitive).
      - tool_use blocks (counted as "probes") split across > 1 assistant message.
      - No assistant text mentions "sequential — depends on" (legit override).

    Bash filter: only treat Bash tool_use as a probe when the command contains
    an EVIDENCE_BASH_SUBSTRING token (`select`, `psql`, `curl`, etc.). Plain
    Bash for restart/mkdir/kill is NOT a probe — counting them caused
    false-positive blocks (BUG-FIX B2, 2026-05-17).
    """
    if not VERIFY_REPORT_HEADER_RE.search(text):
        return None
    if SEQUENTIAL_OVERRIDE_RE.search(text):
        return None

    msg_with_probes = 0
    total_probes = 0
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if not isinstance(content, list):
            continue
        had_probe_here = False
        for block in content:
            if block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            is_probe = False
            if name.startswith("mcp__"):
                is_probe = True
            elif name == "Bash":
                cmd = ((block.get("input") or {}).get("command") or "").lower()
                if any(sub in cmd for sub in EVIDENCE_BASH_SUBSTRINGS):
                    is_probe = True
            if is_probe:
                total_probes += 1
                had_probe_here = True
        if had_probe_here:
            msg_with_probes += 1

    if msg_with_probes <= 1 or total_probes <= 1:
        return None

    return (
        "[evidence-audit] ADR-007 Bước 3 violation — Verify Report's probes spread "
        f"across {msg_with_probes} assistant messages ({total_probes} probes total). "
        "Verify phải capture 1 snapshot point-in-time → tất cả probe đi trong 1 "
        "message duy nhất (multiple tool_use blocks song song).\n\n"
        "Hợp lệ override: nếu probe N phụ thuộc output của probe N-1, ghi "
        "`(sequential — depends on #<N-1>)` trong Verify Report → audit pass.\n\n"
        "Sửa: re-emit Verify Report với tất cả probe trong 1 message duy nhất."
    )
