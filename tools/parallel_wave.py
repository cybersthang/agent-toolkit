#!/usr/bin/env python
"""Parallel-wave manifest CLI helper (v0.25.0, parallel-subagent-guard).

Writes / reads / clears `.agent-toolkit/.parallel_wave.json` — the
manifest consumed by `parallel_conflict_guard.py` (PreToolUse hook) to
detect cross-zone Edits between concurrent sub-agents.

Workflow (main agent, before spawning sub-agents via the Agent tool):

  python tools/parallel_wave.py emit \\
      --wave my-wave \\
      --zone agent-a:src/a.py,src/b.py \\
      --zone agent-b:tests/test_a.py \\
      [--ttl 3600]

  # … spawn N sub-agents in parallel …

  python tools/parallel_wave.py declare-done   # or `clear`

Sub-commands: `emit`, `declare-done`, `clear`, `show`. All commands run
relative to `--project-dir` (default CWD).

Schema written:
  {
    "version": 1,
    "wave": "<name>",
    "created_ts": <int>,
    "ttl_seconds": <int>,
    "zones": [{"agent_id": "<id>", "owned": ["..."]}, ...],
    "wave_done": false
  }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_REL = ".agent-toolkit/.parallel_wave.json"
DEFAULT_TTL_SECONDS = 3600


def manifest_path(project_dir: Path) -> Path:
    return project_dir / MANIFEST_REL


def _parse_zone_arg(raw: str) -> Dict[str, Any]:
    """`agent_id:path1,path2,...` → {agent_id, owned: [path1, path2, ...]}"""
    if ":" not in raw:
        raise ValueError(f"Invalid --zone {raw!r}: expected 'agent_id:path1,path2'")
    agent_id, paths = raw.split(":", 1)
    agent_id = agent_id.strip()
    owned = [p.strip() for p in paths.split(",") if p.strip()]
    if not agent_id or not owned:
        raise ValueError(f"--zone {raw!r}: empty agent_id or owned list")
    return {"agent_id": agent_id, "owned": owned}


def emit(project_dir: Path, wave: str, zone_args: List[str],
         ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Dict[str, Any]:
    zones = [_parse_zone_arg(z) for z in zone_args]
    manifest = {
        "version": 1,
        "wave": wave,
        "created_ts": int(time.time()),
        "ttl_seconds": int(ttl_seconds),
        "zones": zones,
        "wave_done": False,
    }
    path = manifest_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return manifest


def read(project_dir: Path) -> Optional[Dict[str, Any]]:
    path = manifest_path(project_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def declare_done(project_dir: Path) -> bool:
    """Set wave_done=true (lifecycle trigger). Guard will treat as cleared."""
    manifest = read(project_dir)
    if manifest is None:
        return False
    manifest["wave_done"] = True
    manifest_path(project_dir).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def clear(project_dir: Path) -> bool:
    path = manifest_path(project_dir)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def show(project_dir: Path) -> Optional[Dict[str, Any]]:
    return read(project_dir)


def _cli(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Parallel-wave manifest helper")
    p.add_argument("--project-dir", default=os.getcwd(),
                   help="Workspace root (default: CWD)")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("emit", help="Write a new wave manifest")
    e.add_argument("--wave", required=True)
    e.add_argument("--zone", action="append", required=True,
                   help="agent_id:path1,path2,... (repeat per agent)")
    e.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)

    sub.add_parser("declare-done", help="Mark wave done (lifecycle trigger)")
    sub.add_parser("clear", help="Unlink manifest file")
    sub.add_parser("show", help="Print current manifest")

    args = p.parse_args(argv)
    pdir = Path(args.project_dir).resolve()

    if args.cmd == "emit":
        m = emit(pdir, args.wave, args.zone, ttl_seconds=args.ttl)
        print(json.dumps(m, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "declare-done":
        ok = declare_done(pdir)
        print("done" if ok else "no manifest")
        return 0 if ok else 1
    if args.cmd == "clear":
        ok = clear(pdir)
        print("cleared" if ok else "no manifest")
        return 0
    if args.cmd == "show":
        m = show(pdir)
        if m is None:
            print("no manifest")
            return 1
        print(json.dumps(m, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
