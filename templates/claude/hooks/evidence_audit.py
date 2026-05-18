#!/usr/bin/env python
"""Stop hook — flag claims that lack tool-call evidence in this turn.

Runs after the agent finishes a response. Reads the transcript for the
turn that just ended (from the most recent user message to the final
assistant text). If the assistant made non-trivial claims ("root cause
is X", "Y is slow", "Z is missing") WITHOUT having called any
discovery tool (Read, Grep, Glob, codebase MCP, postgres MCP,
realdata_test MCP), the hook blocks the stop and asks the agent to
either verify the claims or tag them `[assumption]`.

Loops are bounded: the hook checks `stop_hook_active` in the envelope
and skips if Claude has already been re-prompted once for this stop.

Stays silent (exit 0) when:
  - No claims detected.
  - Response already tags itself with [assumption] / [unverified] /
    "tôi không chắc" / "I'm not sure" markers.
  - Tool calls in this turn already include any discovery tool.
  - Response is short (< 240 chars) — likely a non-load-bearing reply.

Fails open on any parse error.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, split_current_turn,
)
from _patterns import (  # noqa: E402
    VERIFY_REPORT_HEADER_RE as _VERIFY_REPORT_HEADER_RE,
    SEQUENTIAL_OVERRIDE_RE as _SEQUENTIAL_OVERRIDE_RE,
)

wrap_utf8_stdio()


CLAIM_PATTERNS = [
    r"\broot\s*cause\b",
    r"\bnguy(ê|e)n\s*nhân\s*(g(ố|o)c|chính)\b",
    r"\bch(ậ|a)m\b|\bslow\b|\bbottleneck\b",
    r"\bthi(ế|e)u\b|\bmissing\b|\bdoesn'?t\s*exist\b",
    r"\bbug\b|\bb(ị|i)\s*l(ỗ|o)i\b|\bbroken\b",
    r"\bkhông\s*ho(ạ|a)t\s*đ(ộ|o)ng\b|\bnot\s*working\b",
    r"\bsai\b|\bwrong\b|\bincorrect\b",
    r"\bthay\s*đ(ổ|o)i\s*này\s*s(ẽ|e)\b|\bthis\s*change\s*will\b",
    r"\bnên\s*(s(ử|u)a|d(ù|u)ng|b(ỏ|o))\b|\bshould\s*(fix|use|remove)\b",
    r"\bsafe\s*to\b|\ban\s*toàn\s*đ(ể|e)\b",
]

# If any of these strings appear in the response, the agent has already
# disclaimed — skip the audit. Substring match (lowercase).
DISCLAIMER_MARKERS = (
    "[assumption]",
    "[unverified]",
    "[chưa verify]",
    "[không chắc]",
    "tôi không chắc",
    "i'm not sure",
    "i am not sure",
    "needs verification",
    "cần xác minh",
    "chưa kiểm chứng",
)

# Tool names that count as "evidence-gathering" in a turn. MCP tools are
# matched by prefix (`mcp__`) AND not by name suffix — covers any
# server (codebase / postgres / realdata_test / jira / custom plugin).
EVIDENCE_TOOLS = {"Read", "Grep", "Glob", "NotebookRead", "BashOutput", "WebFetch"}
EVIDENCE_TOOL_PREFIXES = ("mcp__",)
# Bash counts only when it looks like inspection (not raw mutation).
EVIDENCE_BASH_SUBSTRINGS = (
    "grep", "rg ", "find ", "cat ", "head ", "tail ", "ls ", "wc ",
    "git log", "git diff", "git blame", "git show", "psql", "select ", "explain",
)


def _exit_allow() -> None:
    sys.exit(0)


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


# Transcript reader + turn split are imported from _common (read_jsonl_transcript
# + split_current_turn). Kept aliases below for local readability.
_read_transcript = read_jsonl_transcript
_split_current_turn = split_current_turn


def _extract_text_and_tools(turn: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Concatenate assistant text and collect tool_use entries from the turn."""
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for msg in turn:
        # Claude Code stores either `message.content` (Anthropic block list)
        # or a flat text field. Handle both.
        role = msg.get("role") or msg.get("type")
        if role == "assistant":
            content = (msg.get("message") or {}).get("content") or msg.get("content")
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text") or "")
                    elif btype == "tool_use":
                        tool_calls.append(block)
    return ("\n".join(text_parts), tool_calls)


def _verify_report_probe_spread(turn: List[Dict[str, Any]], text: str) -> Optional[str]:
    """ADR-007 Bước 3 enforcement: Verify Report probes phải PARALLEL (1 message).

    Returns reason string if violated, else None.

    Conditions to flag:
      - Response text matches /#+\\s*verify\\s*report/i.
      - tool_use blocks split across > 1 assistant message.
      - No assistant text mentions "sequential — depends on" (legit override).

    Bash filter: only treat Bash tool_use as a probe when the command contains
    an EVIDENCE_BASH_SUBSTRING token (`select`, `psql`, `curl`, etc.). Plain
    Bash for restart/mkdir/kill is NOT a probe — counting them caused
    false-positive blocks (BUG-FIX B2, 2026-05-17).
    """
    if not _VERIFY_REPORT_HEADER_RE.search(text):
        return None
    if _SEQUENTIAL_OVERRIDE_RE.search(text):
        return None
    # Count assistant messages containing >=1 probe-like tool_use.
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
                # B2 fix: only count Bash as probe if command contains evidence tokens.
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


def _has_disclaimer(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in DISCLAIMER_MARKERS)


def _find_claims(text: str) -> List[str]:
    """Return list of distinct matched claim labels (deduped)."""
    seen = []
    low = text.lower()
    for pat in CLAIM_PATTERNS:
        if re.search(pat, low, re.UNICODE):
            seen.append(pat)
    return seen


def _has_evidence(tool_calls: List[Dict[str, Any]]) -> bool:
    for call in tool_calls:
        name = call.get("name") or ""
        if name in EVIDENCE_TOOLS:
            return True
        if any(name.startswith(prefix) for prefix in EVIDENCE_TOOL_PREFIXES):
            return True
        if name == "Bash":
            cmd = ((call.get("input") or {}).get("command") or "").lower()
            if any(sub in cmd for sub in EVIDENCE_BASH_SUBSTRINGS):
                return True
    return False


def _format_reason(text: str, claims: List[str]) -> str:
    sample = (text[:280].rstrip() + "…") if len(text) > 280 else text.strip()
    return (
        "[evidence-audit] Response vừa rồi có claim nhưng KHÔNG đi kèm bất kỳ "
        "tool call inspect nào trong turn này (không Read/Grep/Glob/MCP search/"
        "psql). Trước khi chốt, hoặc:\n\n"
        f"1. Chạy MCP / Read / Grep để verify các claim ({len(claims)} pattern "
        "khớp: " + ", ".join(c for c in claims[:5]) + ").\n"
        "2. Hoặc nếu không thể verify, sửa response gắn nhãn `[assumption]` "
        "hoặc `[chưa verify]` cho từng claim chưa có chứng cứ — rõ ràng với "
        "user là phỏng đoán, không phải fact.\n\n"
        "Trích response cần kiểm tra:\n"
        f"---\n{sample}\n---\n\n"
        "Bỏ qua audit cho turn này: thêm dòng `evidence-audit: skip` vào "
        "response (chỉ dùng khi claim hiển nhiên vô hại như format/style)."
    )


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        _exit_allow()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_allow()

    # Don't recurse — Claude Code re-runs the agent if we block; bail out
    # the second time so we never loop forever.
    if envelope.get("stop_hook_active"):
        _exit_allow()

    transcript_path = envelope.get("transcript_path")
    if not transcript_path:
        _exit_allow()
    tpath = Path(transcript_path)
    if not tpath.exists():
        _exit_allow()

    messages = _read_transcript(tpath)
    if not messages:
        _exit_allow()

    turn = _split_current_turn(messages)
    text, tool_calls = _extract_text_and_tools(turn)

    if not text or len(text) < 240:
        _exit_allow()
    if "evidence-audit: skip" in text.lower():
        _exit_allow()

    # ADR-007 Bước 3 enforcement — check BEFORE disclaimer/claim audit
    # because Verify Report skipping parallel probes is a structural violation,
    # not a claim-evidence one.
    probe_spread_reason = _verify_report_probe_spread(turn, text)
    if probe_spread_reason:
        _emit_block(probe_spread_reason)

    if _has_disclaimer(text):
        _exit_allow()

    claims = _find_claims(text)
    if not claims:
        _exit_allow()

    if _has_evidence(tool_calls):
        _exit_allow()

    _emit_block(_format_reason(text, claims))
    return 0


if __name__ == "__main__":
    sys.exit(main())
