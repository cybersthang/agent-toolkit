#!/usr/bin/env python
"""Stop hook — Vibe-flow Phase 4: Debug sentry.

Sau khi agent chốt 1 response, hook này quét text + tool_result của turn vừa
rồi cho dấu hiệu traceback / exception chưa xử lý. Nếu phát hiện và agent
chưa disclaim (`[assumption]`, `[chưa fix]`) hoặc chưa gọi debug skill →
block stop, đòi agent:

1. Mở skill `<stack>-<version>-debug-troubleshoot` để root-cause + fix, HOẶC
2. Tag response `[assumption]` cho phần liên quan traceback (nếu thật sự
   chưa đủ thông tin để fix).

Config: `<workspace>/.agent-toolkit/debug.json`.

```json
{
  "enabled": true,
  "block_on_match": true,
  "patterns": [
    "Traceback \\(most recent call last\\)",
    "AssertionError",
    "AttributeError",
    "IntegrityError",
    "AccessError",
    "psycopg2\\.Error"
  ]
}
```

`block_on_match: false` → warn only (emit non-blocking additionalContext).

Bounded: skip nếu `stop_hook_active` (Claude đã re-prompt 1 lần).
Idempotent: nếu turn vừa rồi đã chứa text "debug-troubleshoot" hoặc
`[assumption]` → skip.

Fails open: lỗi parse / IO → exit 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, split_current_turn, run_main_safe)

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/debug.json"

DEFAULT_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"\bAssertionError\b",
    r"\bAttributeError\b",
    r"\bIntegrityError\b",
    r"\bKeyError\b",
    r"\bTypeError\b",
    r"\bValueError\b",
    r"\bImportError\b",
    r"psycopg2\.errors\.",
]

# v0.6.1 split — bare exception names are WEAK and only count when
# wrapped in traceback context (File "...", line N | Traceback caret).
# Reading a Python source file containing `raise ValueError(...)`
# previously false-triggered → duplicate clarification-gate output.
# Framework-specific exception namespaces (e.g. odoo.exceptions.*,
# werkzeug.exceptions.*, django.core.exceptions.*) live in the runtime
# config `.agent-toolkit/debug.json`'s `patterns` field — installer
# pulls the right `debug.<framework>.json` overlay at install time.
STRONG_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"psycopg2\.errors\.[A-Z]\w*",
    r'^\s*File "[^"]+", line \d+',
    r"\bUnhandledPromiseRejection\b",
]

WEAK_PATTERNS = [
    r"\bAssertionError\b",
    r"\bAttributeError\b",
    r"\bIntegrityError\b",
    r"\bAccessError\b",
    r"\bKeyError\b",
    r"\bTypeError\b",
    r"\bValueError\b",
    r"\bImportError\b",
    r"\bRuntimeError\b",
]

CONTEXT_WINDOW_CHARS = 200
TRACEBACK_CONTEXT = re.compile(
    r'File "[^"]+", line \d+|Traceback|^\s*\^+\s*$',
    re.MULTILINE,
)

# If response contains any of these markers, the agent already self-disclaimed
# or is actively debugging — skip the sentry.
SKIP_MARKERS = (
    "[assumption]",
    "[chưa fix]",
    "[chưa verify]",
    "debug-troubleshoot",
    "debug-sentry: skip",
    "root cause đã xác định",
    "fix applied:",
)


def _exit_allow() -> None:
    sys.exit(0)


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _emit_warn(reason: str) -> None:
    """Non-blocking — emit additionalContext only."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": reason,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _load_config(workspace: Path) -> Dict[str, Any]:
    path = workspace / CONFIG_REL
    if not path.exists():
        return {"enabled": True, "block_on_match": True, "patterns": DEFAULT_PATTERNS}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"enabled": True, "block_on_match": True, "patterns": DEFAULT_PATTERNS}
    if not isinstance(cfg, dict):
        return {"enabled": True, "block_on_match": True, "patterns": DEFAULT_PATTERNS}
    cfg.setdefault("enabled", True)
    cfg.setdefault("block_on_match", True)
    if not cfg.get("patterns"):
        cfg["patterns"] = DEFAULT_PATTERNS
    return cfg


_read_transcript = read_jsonl_transcript
_split_current_turn = split_current_turn


def _extract_text_and_results(turn: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Return (assistant_text, tool_results_text) for the turn."""
    asst_parts: List[str] = []
    result_parts: List[str] = []
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if role == "assistant":
            if isinstance(content, str):
                asst_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        asst_parts.append(block.get("text") or "")
        elif role == "user":
            # tool_result content for tool_use is delivered as a user message
            # with content blocks of type tool_result.
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        c = block.get("content")
                        if isinstance(c, str):
                            result_parts.append(c)
                        elif isinstance(c, list):
                            for sub in c:
                                if isinstance(sub, dict) and sub.get("type") == "text":
                                    result_parts.append(sub.get("text") or "")
    return ("\n".join(asst_parts), "\n".join(result_parts))


def _matches(text: str, patterns: List[str]) -> List[str]:
    """Return pattern hits.

    v0.6.1 logic:
      - STRONG_PATTERNS match → count immediately (clear runtime shape).
      - WEAK_PATTERNS only count when a TRACEBACK_CONTEXT signal
        (File "...", line N | Traceback | caret) appears within
        ±CONTEXT_WINDOW_CHARS of the match.

    Custom `patterns` arg (project debug.json override) are treated as
    STRONG (no context check) — DEV explicitly opted in.
    """
    seen: List[str] = []
    is_default = patterns is DEFAULT_PATTERNS or patterns == DEFAULT_PATTERNS
    if is_default:
        for pat in STRONG_PATTERNS:
            try:
                if re.search(pat, text, re.MULTILINE):
                    seen.append(pat)
            except re.error:
                continue
        for pat in WEAK_PATTERNS:
            try:
                rx = re.compile(pat, re.MULTILINE)
            except re.error:
                continue
            for m in rx.finditer(text):
                start = max(0, m.start() - CONTEXT_WINDOW_CHARS)
                end = min(len(text), m.end() + CONTEXT_WINDOW_CHARS)
                if TRACEBACK_CONTEXT.search(text[start:end]):
                    seen.append(pat)
                    break
        return seen
    # Legacy / project-customized patterns.
    for pat in patterns:
        try:
            if re.search(pat, text, re.MULTILINE):
                seen.append(pat)
        except re.error:
            continue
    return seen


def _has_skip_marker(text: str) -> bool:
    low = text.lower()
    return any(marker.lower() in low for marker in SKIP_MARKERS)


def _format_reason(asst_text: str, tool_text: str, matched: List[str]) -> str:
    # Trim sample to 320 chars
    combined = (asst_text + "\n" + tool_text).strip()
    sample = combined[:320].rstrip()
    if len(combined) > 320:
        sample += "…"
    return (
        "[debug-sentry] Turn vừa rồi phát hiện traceback / exception NHƯNG response "
        "chưa root-cause + chưa fix + chưa tag `[assumption]`. Trước khi chốt, làm 1 "
        "trong 2:\n\n"
        f"1. Mở skill `<stack>-<version>-debug-troubleshoot` → xác định root cause + "
        f"apply fix. Patterns khớp ({len(matched)}): " + ", ".join(matched[:5]) + ".\n"
        "2. Hoặc nếu chưa đủ thông tin để fix → sửa response gắn `[assumption]` "
        "cho phần liên quan traceback, ghi rõ cần input gì từ user.\n\n"
        "Trích đoạn có traceback:\n"
        f"---\n{sample}\n---\n\n"
        "Bỏ qua audit cho turn này: thêm `debug-sentry: skip` vào response (chỉ "
        "dùng khi traceback là expected, ví dụ test đang demo error path)."
    )


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_allow()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_allow()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_allow()

    # Don't loop forever
    if envelope.get("stop_hook_active"):
        _exit_allow()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    cfg = _load_config(workspace)
    if not cfg.get("enabled"):
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
    asst_text, tool_text = _extract_text_and_results(turn)

    if not asst_text and not tool_text:
        _exit_allow()

    if _has_skip_marker(asst_text):
        _exit_allow()

    patterns = cfg.get("patterns") or DEFAULT_PATTERNS
    matched = _matches(tool_text + "\n" + asst_text, patterns)
    if not matched:
        _exit_allow()

    reason = _format_reason(asst_text, tool_text, matched)
    if cfg.get("block_on_match"):
        _emit_block(reason)
    else:
        _emit_warn(reason)
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
