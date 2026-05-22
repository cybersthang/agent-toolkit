#!/usr/bin/env python
"""PostToolUse hook — track LOC delta per turn into a ring buffer.

Observability tool (Dim 3), not enforcement. Emits a soft warn when:
  - This turn added > per_turn_added_warn LOC (default 200)
  - OR a file touched grew past per_file_total_warn LOC (default 800)

Writes events to `.agent-toolkit/.hook_loc_log.json` (ring buffer, 1000 max)
so `/hook-health` can show LOC growth trend over time.

Config: `<workspace>/.agent-toolkit/loc_budget.json` (see
`templates/agent_toolkit/loc_budget.example.json`).

Honors `AGENT_TOOLKIT_DISABLE=1`. Fails open on any error.

v0.12.0 — closes "ít code càng tốt" gap (HE Dim 3 observability).
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, atomic_write_json, run_main_safe, emit_fire_event,
)

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/loc_budget.json"
LOG_REL = ".agent-toolkit/.hook_loc_log.json"
RING_BUFFER_MAX = 1000

_DEFAULT_CFG = {
    "enabled": True,
    "per_turn_added_warn": 200,
    "per_file_total_warn": 800,
    # v0.12.1: docs / metadata files are append-only by nature; CHANGELOG
    # routinely grows past 800 LOC and that's not a problem. Empirical
    # signal from first prod fire of loc_delta_tracker — adding sane
    # defaults so the warn fires only on source-code bloat.
    "exempt_globs": ["tests/**", "**/test_*.py", "**/*_test.py",
                     "**/migrations/**", "**/__init__.py",
                     "**/*.md", "CHANGELOG*", "LICENSE*", "NOTICE*",
                     "**/*.json", "**/*.lock"],
}


def _exit_allow() -> None:
    sys.exit(0)


def _load_cfg(workspace: Path) -> Dict[str, Any]:
    p = workspace / CONFIG_REL
    cfg = dict(_DEFAULT_CFG)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                cfg.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _is_exempt(rel_path: str, exempt_globs: List[str]) -> bool:
    rel = rel_path.replace("\\", "/")
    for pat in exempt_globs:
        if fnmatch.fnmatch(rel, pat):
            return True
    return False


def _count_loc(text: str) -> int:
    """Count non-blank lines (closer to functional LOC than raw line count)."""
    return sum(1 for line in text.splitlines() if line.strip())


def _compute_delta(envelope: dict) -> Optional[Dict[str, Any]]:
    """Return {file, added, removed, total} for the edit, or None if N/A."""
    tool_name = envelope.get("tool_name") or ""
    tool_input = envelope.get("tool_input") or {}
    tool_response = envelope.get("tool_response") or {}
    file_path = tool_input.get("file_path")
    if not file_path:
        return None

    if tool_name == "Write":
        new_text = tool_input.get("content") or ""
        # tool_response.oldContent may exist if file already existed; not always present
        old_text = tool_response.get("oldContent") or ""
        added = _count_loc(new_text)
        removed = _count_loc(old_text)
        return {
            "file": file_path,
            "added": max(0, added - removed),
            "removed": max(0, removed - added),
            "total": added,
        }
    if tool_name == "Edit":
        old_s = tool_input.get("old_string") or ""
        new_s = tool_input.get("new_string") or ""
        return {
            "file": file_path,
            "added": _count_loc(new_s),
            "removed": _count_loc(old_s),
            "total": _count_total_from_disk(file_path),
        }
    if tool_name == "MultiEdit":
        added = 0
        removed = 0
        for e in (tool_input.get("edits") or []):
            if isinstance(e, dict):
                added += _count_loc(e.get("new_string") or "")
                removed += _count_loc(e.get("old_string") or "")
        return {
            "file": file_path,
            "added": added,
            "removed": removed,
            "total": _count_total_from_disk(file_path),
        }
    return None


def _count_total_from_disk(file_path: str) -> int:
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        return _count_loc(text)
    except OSError:
        return 0


def _append_event(workspace: Path, event: Dict[str, Any]) -> None:
    log_path = workspace / LOG_REL
    try:
        if log_path.exists():
            try:
                data = json.loads(log_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "events" not in data:
                    data = {"events": []}
            except (json.JSONDecodeError, OSError):
                data = {"events": []}
        else:
            data = {"events": []}
        events = data.get("events") or []
        events.append(event)
        if len(events) > RING_BUFFER_MAX:
            events = events[-RING_BUFFER_MAX:]
        data["events"] = events
        atomic_write_json(log_path, data)
    except OSError:
        pass


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_allow()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_allow()
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_allow()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    cfg = _load_cfg(workspace)
    if not cfg.get("enabled", True):
        _exit_allow()

    delta = _compute_delta(envelope)
    if not delta:
        _exit_allow()

    # Resolve workspace-relative path for exempt check.
    try:
        rel = str(Path(delta["file"]).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel = delta["file"].replace("\\", "/")
    if _is_exempt(rel, cfg.get("exempt_globs") or []):
        _exit_allow()

    event = {
        "ts": int(time.time()),
        "file": rel,
        "added": delta["added"],
        "removed": delta["removed"],
        "total": delta["total"],
    }
    _append_event(workspace, event)

    warn_added = int(cfg.get("per_turn_added_warn", 200))
    warn_total = int(cfg.get("per_file_total_warn", 800))
    warnings: List[str] = []
    if delta["added"] > warn_added:
        warnings.append(
            f"+{delta['added']} LOC in one edit (threshold {warn_added}). "
            f"Karpathy §2: 'If you write 200 lines and it could be 50, rewrite it.'"
        )
    if delta["total"] > warn_total:
        warnings.append(
            f"{rel} now {delta['total']} LOC (threshold {warn_total}). "
            f"Consider splitting before the file grows further."
        )

    if not warnings:
        try:
            emit_fire_event("loc_delta_tracker.py", verdict="allow",
                            detail=f"+{delta['added']}")
        except Exception:
            pass
        _exit_allow()

    try:
        emit_fire_event("loc_delta_tracker.py", verdict="warn",
                        detail=f"+{delta['added']}/{delta['total']}")
    except Exception:
        pass

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "[loc-budget] " + " | ".join(warnings),
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
