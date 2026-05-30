#!/usr/bin/env python
"""Stop hook — BLOCK 'done/verified' claim if turn had Edit on spec-tracked file
but `/verify` was NOT run.

Closes the last enforcement gap: previously verify_nudge merely SUGGESTED running
/verify after Edit; agent could ignore and claim "done". This hook detects the
combination [Edit happened] + [Edit target is in an implementing/gaps-found spec]
+ [final text claims completion] + [no /verify or run_python_tests in turn] →
BLOCK with re-emit directive.

Detection logic
---------------
For the current turn (between last user message and final assistant):
  1. ANY tool_use with name in {Edit, Write, MultiEdit} on a file path that
     a spec at status implementing/gaps-found references?
  2. Final assistant text contains completion claim (regex on done/ready/
     verified/complete/xong/hoàn thành/đã fix/ready to merge)?
  3. NO /verify run AND no run_python_tests AND no equivalent perturb-test
     in this turn?

If all three → BLOCK.

Escape hatch: agent can prepend `verify-gate: skip` to response (e.g. when
work-in-progress, intentionally not closing the loop yet).

Loops bounded: `stop_hook_active` short-circuits.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, split_current_turn,
    find_workspace_root, run_main_safe, get_enforce_mode)
from _patterns import (  # noqa: E402
    COMPLETION_RE as _COMPLETION_RE,
    VERIFY_INVOCATION_RE as _VERIFY_INVOCATION_RE,
    SPEC_STATUS_RE as _STATUS_RE,
    SPEC_SLUG_RE as _SPEC_SLUG_RE,
    IMPLEMENTING_STATUSES,
)

wrap_utf8_stdio()


HOOK_NAME = "post_edit_verify_gate"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
VERIFY_TOOL_PATTERNS = (
    "mcp__",   # any postgres/test/playwright probe counts
)
SKIP_MARKER = "verify-gate: skip"


def _exit_allow() -> None:
    sys.exit(0)


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _emit_warn(reason: str) -> None:
    # v0.27 — emit advisory to stderr, do NOT block.
    sys.stderr.write(f"[post-edit-verify-gate] warn: {reason}\n")
    sys.exit(0)


_read_transcript = read_jsonl_transcript
_split_current_turn = split_current_turn


def _edited_paths_in_turn(turn: List[Dict[str, Any]]) -> List[str]:
    paths: List[str] = []
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            if name not in EDIT_TOOLS:
                continue
            inp = block.get("input") or {}
            fp = inp.get("file_path") or ""
            if fp:
                paths.append(fp)
    return paths


def _turn_has_verify_invocation(turn: List[Dict[str, Any]], text: str) -> bool:
    # Either agent text mentions /verify / run_python_tests / perturb-test,
    # OR a tool_use named mcp__*run_python_tests / *postgres_read_query happened.
    if _VERIFY_INVOCATION_RE.search(text):
        return True
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "tool_use":
                continue
            name = (block.get("name") or "").lower()
            if "run_python_tests" in name or "postgres_read_query" in name:
                return True
            if name.startswith("mcp__playwright__"):
                return True
    return False


def _extract_text(turn: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    parts.append(block.get("text") or "")
    return "\n".join(parts)


_find_workspace_root = find_workspace_root


def _file_in_implementing_spec(workspace: Path, file_path: str) -> Optional[str]:
    """Return spec slug if file is referenced by any implementing/gaps-found spec.

    Uses verify_nudge's mtime cache if available for O(active) scan.
    """
    specs_dir = workspace / ".agent-toolkit" / "specs"
    if not specs_dir.is_dir():
        return None
    try:
        rel = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel = file_path
    basename = Path(file_path).name
    # rglob picks up both branch-scoped (`<branch>/<slug>.md`) and legacy
    # flat (`<slug>.md`) layouts — consistent with verify_nudge / verify_lint /
    # analyze_halt_gate which all rglob. Previously glob("*.md") meant
    # branch-scoped specs slipped past this gate.
    for path in specs_dir.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not fm:
            continue
        status_m = _STATUS_RE.search(fm.group(1))
        if not status_m or status_m.group(1).lower() not in IMPLEMENTING_STATUSES:
            continue
        if rel in text:
            slug_m = _SPEC_SLUG_RE.search(fm.group(1))
            return slug_m.group(1) if slug_m else path.stem
        if (len(basename) >= 12 or "_" in basename) and basename in text:
            slug_m = _SPEC_SLUG_RE.search(fm.group(1))
            return slug_m.group(1) if slug_m else path.stem
    return None


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

    text = _extract_text(turn)
    if not text:
        _exit_allow()
    if SKIP_MARKER in text.lower():
        _exit_allow()

    # Condition 1: any Edit in this turn?
    edited = _edited_paths_in_turn(turn)
    if not edited:
        _exit_allow()

    # Condition 2: does the final text claim completion?
    if not _COMPLETION_RE.search(text):
        _exit_allow()

    # Condition 3: any Edit on a file in implementing/gaps-found spec?
    workspace_str = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = _find_workspace_root(Path(workspace_str)) or Path(workspace_str).resolve()
    matched_spec: Optional[str] = None
    for fp in edited:
        slug = _file_in_implementing_spec(workspace, fp)
        if slug:
            matched_spec = slug
            break
    if not matched_spec:
        _exit_allow()

    # Condition 4: verify NOT invoked in turn?
    if _turn_has_verify_invocation(turn, text):
        _exit_allow()

    reason = (
        f"Turn này có Edit trên file thuộc spec "
        f"`{matched_spec}` (status implementing/gaps-found) VÀ response "
        "claim completion (done/ready/verified/xong/...) — NHƯNG agent CHƯA "
        f"chạy `/verify {matched_spec}` hoặc tương đương trong turn.\n\n"
        "Theo ADR-006 + ADR-007: code đã Edit phải qua /verify trước khi "
        "claim done. Lý do: skill `verify-feature` Bước 1.5 + Bước 8 ép "
        "acceptance_evals coverage, mà chỉ /verify mới chạy được.\n\n"
        f"Sửa: chạy `/verify {matched_spec}` (hoặc tương đương run_python_tests "
        "/ postgres probe / Playwright perturb-test) rồi re-emit response.\n\n"
        "Override 1 lần (work-in-progress, intentionally not closing): thêm "
        f"`{SKIP_MARKER}` vào response."
    )

    # v0.27 enforce-mode aware: warn-by-default (cuts paralysis when
    # evidence_audit / scope_completeness_gate already raise voice on the
    # same claim). DEV opts back into block via enforce_mode.json.
    mode = get_enforce_mode(workspace, HOOK_NAME, default="warn")
    if mode == "off":
        _exit_allow()
    if mode == "warn":
        _emit_warn(reason)
    _emit_block(f"[post-edit-verify-gate] {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
