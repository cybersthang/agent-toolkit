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
from _common import run_main_safe, emit_fire_event, get_enforce_mode  # noqa: E402

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
    # Check expires_at if present (ISO string); otherwise treat as active.
    expires = data.get("expires_at")
    if not expires:
        return True
    try:
        # Parse ISO 8601 — strip timezone for naive compare against now.
        # Reasonable fallback: if parse fails, treat as active (fail-open).
        from datetime import datetime
        # datetime.fromisoformat handles "+07:00" in 3.7+.
        exp_dt = datetime.fromisoformat(expires)
        # Compare in UTC if tz-aware; else naive vs naive.
        now_dt = datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now()
        return now_dt < exp_dt
    except (ValueError, TypeError):
        return True


def _consume_skip_token(workspace: Path) -> Optional[str]:
    """Read skip-clarification state file; if fresh, unlink + return reason.
    Returns None if no file or expired."""
    data = _read_state(workspace, SKIP_REL)
    if not data:
        return None
    ts = int(data.get("ts") or 0)
    ttl = int(data.get("ttl_seconds") or 300)
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

    Claude Code envelope shape varies; try common fields in order. Falls
    back to empty string (treated as 0-marker → enforce).
    """
    for key in ("response", "response_text", "assistant_message", "text"):
        v = envelope.get(key)
        if isinstance(v, str) and v.strip():
            return v
    # Newer envelope nests under transcript / messages — best-effort.
    messages = envelope.get("messages") or envelope.get("transcript")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            content = last.get("content") or last.get("text") or ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # Anthropic-style list of content blocks.
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text") or "")
                return "\n".join(parts)
    return ""


def _missing_markers(response: str) -> List[str]:
    return [m for m in REQUIRED_MARKERS if m not in response]


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
    missing = _missing_markers(response)
    if not missing:
        return _exit_allow(workspace, detail="shape-ok")

    # Missing markers → enforce per mode.
    mode = get_enforce_mode(workspace, HOOK_NAME, default="block")
    reason = f"missing markers: {', '.join(missing)}"
    if mode == "block":
        return _exit_block(reason)
    return _exit_warn(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
