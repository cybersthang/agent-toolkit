#!/usr/bin/env python3
"""flip_readiness (v0.34 T10 / R5.2) — per-trigger would-block telemetry that gates
the block-default FLIP.

A v0.34 gate ships block-CAPABLE @ WARN: under default `enforce_mode` it WARNS where
it *would* block. Flipping a trigger warn→block (per-trigger, via `enforce_mode.json`)
is only safe once that trigger's would-block FALSE-POSITIVE rate ≈ 0. This report
surfaces, per flip-candidate trigger, how often it would have blocked (warn verdicts)
+ how often it actually blocked + how often it was bypassed — the candidate set for
R5.3 sampling.

It does NOT auto-flip and does NOT compute an FP-rate: whether a given would-block was
a true catch or a false positive is a human/independent-review judgment (R5.3). The
report counts the candidates and refuses to call a trigger "READY" while any
would-block or bypass sits unsampled in the window.

CLI:  python3 flip_readiness.py [--workspace .] [--window 200] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

FIRE_LOG_REL = ".agent-toolkit/.hook_fire_log.json"

# v0.34 block-CAPABLE-@-WARN triggers (flip candidates). `no-subagents-forge`
# (invariant_guard) ships block-default already (FP≈0 by construction), so it is NOT
# a flip candidate — it never warns.
FLIP_CANDIDATES = (
    "verify_lint.py",
    "analyze_halt_gate.py",
    "review_proof_gate.py",
    "implement_notes_gate.py",
    "implement_orchestrator.py",
)


def _load(ws: Path) -> List[Dict[str, Any]]:
    p = ws / FIRE_LOG_REL
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    events = data.get("events") if isinstance(data, dict) else data
    return events if isinstance(events, list) else []


def readiness(ws: Path, window: int = 200) -> Dict[str, Any]:
    events = _load(ws)[-window:]
    per: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in events:
        if isinstance(e, dict) and e.get("hook"):
            per[e["hook"]][e.get("verdict") or "ok"] += 1
    triggers = []
    for hook in FLIP_CANDIDATES:
        c = per.get(hook, {})
        # "would_block" = a warn-capable gate emitting warn (it would block under
        # enforce) OR an actual block. Both are FP-sampling candidates.
        would_block = int(c.get("warn", 0)) + int(c.get("block", 0))
        bypass = int(c.get("bypass", 0))
        ready = would_block == 0 and bypass == 0
        triggers.append({
            "trigger": hook,
            "fires": int(sum(c.values())),
            "would_block": would_block,
            "block": int(c.get("block", 0)),
            "bypass": bypass,
            "flip": ("READY — 0 would-block/bypass in window; confirm with an R5.3 "
                     "sample before flipping" if ready else
                     f"HOLD — {would_block} would-block + {bypass} bypass need FP "
                     f"sampling (R5.3) before flip"),
        })
    return {"window": window, "events_seen": len(events), "triggers": triggers}


def _md(rep: Dict[str, Any]) -> str:
    lines = [
        f"# flip-readiness (window={rep['window']}, {rep['events_seen']} events seen)",
        "",
        "| trigger | fires | would-block | block | bypass | flip? |",
        "|---|---|---|---|---|---|",
    ]
    for r in rep["triggers"]:
        lines.append(f"| {r['trigger']} | {r['fires']} | {r['would_block']} | "
                     f"{r['block']} | {r['bypass']} | {r['flip']} |")
    lines += [
        "",
        "Flip a trigger warn→block (in `.agent-toolkit/enforce_mode.json` `per_hook`) "
        "ONLY after R5.3 sampling shows its would-block events are FP≈0. This report "
        "counts candidates; it does NOT judge FP — a `warn` may be a correct catch or "
        "a false positive, and only an independent review of the sample can tell.",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v0.34 per-trigger flip-readiness report")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--window", type=int, default=200)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = readiness(Path(a.workspace).resolve(), a.window)
    print(json.dumps(rep, indent=2) if a.json else _md(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
