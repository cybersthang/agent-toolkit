#!/usr/bin/env python
"""Stop hook — enforce clarification-gate response shape contract.

When intent_router (UserPromptSubmit) suggested the `clarification-gate`
skill for the current turn, this hook verifies that the agent's response
text contains all 4 required markers:
  - UNDERSTANDING
  - ASSUMPTIONS
  - QUESTIONS
  - Searched:

Missing any → enforce per `get_enforce_mode(workspace, 'clarification_gate_enforcer')`:
  - `block` (D8 default for new contract-enforcement hooks): exit 2 + stderr.
  - `warn`: exit 0 + stderr cảnh báo.

Skips (no shape check, exit 0):
  - `stop_hook_active` (recursion break)
  - `.autonomy_active.json` fresh (/go or /implement in progress)
  - `.last_intent_suggested.json` missing OR doesn't list clarification-gate
  - state file > 600s old (stale, not this turn)
  - `.skip_clarification_next.json` fresh (single-use escape token — consume)

Wired into `templates/claude/settings.json` Stop chain after
`evidence_audit.py`. Fails open on any unexpected error.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import run_main_safe, emit_fire_event, get_enforce_mode, parse_expires_at  # noqa: E402
from _audit.transcript import read_transcript, split_current_turn, extract_text_and_tools  # noqa: E402

# UTF-8 stdin/stdout (Vietnamese-friendly).
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LAST_INTENT_REL = ".agent-toolkit/.last_intent_suggested.json"
SKIP_REL = ".agent-toolkit/.skip_clarification_next.json"
AUTONOMY_REL = ".agent-toolkit/.autonomy_active.json"

STATE_TTL_SECONDS = 600
SKIP_CLARIFICATION_TTL_SECONDS = 600  # must match intent_router.py constant
HOOK_NAME = "clarification_gate_enforcer"

# 4 marker literals enforced (D5/D10 — no override at v0.13.0).
REQUIRED_MARKERS = ("UNDERSTANDING", "ASSUMPTIONS", "QUESTIONS", "Searched:")


def _exit_allow(workspace: Path, bypass: Optional[List[str]] = None,
                detail: Optional[str] = None) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="allow",
                        detail=detail or (",".join(bypass) if bypass else None))
    except Exception:
        pass
    return 0


def _exit_block(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="block", detail=reason[:200])
    except Exception:
        pass
    sys.stderr.write(f"[clarification-gate-enforcer] block: {reason}\n")
    # v0.21 E6 (UX improvement) — structured docs reference + bypass tail.
    sys.stderr.write(
        "  · See docs: docs/hooks/clarification_gate_enforcer.md\n"
        "  · Bypass once: `skip-clarification: <reason>` in next user prompt "
        "OR ensure all 4 markers (UNDERSTANDING/ASSUMPTIONS/QUESTIONS/Searched:) present\n"
    )
    return 2


def _exit_warn(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=reason[:200])
    except Exception:
        pass
    sys.stderr.write(f"[clarification-gate-enforcer] warn: {reason}\n")
    return 0


def _read_state(workspace: Path, rel: str) -> Optional[Dict[str, Any]]:
    path = workspace / rel
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _autonomy_active(workspace: Path) -> bool:
    data = _read_state(workspace, AUTONOMY_REL)
    if not data:
        return False
    expires = data.get("expires_at")
    if not expires:
        return True
    from datetime import datetime
    exp_dt = parse_expires_at(expires)
    if exp_dt is None:
        return True  # parse fail → treat as active (fail-open)
    now_dt = datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now()
    return now_dt < exp_dt


def _consume_skip_token(workspace: Path) -> Optional[str]:
    """Read skip-clarification state file; if fresh, unlink + return reason.
    Returns None if no file or expired."""
    data = _read_state(workspace, SKIP_REL)
    if not data:
        return None
    ts = int(data.get("ts") or 0)
    ttl = int(data.get("ttl_seconds") or SKIP_CLARIFICATION_TTL_SECONDS)
    if int(time.time()) - ts > ttl:
        # Expired — clean up.
        try:
            (workspace / SKIP_REL).unlink()
        except OSError:
            pass
        return None
    reason = data.get("reason") or ""
    if not reason:
        return None
    # Single-use: consume by unlinking.
    try:
        (workspace / SKIP_REL).unlink()
    except OSError:
        pass
    return reason


def _last_intent_relevant(workspace: Path) -> bool:
    """Return True if the last UserPromptSubmit suggested clarification-gate
    AND the suggestion is still fresh (< STATE_TTL_SECONDS old)."""
    data = _read_state(workspace, LAST_INTENT_REL)
    if not data:
        return False
    ts = int(data.get("ts") or 0)
    if int(time.time()) - ts > STATE_TTL_SECONDS:
        # Stale state — clean up + treat as no suggestion.
        try:
            (workspace / LAST_INTENT_REL).unlink()
        except OSError:
            pass
        return False
    skills = data.get("skills") or []
    return isinstance(skills, list) and "clarification-gate" in skills


def _extract_response_text(envelope: Dict[str, Any]) -> str:
    """Pull the assistant response text from the Stop envelope.

    Claude Code Stop hook envelopes carry the conversation via
    `transcript_path` (JSONL), NOT inline response fields like `response`
    or `response_text`. Read the transcript, slice the current turn,
    and return the assistant text.

    Returns empty string when it cannot read the response (the caller then
    fails OPEN — never blocks on an unreadable response). On a tool-call turn
    the current-turn slice may carry no text yet, so we fall back to the last
    assistant message in the transcript tail instead of returning "" (which
    used to false-block every tool-call turn — R8).
    """
    transcript_path = envelope.get("transcript_path")
    if not transcript_path:
        return ""
    tpath = Path(transcript_path)
    if not tpath.exists():
        return ""
    messages = read_transcript(tpath)
    if not messages:
        return ""
    turn = split_current_turn(messages)
    text, _ = extract_text_and_tools(turn)
    if text and text.strip():
        return text
    # Fallback: tool-call turn → the current-turn slice had no flushed text.
    # Walk the transcript tail for the last assistant message's text so the
    # marker check still runs instead of false-blocking the whole turn.
    for msg in reversed(messages):
        m = msg.get("message") if isinstance(msg.get("message"), dict) else msg
        if isinstance(m, dict) and m.get("role") == "assistant":
            content = m.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                joined = "\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
                if joined.strip():
                    return joined
            break
    return ""


def _missing_markers(response: str) -> List[str]:
    return [m for m in REQUIRED_MARKERS if m not in response]


def _check_searched_coverage(response: str, workspace: Path) -> None:
    """5-layer audit: count Q<N> headers vs Searched: lines in QUESTIONS block.

    If the response has more Q headers than Searched: lines, emit a
    warn-only fire event (no block). This catches questions that skipped
    code-lookup and may be answerable from the codebase.
    """
    # Extract QUESTIONS section (between QUESTIONS and end or next section).
    q_section_match = re.search(r"QUESTIONS\s*\n(.*?)(?:\n[A-Z]{4,}|\Z)",
                                response, re.DOTALL | re.IGNORECASE)
    if not q_section_match:
        return
    q_section = q_section_match.group(1)
    q_count = len(re.findall(r"\bQ\d+[:\.]", q_section))
    searched_count = len(re.findall(r"\bSearched:", response))
    if q_count > 0 and searched_count < q_count:
        detail = f"Q-count={q_count} > Searched:-count={searched_count}: some questions may be answerable from code"
        sys.stderr.write(f"[clarification-gate-enforcer] warn: {detail}\n")
        try:
            emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=detail[:200])
        except Exception:
            pass


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return 0  # Fail open on malformed envelope.

    # Recursion break (per Claude Code Stop hook contract).
    if envelope.get("stop_hook_active"):
        return _exit_allow(Path("."), bypass=["stop_hook_active"])

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    # Skip path 1: autonomy active (/go or /implement) → never enforce.
    if _autonomy_active(workspace):
        return _exit_allow(workspace, bypass=["autonomy"])

    # Skip path 2: no clarification-gate suggestion this turn → silent no-op.
    if not _last_intent_relevant(workspace):
        return _exit_allow(workspace, detail="no-suggestion")

    # Skip path 3: escape token present → single-use consume + allow.
    skip_reason = _consume_skip_token(workspace)
    if skip_reason:
        return _exit_allow(workspace, bypass=[f"escape-token:{skip_reason}"])

    # Shape check.
    response = _extract_response_text(envelope)
    if not response.strip():
        # Couldn't read the response (e.g. final text not yet flushed on a
        # tool-call turn) — cannot judge markers → fail OPEN, never block on
        # an unreadable response (R8).
        return _exit_allow(workspace, detail="unreadable-response-fail-open")
    missing = _missing_markers(response)
    if not missing:
        # All 4 markers present — run 5-layer Searched: coverage audit (warn only).
        _check_searched_coverage(response, workspace)

        # v0.21 T15 (M12): inject deferred skills (downstream skills
        # suppressed during gate turn) as additionalContext.
        intent_state = _read_state(workspace, LAST_INTENT_REL) or {}
        deferred = intent_state.get("deferred_skills") or []
        if isinstance(deferred, list) and deferred:
            skill_list = ", ".join(f"`{s}`" for s in deferred)
            reminder = (
                f"[clarification-gate-enforcer] Gate satisfied. "
                f"Skills queued for next turn: {skill_list}. "
                f"Open these SKILL.md files when you act on the DEV answer."
            )
            try:
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "Stop",
                        "additionalContext": reminder,
                    }
                }, ensure_ascii=False))
            except Exception:
                pass

        # T15 round 1: Consume last_intent_suggested.json so gate doesn't
        # re-fire on subsequent turns in the same session.
        try:
            (workspace / LAST_INTENT_REL).unlink(missing_ok=True)
        except (OSError, TypeError):
            try:
                intent_path = workspace / LAST_INTENT_REL
                if intent_path.exists():
                    intent_path.unlink()
            except OSError:
                pass
        return _exit_allow(workspace, detail="shape-ok")

    # Missing markers → enforce per mode.
    mode = get_enforce_mode(workspace, HOOK_NAME, default="block")
    reason = f"missing markers: {', '.join(missing)}"
    if mode == "block":
        return _exit_block(reason)
    return _exit_warn(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
