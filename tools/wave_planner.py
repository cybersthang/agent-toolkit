#!/usr/bin/env python3
"""Auto-parallel wave planner (v0.29.0).

Reads a `tasks.md` (emitted by /tasks), and turns its task list into
PARALLEL WAVES — sets of tasks that can safely run concurrently because
they (a) have all dependencies satisfied by an earlier wave AND (b) touch
DISJOINT files. This closes the Q3 gap: `/implement` shipped sequential-only;
this gives it a mechanical, conservative parallel decomposition.

Pure logic — no Claude Code, no network. The actual sub-agent fan-out is
done by the /implement skill, which calls `emit` here to write the
`.parallel_wave.json` manifest that `parallel_conflict_guard.py` enforces
(file-disjoint zones, one agent_id per task).

Conservative by design — when disjointness CANNOT be proven, tasks are NOT
parallelized (they fall back to their own wave):
  - empty / missing `Touches`        → unknown scope → solo wave
  - any glob in `Touches` (* ? [)     → can't prove disjoint → solo/serialize
  - any shared path between two tasks → conflict → different waves
  - dependency cycle / unsatisfiable  → full sequential fallback

CLI:
  python tools/wave_planner.py plan <tasks.md>
      → prints the wave plan as JSON (tasks, waves, parallel width).
  python tools/wave_planner.py emit <tasks.md> --wave <i> [--ttl 3600]
      → writes .parallel_wave.json for wave i (zones = one agent per task),
        reusing tools/parallel_wave.py. The /implement skill then spawns one
        sub-agent per zone.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel_wave  # noqa: E402  (sibling helper — reuse emit/manifest format)

_TASK_HDR = re.compile(r"^##\s+(T\d+)\b\s*(?:[—\-:]\s*(.*))?$")
_FIELD = re.compile(r"^\s*-\s+\*\*([A-Za-z ]+):\*\*\s*(.*)$")
_GLOB_CHARS = ("*", "?", "[")


def _clean_touches(raw: str) -> List[str]:
    """`\\`a.py\\` (extend), \\`b.py\\` (new)` → ['a.py', 'b.py']."""
    raw = raw.replace("`", "")
    raw = re.sub(r"\([^)]*\)", "", raw)        # drop (extend)/(new)/(refactor)
    parts = [p.strip().replace("\\", "/") for p in raw.split(",")]
    return [p for p in parts if p and p.lower() != "none"]


def parse_tasks(md: str) -> List[Dict[str, Any]]:
    """Parse a tasks.md body into [{id, goal, touches:[...], deps:[...]}]."""
    tasks: List[Dict[str, Any]] = []
    cur: Dict[str, Any] | None = None
    field: str | None = None
    for line in md.splitlines():
        hm = _TASK_HDR.match(line)
        if hm:
            cur = {"id": hm.group(1), "goal": (hm.group(2) or "").strip(),
                   "_touches_raw": "", "_deps_raw": ""}
            tasks.append(cur)
            field = None
            continue
        if cur is None:
            continue
        fm = _FIELD.match(line)
        if fm:
            name = fm.group(1).strip().lower()
            if name == "touches":
                field, cur["_touches_raw"] = "touches", fm.group(2)
            elif name in ("depends on", "depends"):
                field, cur["_deps_raw"] = "deps", fm.group(2)
            else:
                field = None
            continue
        # continuation of a multi-line field (e.g. Touches spilling lines)
        if field and line.strip() and not line.lstrip().startswith("#"):
            cur["_touches_raw" if field == "touches" else "_deps_raw"] += " " + line.strip()
    for t in tasks:
        t["touches"] = _clean_touches(t.pop("_touches_raw"))
        deps = re.findall(r"\bT\d+\b", t.pop("_deps_raw"))
        t["deps"] = [d for d in dict.fromkeys(deps) if d != t["id"]]
    return tasks


def _has_glob(path: str) -> bool:
    return any(c in path for c in _GLOB_CHARS)


def _conflict(a: List[str], b: List[str]) -> bool:
    """True when two tasks CANNOT be proven file-disjoint (conservative)."""
    if not a or not b:
        return True                       # unknown scope → unsafe
    if any(_has_glob(p) for p in (*a, *b)):
        return True                       # globs → can't prove disjoint
    return bool(set(a) & set(b))


def plan_waves(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group tasks into ordered waves. Each wave = file-disjoint tasks whose
    deps are all in earlier waves. Returns plan + stats."""
    by_id = {t["id"]: t for t in tasks}
    order = [t["id"] for t in tasks]
    known_deps = {tid: [d for d in by_id[tid]["deps"] if d in by_id] for tid in order}

    # BUG#2: a dependency that references a task we never saw is unsatisfiable.
    # Silently dropping it would mis-order the plan, so fall back to sequential.
    for tid in order:
        for d in by_id[tid]["deps"]:
            if d not in by_id:
                return {
                    "tasks": len(tasks),
                    "waves": [[t] for t in order],
                    "parallel_waves": 0, "max_width": 1,
                    "sequential_fallback": True,
                    "reason": f"unsatisfiable dependency: {tid} -> {d} (not found)",
                }

    done: set[str] = set()
    waves: List[List[str]] = []
    remaining = list(order)
    while remaining:
        ready = [tid for tid in remaining if all(d in done for d in known_deps[tid])]
        if not ready:
            # cycle / unsatisfiable dependency → safe sequential fallback
            return {
                "tasks": len(tasks),
                "waves": [[tid] for tid in remaining_with(waves, order)],
                "parallel_waves": 0, "max_width": 1,
                "sequential_fallback": True,
                "reason": "dependency cycle or unsatisfiable dep among "
                          + ",".join(remaining),
            }
        wave: List[str] = []
        for tid in ready:                 # preserve task order for stability
            if all(not _conflict(by_id[tid]["touches"], by_id[w]["touches"]) for w in wave):
                wave.append(tid)
        waves.append(wave)
        done.update(wave)
        remaining = [tid for tid in remaining if tid not in done]

    parallel = [w for w in waves if len(w) > 1]
    return {
        "tasks": len(tasks),
        "waves": waves,
        "parallel_waves": len(parallel),
        "max_width": max((len(w) for w in waves), default=0),
        "sequential_fallback": False,
        "reason": "ok" if parallel else "no provably-disjoint tasks → sequential",
    }


def remaining_with(waves: List[List[str]], order: List[str]) -> List[str]:
    placed = {tid for w in waves for tid in w}
    return [tid for tid in order if tid not in placed]


def emit_wave(project_dir: Path, tasks_md: Path, wave_index: int,
              ttl_seconds: int = parallel_wave.DEFAULT_TTL_SECONDS) -> Dict[str, Any]:
    """Write .parallel_wave.json for wave `wave_index`: one zone per task
    (agent_id = task id, owned = its Touches). Reuses parallel_wave.emit so
    parallel_conflict_guard enforces the file-disjoint contract."""
    # BUG#3: parse the file exactly ONCE; build by_id and the plan from the
    # SAME parsed list (no second read/parse → no TOCTOU mismatch).
    tasks = parse_tasks(tasks_md.read_text(encoding="utf-8"))
    plan = plan_waves(tasks)
    waves = plan["waves"]
    if wave_index < 0 or wave_index >= len(waves):
        raise ValueError(f"wave index {wave_index} out of range (0..{len(waves) - 1})")
    by_id = {t["id"]: t for t in tasks}
    zone_args = [f"{tid}:{','.join(by_id[tid]['touches'])}" for tid in waves[wave_index]
                 if by_id[tid]["touches"]]
    if not zone_args:
        raise ValueError(f"wave {wave_index} has no task with concrete Touches to zone")
    return parallel_wave.emit(project_dir, wave=f"tasks-wave-{wave_index}",
                              zone_args=zone_args, ttl_seconds=ttl_seconds)


def _cli(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Auto-parallel wave planner")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan", help="Print the wave plan for a tasks.md")
    pl.add_argument("tasks_md")

    em = sub.add_parser("emit", help="Write .parallel_wave.json for one wave")
    em.add_argument("tasks_md")
    em.add_argument("--wave", type=int, required=True)
    em.add_argument("--ttl", type=int, default=parallel_wave.DEFAULT_TTL_SECONDS)
    em.add_argument("--project-dir", default=None)

    args = p.parse_args(argv)
    tasks_md = Path(args.tasks_md).resolve()
    if not tasks_md.exists():
        print(f"tasks.md not found: {tasks_md}", file=sys.stderr)
        return 2

    if args.cmd == "plan":
        plan = plan_waves(parse_tasks(tasks_md.read_text(encoding="utf-8")))
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "emit":
        pdir = Path(args.project_dir).resolve() if args.project_dir else tasks_md.parent
        # walk up to a workspace root holding .agent-toolkit if possible
        cur = pdir
        while cur != cur.parent and not (cur / ".agent-toolkit").is_dir():
            cur = cur.parent
        if (cur / ".agent-toolkit").is_dir():
            pdir = cur
        m = emit_wave(pdir, tasks_md, args.wave, ttl_seconds=args.ttl)
        print(json.dumps(m, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
