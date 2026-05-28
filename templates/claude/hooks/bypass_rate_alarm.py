#!/usr/bin/env python
# v0.23 R1 — bypass-rate alarm Stop hook
"""Stop hook — bypass-rate alarm (v0.23 R1).

Reads the shared hook fire-log ring buffer
(`.agent-toolkit/.hook_fire_log.json`), groups events by hook, and
computes the *bypass rate* per hook over a rolling window (default 7
days). If ANY hook's bypass rate exceeds a threshold (default 5%), the
hook surfaces a non-blocking `additionalContext` warning so DEV knows
that a guard is being routinely bypassed — "bypass becoming routine =
security theatre".

A "bypass" event is any fire-log event whose `verdict` is one of the
bypass-shaped verdicts (`bypass`, `skip`, `skipped`, `override`) OR
whose `detail` begins with `bypass`. The denominator is the total
number of events for that hook in the window (min `min_events` to avoid
noisy small samples).

Config: `.agent-toolkit/bypass_alarm.json` (fail-open if missing):
    {
      "threshold_pct": 5,     // alarm when bypass rate > this %
      "window_days": 7,       // rolling window size in days
      "min_events": 10        // skip hooks with fewer total events
    }

Default WARN-only (informational; never blocks). `enforce_mode.json`
`per_hook.bypass_rate_alarm: "block"` promotes it to a blocking gate.

Skip cases (silent allow, exit 0):
  - `AGENT_TOOLKIT_DISABLE=1` kill-switch.
  - `stop_hook_active` recursion break.
  - Config file missing (feature opt-in — no config → skip silently).
  - Fire-log missing / empty / unparseable.
  - No hook exceeds threshold.

Fails open on any unexpected error (run_main_safe wrapper).
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


FIRE_LOG_REL = ".agent-toolkit/.hook_fire_log.json"
CONFIG_REL = ".agent-toolkit/bypass_alarm.json"
HOOK_NAME = "bypass_rate_alarm"

DEFAULT_THRESHOLD_PCT = 5.0
DEFAULT_WINDOW_DAYS = 7
DEFAULT_MIN_EVENTS = 10

# Verdicts (case-insensitive) that count as a bypass for rate purposes.
_BYPASS_VERDICTS = {"bypass", "skip", "skipped", "override", "overridden"}


def _exit_allow(detail: Optional[str] = None) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="allow", detail=detail)
    except Exception:
        pass
    return 0


def _exit_warn(reason: str) -> int:
    """Non-blocking warning — surface via Stop additionalContext envelope."""
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=reason[:200])
    except Exception:
        pass
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": reason,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.stderr.write(f"[bypass-rate-alarm] warn: {reason}\n")
    return 0


def _exit_block(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="block", detail=reason[:200])
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.stderr.write(f"[bypass-rate-alarm] block: {reason}\n")
    return 2


def _find_workspace(cwd: Optional[str]) -> Path:
    if cwd:
        return Path(cwd).resolve()
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_config(workspace: Path) -> Optional[Dict[str, Any]]:
    """Return parsed config, or None when the feature is not opted in
    (config file missing) so the caller can skip silently."""
    data = _read_json(workspace / CONFIG_REL)
    if not isinstance(data, dict):
        return None
    cfg = {
        "threshold_pct": DEFAULT_THRESHOLD_PCT,
        "window_days": DEFAULT_WINDOW_DAYS,
        "min_events": DEFAULT_MIN_EVENTS,
    }
    try:
        if "threshold_pct" in data:
            cfg["threshold_pct"] = float(data["threshold_pct"])
        if "window_days" in data:
            cfg["window_days"] = int(data["window_days"])
        if "min_events" in data:
            cfg["min_events"] = int(data["min_events"])
    except (TypeError, ValueError):
        # Malformed values — fall back to defaults (fail-open).
        pass
    return cfg


def _load_events(workspace: Path) -> List[Dict[str, Any]]:
    data = _read_json(workspace / FIRE_LOG_REL)
    if isinstance(data, dict):
        events = data.get("events") or []
    elif isinstance(data, list):
        events = data
    else:
        events = []
    return [e for e in events if isinstance(e, dict)]


def _is_bypass_event(event: Dict[str, Any]) -> bool:
    verdict = str(event.get("verdict") or "").strip().lower()
    if verdict in _BYPASS_VERDICTS:
        return True
    detail = str(event.get("detail") or "").strip().lower()
    return detail.startswith("bypass")


def _compute_rates(events: List[Dict[str, Any]], cfg: Dict[str, Any]
                   ) -> List[Dict[str, Any]]:
    """Group events by hook within the rolling window, compute bypass
    rate. Returns a list of dicts for hooks exceeding the threshold AND
    meeting the min-events floor, sorted by rate descending."""
    now = int(time.time())
    window_s = int(cfg["window_days"]) * 86400
    cutoff = now - window_s if window_s > 0 else 0

    totals: Dict[str, int] = {}
    bypasses: Dict[str, int] = {}
    for e in events:
        ts = e.get("ts")
        try:
            ts_int = int(ts)
        except (TypeError, ValueError):
            continue
        if ts_int < cutoff:
            continue
        hook = str(e.get("hook") or "").strip()
        if not hook:
            continue
        totals[hook] = totals.get(hook, 0) + 1
        if _is_bypass_event(e):
            bypasses[hook] = bypasses.get(hook, 0) + 1

    threshold = float(cfg["threshold_pct"])
    min_events = int(cfg["min_events"])
    alarms: List[Dict[str, Any]] = []
    for hook, total in totals.items():
        if total < min_events:
            continue
        bypass_n = bypasses.get(hook, 0)
        rate = (bypass_n / total) * 100.0 if total else 0.0
        if rate > threshold:
            alarms.append({
                "hook": hook,
                "rate": rate,
                "bypasses": bypass_n,
                "total": total,
            })
    alarms.sort(key=lambda a: a["rate"], reverse=True)
    return alarms


def _build_reason(alarms: List[Dict[str, Any]], cfg: Dict[str, Any]) -> str:
    threshold = float(cfg["threshold_pct"])
    window_days = int(cfg["window_days"])
    lines: List[str] = []
    for a in alarms:
        lines.append(
            f"⚠️ BYPASS ALARM: {a['hook']} {a['rate']:.1f}% "
            f"over {window_days}d (>{threshold:g}% threshold). "
            f"Review ADR — bypass becoming routine = security theatre."
        )
        lines.append(
            f"   ({a['bypasses']}/{a['total']} fires bypassed in window)"
        )
    return "\n".join(lines)


def _main() -> int:
    # Recursion break.
    if os.environ.get("stop_hook_active") == "true":
        return _exit_allow(detail="stop_hook_active")

    raw = sys.stdin.read()
    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        envelope = {}

    workspace = _find_workspace(envelope.get("cwd"))

    cfg = _load_config(workspace)
    if cfg is None:
        # Feature not opted in (no config) — skip silently (fail-open).
        return _exit_allow(detail="no-config")

    events = _load_events(workspace)
    if not events:
        return _exit_allow(detail="no-events")

    alarms = _compute_rates(events, cfg)
    if not alarms:
        return _exit_allow(detail="under-threshold")

    reason = _build_reason(alarms, cfg)

    mode = get_enforce_mode(workspace, HOOK_NAME, default="warn")
    if mode == "off":
        return _exit_allow(detail=f"off;alarms={len(alarms)}")
    if mode == "block":
        return _exit_block(reason)
    # Default: warn (informational).
    return _exit_warn(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(_main))
