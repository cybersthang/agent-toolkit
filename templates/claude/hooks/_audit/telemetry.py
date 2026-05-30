"""Hook telemetry — append every audit invocation to a JSONL log so dev
can measure FP rate / bypass usage / block effectiveness over time.

Logged event shape:
  {ts, hook, decision, categories: [...], bypass: [...], turn_chars}

Log path: <workspace>/.codex/logs/hook_events.jsonl
Best-effort: silently no-op if write fails (never jam the hook).
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


LOG_REL = ".codex/logs/hook_events.jsonl"
# Rotate when log exceeds this size (bytes). Default 1 MB.
LOG_ROTATE_BYTES = 1_000_000
# Keep this many rotated files (oldest auto-deleted).
LOG_KEEP_ROTATIONS = 3


def _rotate_if_large(log_path: Path) -> None:
    """If log file exceeds LOG_ROTATE_BYTES, rotate. Best-effort, silent."""
    try:
        if not log_path.exists():
            return
        if log_path.stat().st_size < LOG_ROTATE_BYTES:
            return
        # Shift older rotations: .3 deleted, .2 → .3, .1 → .2, current → .1
        for i in range(LOG_KEEP_ROTATIONS, 0, -1):
            src = log_path.with_suffix(f".jsonl.{i}")
            dst = log_path.with_suffix(f".jsonl.{i + 1}")
            if i == LOG_KEEP_ROTATIONS and src.exists():
                src.unlink(missing_ok=True)
            elif src.exists():
                src.replace(dst)
        log_path.replace(log_path.with_suffix(".jsonl.1"))
    except OSError:
        pass


def log_event(
    workspace: Path,
    hook: str,
    decision: str,
    categories: Optional[List[str]] = None,
    bypass: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a single event line. Never raises. Auto-rotates when file
    exceeds LOG_ROTATE_BYTES."""
    try:
        # Honor kill-switch.
        import os
        if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
            return
        log_path = workspace / LOG_REL
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_large(log_path)
        evt: Dict[str, Any] = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "hook": hook,
            "decision": decision,
        }
        if categories:
            evt["categories"] = list(categories)
        if bypass:
            evt["bypass"] = list(bypass)
        if extra:
            evt.update(extra)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_recent_stats(workspace: Path, max_events: int = 200) -> Dict[str, Any]:
    """Read the last N events and return aggregate stats. Returns empty
    dict if log missing or unreadable."""
    log_path = workspace / LOG_REL
    if not log_path.exists():
        return {}
    try:
        with log_path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return {}
    recent = lines[-max_events:]
    total = 0
    by_decision: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    bypass_count = 0
    for line in recent:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        d = evt.get("decision") or "unknown"
        by_decision[d] = by_decision.get(d, 0) + 1
        for cat in evt.get("categories") or []:
            by_category[cat] = by_category.get(cat, 0) + 1
        if evt.get("bypass"):
            bypass_count += 1
    return {
        "total": total,
        "by_decision": by_decision,
        "by_category": by_category,
        "bypass_count": bypass_count,
    }
