"""Shared resume-state core (v0.24.0, agent-resilience-supervisor).

Reads the R9 scope manifest + tasks.md status + autonomy state and builds a
short "resume brief" describing where autonomous work stopped, so a resumed
session (CLI relaunch OR VSCode-extension SessionStart) can continue
IDEMPOTENTLY — already-done/passed items are never re-listed.

Used by:
- `session_brief.py` (SessionStart hook) → injects the brief for the
  extension semi-auto path.
- `tools/agent_supervisor.py` (external watcher) → passes the brief as the
  relaunch prompt for the CLI full-auto path.

Underscore-prefixed = library module (not a hook); the Stop-chain kill-switch
test skips `_`-prefixed files. Fails soft: any read error → returns None.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_REL = ".agent-toolkit/.scope_manifest.json"
AUTONOMY_REL = ".agent-toolkit/.autonomy_active.json"

# Manifest item statuses that count as resolved (not pending).
_RESOLVED = {"done", "deferred", "cant"}

# tasks.md task header + status parsing (mirrors scope_completeness_gate).
_TASK_HEADER_RE = re.compile(r"^#{1,6}\s*(T\d+)\b\s*[—\-:]?\s*(.*)$", re.MULTILINE)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def read_manifest(workspace: Path) -> Optional[Dict[str, Any]]:
    return _read_json(workspace / MANIFEST_REL)


def read_autonomy(workspace: Path) -> Optional[Dict[str, Any]]:
    return _read_json(workspace / AUTONOMY_REL)


def _find_tasks_md(workspace: Path, slug: str) -> Optional[Path]:
    """Locate tasks.md for a spec slug (canonical, legacy flat, version-
    prefixed). Returns the most-recently-modified hit or None."""
    if not slug:
        return None
    roots = [workspace / ".agent-toolkit" / "specs", workspace / "specs"]
    hits: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        hits.extend(root.rglob(f"{slug}/tasks.md"))
        hits.extend(root.rglob(f"{slug}.tasks.md"))
        hits.extend(root.rglob(f"*{slug}*.tasks.md"))
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def _tasks_status_map(tasks_path: Path) -> Dict[str, str]:
    """Map T<n> → resolved-status from tasks.md recorded results.
    `passed` → done, `skipped` → deferred, else pending."""
    try:
        text = tasks_path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    headers = list(_TASK_HEADER_RE.finditer(text))
    out: Dict[str, str] = {}
    for idx, m in enumerate(headers):
        tid = m.group(1).upper()
        start = m.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        section = text[start:end].lower()
        if re.search(r"\bpassed\b", section):
            out[tid] = "done"
        elif re.search(r"\bskipped\b", section):
            out[tid] = "deferred"
        else:
            out[tid] = "pending"
    return out


def _effective_status(item: Dict[str, Any], tasks_status: Dict[str, str]) -> str:
    """Item status refreshed against current tasks.md (idempotency): if the
    item references a T<n> that tasks.md now marks resolved, honor that."""
    status = str(item.get("status") or "pending")
    ref = str(item.get("ref") or "")
    if ref.upper() in tasks_status:
        ts = tasks_status[ref.upper()]
        if ts in _RESOLVED:
            return ts
    return status


def build_brief(workspace: Path) -> Optional[str]:
    """Return a short resume brief, or None if nothing to resume.

    None when: no manifest, or every item resolved (done/deferred/cant or
    tasks.md-passed). Pending items are listed; resolved items are NEVER
    listed (idempotent — a resumed session won't redo finished work).
    """
    manifest = read_manifest(workspace)
    if not manifest:
        return None
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        return None

    slug = str(manifest.get("spec") or "")
    tasks_path = _find_tasks_md(workspace, slug)
    tasks_status = _tasks_status_map(tasks_path) if tasks_path else {}

    pending: List[Dict[str, Any]] = []
    done_count = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        if _effective_status(it, tasks_status) == "pending":
            pending.append(it)
        else:
            done_count += 1

    if not pending:
        return None

    autonomy = read_autonomy(workspace)
    spec_label = slug or (autonomy or {}).get("spec") or "(unknown)"
    src = manifest.get("source", "?")

    lines = [
        f"🔄 RESUME — phiên autonomous đang dở (spec `{spec_label}`, "
        f"source {src}). Đã xong {done_count}, còn {len(pending)} item:",
    ]
    for it in pending[:12]:
        sid = it.get("id", "?")
        ref = it.get("ref", "")
        desc = (it.get("desc") or "")[:110]
        ref_part = f" ({ref})" if ref else ""
        lines.append(f"  • {sid}{ref_part} — {desc}")
    if len(pending) > 12:
        lines.append(f"  • ... và {len(pending) - 12} item khác")
    lines.append("Tiếp tục các item còn pending; KHÔNG làm lại item đã xong.")
    return "\n".join(lines)
