#!/usr/bin/env python
"""hook_health — aggregate hook telemetry into a single health report.

Reads ring-buffer logs that hooks write:
  - `.agent-toolkit/.hook_crash_log.json` (P9 v0.8.0)
  - `.agent-toolkit/.hook_fire_log.json` (Phase C v0.9.0)
  - `.agent-toolkit/.spec_first_guard_log.json`
  - `.agent-toolkit/.implement_notes_gate_log.json`

Produces markdown summary:
  - Total fires per hook (last N events)
  - Crash counts per hook
  - Warn / block / silent verdicts breakdown
  - Recent stale-ness check
  - Health verdict (green / yellow / red)

CLI:
  python hook_health.py [--workspace .] [--window 50] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


CRASH_LOG_REL = ".agent-toolkit/.hook_crash_log.json"
FIRE_LOG_REL = ".agent-toolkit/.hook_fire_log.json"
SPEC_FIRST_LOG_REL = ".agent-toolkit/.spec_first_guard_log.json"
IMPL_NOTES_LOG_REL = ".agent-toolkit/.implement_notes_gate_log.json"


def _load_log(workspace: Path, rel: str) -> List[Dict[str, Any]]:
    p = workspace / rel
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        return data.get("events") or []
    if isinstance(data, list):
        return data
    return []


def aggregate(workspace: Path, window: int = 50) -> Dict[str, Any]:
    crash_events = _load_log(workspace, CRASH_LOG_REL)[-window:]
    fire_events = _load_log(workspace, FIRE_LOG_REL)[-window:]
    spec_first_events = _load_log(workspace, SPEC_FIRST_LOG_REL)[-window:]
    impl_notes_events = _load_log(workspace, IMPL_NOTES_LOG_REL)[-window:]

    now = int(time.time())

    # Per-hook fire counts
    fires_per_hook: Counter = Counter()
    verdicts_per_hook: Dict[str, Counter] = defaultdict(Counter)
    durations: Dict[str, List[int]] = defaultdict(list)
    for e in fire_events:
        h = e.get("hook", "?")
        fires_per_hook[h] += 1
        verdicts_per_hook[h][e.get("verdict") or "?"] += 1
        d = e.get("duration_ms")
        if isinstance(d, int):
            durations[h].append(d)

    # Crash counts per hook
    crashes_per_hook: Counter = Counter()
    for e in crash_events:
        crashes_per_hook[e.get("hook") or "?"] += 1

    # Bypass / warn counts from spec_first_guard
    spec_first_warns = sum(1 for e in spec_first_events if e.get("kind") == "warn")
    spec_first_bypass = sum(1 for e in spec_first_events if e.get("kind") == "bypass")
    impl_notes_warns = sum(1 for e in impl_notes_events if e.get("kind") == "warn")
    impl_notes_bypass = sum(1 for e in impl_notes_events if e.get("kind") == "bypass")

    # Recent activity
    recent_crash = any(now - (e.get("ts") or 0) < 86400 for e in crash_events)

    # Health verdict
    if sum(crashes_per_hook.values()) > 5:
        health = "red"
    elif recent_crash or sum(crashes_per_hook.values()) > 0:
        health = "yellow"
    else:
        health = "green"

    return {
        "workspace": str(workspace),
        "window": window,
        "health": health,
        "fires_total": sum(fires_per_hook.values()),
        "fires_per_hook": dict(fires_per_hook),
        "verdicts_per_hook": {h: dict(v) for h, v in verdicts_per_hook.items()},
        "avg_duration_ms_per_hook": {
            h: sum(d) // len(d) for h, d in durations.items() if d
        },
        "crashes_total": sum(crashes_per_hook.values()),
        "crashes_per_hook": dict(crashes_per_hook),
        "spec_first_guard": {
            "warns": spec_first_warns,
            "bypasses": spec_first_bypass,
        },
        "implement_notes_gate": {
            "warns": impl_notes_warns,
            "bypasses": impl_notes_bypass,
        },
        "recent_crash_24h": recent_crash,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    health_icon = {"green": "OK", "yellow": "WARN", "red": "CRITICAL"}.get(
        report["health"], "?")
    lines = [
        f"## Hook health — `{Path(report['workspace']).name}`",
        "",
        f"- Status: **{report['health']}** ({health_icon})",
        f"- Window: last {report['window']} events per log",
        f"- Total fires: {report['fires_total']}",
        f"- Total crashes: {report['crashes_total']}",
        f"- Recent crash (last 24h): {report['recent_crash_24h']}",
        "",
    ]
    if report.get("fires_per_hook"):
        lines.append("### Fires per hook")
        lines.append("")
        lines.append("| Hook | Count | Avg ms |")
        lines.append("|---|---|---|")
        durations = report.get("avg_duration_ms_per_hook") or {}
        for hook, count in sorted(report["fires_per_hook"].items(),
                                  key=lambda kv: -kv[1]):
            avg = durations.get(hook, "—")
            lines.append(f"| `{hook}` | {count} | {avg} |")
        lines.append("")

    if report.get("crashes_per_hook"):
        lines.append("### Crashes per hook")
        lines.append("")
        for hook, count in sorted(report["crashes_per_hook"].items(),
                                  key=lambda kv: -kv[1]):
            lines.append(f"- `{hook}`: {count}")
        lines.append("")

    sfg = report.get("spec_first_guard") or {}
    if sfg.get("warns") or sfg.get("bypasses"):
        lines.append("### spec_first_guard activity")
        lines.append(f"- warns: {sfg.get('warns', 0)}")
        lines.append(f"- bypasses: {sfg.get('bypasses', 0)}")
        lines.append("")

    ing = report.get("implement_notes_gate") or {}
    if ing.get("warns") or ing.get("bypasses"):
        lines.append("### implement_notes_gate activity")
        lines.append(f"- warns: {ing.get('warns', 0)}")
        lines.append(f"- bypasses: {ing.get('bypasses', 0)}")
        lines.append("")

    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--window", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv[1:])
    workspace = Path(ns.workspace).resolve()
    report = aggregate(workspace, window=ns.window)
    if ns.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
