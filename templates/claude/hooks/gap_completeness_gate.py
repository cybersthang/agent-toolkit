#!/usr/bin/env python
"""Stop hook — gap-completeness gate (v0.19.0).

Blocks Stop when the assistant claims `done | verified | xong | hoàn tất`
while `.agent-toolkit/.open_gaps.json` lists entries with `status: open`.

Enforces DEV contract: "After implement+review, fix ALL gaps; only
unfixable ones get escalated." Without this hook, agent drip-feeds —
each "is it done" check surfaces NEW gaps that should have been caught
in the first review (`feedback_exhaustive_analysis` complaint, 2026-05-08).

Resolution mechanisms (3 tiers):
  1. **Per-gap defer**: response contains `gap-defer: G<N> <reason ≥ 8 chars>`
  2. **Per-gap cant-fix**: response contains `gap-cant-fix: G<N> <reason>`
     (escalates to DEV via stderr surface)
  3. **Whole-gate bypass**: prior prompt contains
     `bypass-gap-gate: <reason ≥ 8 chars>` (audit-logged)

Skip cases (silent allow, exit 0):
  - `stop_hook_active` env var set (recursion break)
  - `.agent-toolkit/.autonomy_active.json` fresh (auto-chain in progress;
    /implement resolves gaps iteratively via /verify retries — gate
    fires only when agent attempts FINAL stop with open gaps)
  - `.open_gaps.json` missing or empty
  - All open gap entries have `status` ∈ {fixed, deferred, cant_fix, stale}
  - Bypass token consumed from prior UserPromptSubmit

Enforce mode via `get_enforce_mode(workspace, "gap_completeness_gate")`:
  - `block` (default — `feedback_exhaustive_analysis` is strict)
  - `warn` (allow + stderr nudge)
  - `off` (silent allow)

Fails open on any unexpected error.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import run_main_safe, emit_fire_event, get_enforce_mode  # noqa: E402
from _patterns import (  # noqa: E402
    DONE_CLAIM_GAP_RE, GAP_DEFER_RE, GAP_CANT_FIX_RE, GAP_LIST_EMIT_RE,
)

# UTF-8 stdin/stdout/stderr — Vietnamese-friendly + Windows-safe.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# Kill-switch — toolkit-wide disable.
if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
    sys.exit(0)


OPEN_GAPS_REL = ".agent-toolkit/.open_gaps.json"
AUTONOMY_REL = ".agent-toolkit/.autonomy_active.json"
STALE_TTL_SECONDS = 86400  # 24 h — see Risks/R2 in spec v0.19
HOOK_NAME = "gap_completeness_gate"


def _exit_allow(detail: Optional[str] = None) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="allow", detail=detail)
    except Exception:
        pass
    return 0


def _exit_block(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="block", detail=reason[:200])
    except Exception:
        pass
    sys.stderr.write(f"[gap-completeness-gate] block: {reason}\n")
    return 2


def _exit_warn(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=reason[:200])
    except Exception:
        pass
    sys.stderr.write(f"[gap-completeness-gate] warn: {reason}\n")
    return 0


def _find_workspace(cwd: Optional[str]) -> Path:
    if cwd:
        return Path(cwd).resolve()
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def _read_state(path: Path) -> Optional[Dict[str, Any]]:
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
    """Mirror clarification_gate_enforcer logic: auto-chain in progress
    means the agent is mid-fix loop — gate must NOT fire mid-chain.
    Gate fires only on FINAL stop after autonomy expires / cuts."""
    data = _read_state(workspace / AUTONOMY_REL)
    if not data:
        return False
    expires = data.get("expires_at")
    if not expires:
        return True
    try:
        from datetime import datetime
        exp_dt = datetime.fromisoformat(expires)
        now_dt = datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now()
        return now_dt < exp_dt
    except (ValueError, TypeError):
        return True


def _capture_new_gap_emissions(state: Dict[str, Any],
                               response_text: str) -> Dict[str, Any]:
    """Scan response for `G<N> — <desc>` patterns; append as `status: open`
    entries to state (skip if id already tracked). Caller invokes BEFORE
    resolution-marker pass so a turn can emit + immediately resolve a gap
    in the same response (rare but legal)."""
    gaps = state.setdefault("gaps", [])
    if not isinstance(gaps, list):
        state["gaps"] = []
        gaps = state["gaps"]
    existing_ids = {g.get("id") for g in gaps if isinstance(g, dict)}
    now = int(time.time())
    for m in GAP_LIST_EMIT_RE.finditer(response_text):
        gid = f"G{m.group(1)}"
        desc = m.group(2).strip().rstrip(".,;")
        if gid in existing_ids:
            continue
        gaps.append({
            "id": gid,
            "surfaced_ts": now,
            "desc": desc[:200],
            "status": "open",
            "resolution_ts": None,
            "resolution_reason": None,
        })
        existing_ids.add(gid)
    return state


def _apply_resolution_markers(state: Dict[str, Any],
                              response_text: str) -> Dict[str, Any]:
    """Walk gap-defer / gap-cant-fix markers in response, flip matching
    gap entries. Mutates and returns state. Does NOT write back to disk;
    caller persists on allow path."""
    gaps = state.get("gaps") or []
    if not isinstance(gaps, list):
        return state
    now = int(time.time())

    for m in GAP_DEFER_RE.finditer(response_text):
        gid = f"G{m.group(1)}"
        reason = m.group(2).strip()
        for g in gaps:
            if isinstance(g, dict) and g.get("id") == gid and g.get("status") == "open":
                g["status"] = "deferred"
                g["resolution_ts"] = now
                g["resolution_reason"] = reason

    for m in GAP_CANT_FIX_RE.finditer(response_text):
        gid = f"G{m.group(1)}"
        reason = m.group(2).strip()
        for g in gaps:
            if isinstance(g, dict) and g.get("id") == gid and g.get("status") == "open":
                g["status"] = "cant_fix"
                g["resolution_ts"] = now
                g["resolution_reason"] = reason

    # Stale auto-expire (Risk R2): gaps older than TTL → status stale.
    for g in gaps:
        if not isinstance(g, dict):
            continue
        if g.get("status") != "open":
            continue
        surfaced = int(g.get("surfaced_ts") or 0)
        if surfaced and now - surfaced > STALE_TTL_SECONDS:
            g["status"] = "stale"
            g["resolution_ts"] = now
            g["resolution_reason"] = "auto-expired (> 24h)"

    state["gaps"] = gaps
    return state


def _consume_bypass(workspace: Path, state: Dict[str, Any]) -> Optional[str]:
    """Check if the prior UserPromptSubmit captured a bypass token into
    `.open_gaps.json` `pending_bypass` field. Consume + persist (mutate
    state in-place); return reason or None."""
    bypass = state.get("pending_bypass")
    if not isinstance(bypass, dict):
        return None
    ts = int(bypass.get("ts") or 0)
    reason = bypass.get("reason") or ""
    if not reason or int(time.time()) - ts > 600:
        # Stale or empty — clean.
        state.pop("pending_bypass", None)
        return None
    # Consume.
    state.pop("pending_bypass", None)
    history = state.setdefault("bypass_history", [])
    if isinstance(history, list):
        history.append({"ts": ts, "reason": reason})
        # Cap history to last 50.
        state["bypass_history"] = history[-50:]
    return reason


def _extract_assistant_text(envelope: Dict[str, Any]) -> str:
    """Pull current assistant response text from the Stop envelope.
    Mirrors clarification_gate_enforcer pattern."""
    response = envelope.get("response")
    if isinstance(response, str):
        return response
    if isinstance(response, list):
        out: List[str] = []
        for block in response:
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(block.get("text") or "")
        return "\n".join(out)
    return ""


def _persist(state: Dict[str, Any], path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    except OSError:
        pass


def _main() -> int:
    # Recursion break — Claude Code sets this when Stop fires a sub-Stop.
    if os.environ.get("stop_hook_active") == "true":
        return _exit_allow(detail="stop_hook_active")

    raw = sys.stdin.read()
    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return _exit_allow(detail="bad-json")

    workspace = _find_workspace(envelope.get("cwd"))
    gaps_path = workspace / OPEN_GAPS_REL

    state = _read_state(gaps_path) or {"version": 1, "gaps": []}

    # Auto-chain mid-flight: do not fire during /implement loop.
    if _autonomy_active(workspace):
        return _exit_allow(detail="autonomy_active")

    response_text = _extract_assistant_text(envelope)

    # Whole-gate bypass consumed from prior UserPromptSubmit.
    bypass_reason = _consume_bypass(workspace, state)
    if bypass_reason:
        _persist(state, gaps_path)
        return _exit_allow(detail=f"bypass:{bypass_reason[:80]}")

    # Capture NEW gap emissions in this response first (so a turn can
    # emit + resolve in one pass if needed).
    state = _capture_new_gap_emissions(state, response_text)

    # Apply resolution markers (defer / cant_fix / stale-auto-expire)
    # before deciding whether to block.
    state = _apply_resolution_markers(state, response_text)

    # Count remaining open gaps.
    open_gaps = [
        g for g in state.get("gaps", [])
        if isinstance(g, dict) and g.get("status") == "open"
    ]

    # If response doesn't claim done at all, just persist mutations + allow.
    if not DONE_CLAIM_GAP_RE.search(response_text):
        _persist(state, gaps_path)
        return _exit_allow(detail=f"no-done-claim;open={len(open_gaps)}")

    # Done claim WITH open gaps → block / warn / off based on enforce mode.
    if not open_gaps:
        _persist(state, gaps_path)
        return _exit_allow(detail="all-resolved")

    # Build user-facing reason.
    lines = [
        f"Turn này claim done nhưng còn {len(open_gaps)} gap chưa resolve:",
    ]
    for g in open_gaps[:10]:
        gid = g.get("id", "?")
        desc = (g.get("desc") or "")[:120]
        lines.append(f"  {gid} — {desc}")
    if len(open_gaps) > 10:
        lines.append(f"  ... và {len(open_gaps) - 10} gap khác")
    lines.append("")
    lines.append(
        "Per `feedback_exhaustive_analysis`: phải resolve mỗi gap (fix HOẶC "
        "mark deferred với reason) TRƯỚC khi claim done. 3 cách:"
    )
    lines.append("  1. Fix gap → re-emit response, gap tự auto-clear")
    lines.append("  2. `gap-defer: G<N> <reason ≥ 8 chars>` — punt to next sprint")
    lines.append("  3. `gap-cant-fix: G<N> <reason>` — escalate to DEV")
    lines.append(
        "Whole-gate bypass single-shot: DEV gõ `bypass-gap-gate: <reason>` ở prompt kế."
    )

    reason = "\n".join(lines)

    # Persist mutations (defer / cant_fix applied but residual open).
    _persist(state, gaps_path)

    mode = get_enforce_mode(workspace, HOOK_NAME, default="block")
    if mode == "off":
        return _exit_allow(detail=f"off;open={len(open_gaps)}")
    if mode == "warn":
        return _exit_warn(reason)
    # Default: block.
    return _exit_block(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(_main))
