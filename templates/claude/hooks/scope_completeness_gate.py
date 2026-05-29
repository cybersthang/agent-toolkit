#!/usr/bin/env python
"""Stop hook — scope-completeness gate (v0.23.0, R9).

Sibling of gap_completeness_gate. Where the gap gate tracks gaps the AGENT
surfaces MID-WORK (reactive, anti drip-feed), this gate tracks the FULL
request scope declared UPFRONT (proactive, anti partial-done).

Root cause (R9, session 2026-05-27): DEV said "làm full" (fix ALL reviewer
findings — multi-item scope). Agent did 7/14, claimed substantial progress.
DEV had to ask "đã làm đầy đủ chưa" → agent only THEN audited (reactive).
gap_completeness_gate could not catch this: it only measures gaps the agent
self-surfaces via `G<N>`, not the full request scope. Partial completion is
invisible because un-done items never register as a gap.

This gate enumerates the request scope into a mechanical manifest
(`.agent-toolkit/.scope_manifest.json`) derived from a STRUCTURED artifact
(NOT DEV prompt keywords — explicit anti-requirement), then BLOCKs a
done/full claim while any manifest item is still `pending`.

Manifest source priority (D1):
  1. `tasks.md` (Spec Kit) — each `## T<N>` header = 1 item; task status
     (`passed`/`skipped`/`failed`) maps to item status (D4 — read directly,
     no separate sync layer).
  2. `acceptance_evals` (spec frontmatter) — each eval id = 1 item.
  3. Ad-hoc TodoWrite ≥ `min_items` (default 3) read from the session
     transcript — each todo = 1 item. Sub-agent batches do NOT auto-trigger.

Resolution markers in agent response (D5 / sibling gap gate parity):
  - `scope-done: S<N>`            → item done
  - `scope-defer: S<N> <reason>`  → item deferred (≥ 8-char reason)
  - `scope-cant: S<N> <reason>`   → item cant (escalate DEV)

Activation boundary (D3, us4): the gate is SILENT (exit 0, zero output)
unless a manifest exists. Small requests (no tasks.md, < min_items todos)
never produce a manifest → zero friction.

Whole-gate single-shot bypass (D5): prior prompt `bypass-scope-gate:
<reason ≥ 8 chars>` → intent_router writes `.skip_scope_gate_next.json`;
this hook consumes it on Stop.

Enforce mode via `get_enforce_mode(workspace, "scope_completeness_gate")`:
  - `warn`  (default v0.27 — surface pending items but don't block; cuts
             paralysis from stacked Stop gates)
  - `block` (opt-in via enforce_mode.json — D2, strict mode)
  - `off`   (silent allow)

Fails open on any unexpected error (wrapped by run_main_safe).
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
from _common import (  # noqa: E402
    run_main_safe, emit_fire_event, get_enforce_mode, atomic_write_json,
    parse_expires_at, read_jsonl_transcript,
)
from _patterns import (  # noqa: E402
    SCOPE_DONE_RE, SCOPE_DEFER_RE, SCOPE_CANT_RE, DONE_FULL_CLAIM_RE,
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


MANIFEST_REL = ".agent-toolkit/.scope_manifest.json"
AUTONOMY_REL = ".agent-toolkit/.autonomy_active.json"
CONFIG_REL = ".agent-toolkit/scope_gate.json"
SKIP_TOKEN_REL = ".agent-toolkit/.skip_scope_gate_next.json"
DEFAULT_MIN_ITEMS = 3
HOOK_NAME = "scope_completeness_gate"

# Task-header parser for tasks.md: `## T1 — goal`, `## T12 - goal`.
_TASK_HEADER_RE = re.compile(r"^#{1,6}\s*(T\d+)\b\s*[—\-:]?\s*(.*)$", re.MULTILINE)
# Acceptance-eval id parser for spec frontmatter: `- id: us1-foo`.
_EVAL_ID_RE = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9][\w\-]*)\s*$", re.MULTILINE)


# ---------------------------------------------------------------- exits

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
    sys.stderr.write(f"[scope-completeness-gate] block: {reason}\n")
    return 2


def _exit_warn(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=reason[:200])
    except Exception:
        pass
    sys.stderr.write(f"[scope-completeness-gate] warn: {reason}\n")
    return 0


# ---------------------------------------------------------------- helpers

def _find_workspace(cwd: Optional[str]) -> Path:
    if cwd:
        return Path(cwd).resolve()
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _read_config(workspace: Path) -> Dict[str, Any]:
    cfg = _read_json(workspace / CONFIG_REL) or {}
    return cfg if isinstance(cfg, dict) else {}


def _autonomy(workspace: Path) -> Optional[Dict[str, Any]]:
    """Return autonomy state dict if a non-expired autonomy file exists,
    else None. Manifest lifecycle mirrors autonomy (D3)."""
    data = _read_json(workspace / AUTONOMY_REL)
    if not data:
        return None
    expires = data.get("expires_at")
    if not expires:
        return data
    from datetime import datetime
    exp_dt = parse_expires_at(expires)
    if exp_dt is None:
        return data  # parse fail → treat as active (fail-open)
    now_dt = datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now()
    return data if now_dt < exp_dt else None


def _extract_assistant_text(envelope: Dict[str, Any]) -> str:
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


# ---------------------------------------------------------------- derive

def _find_tasks_md(workspace: Path, slug: str) -> Optional[Path]:
    """Locate tasks.md for a spec slug, both canonical and legacy layouts.
    Toolkit self-spec layout (`specs/<slug>.tasks.md`) also supported."""
    if not slug:
        return None
    roots = [workspace / ".agent-toolkit" / "specs", workspace / "specs"]
    candidates: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(root.rglob(f"{slug}/tasks.md"))        # canonical
        candidates.extend(root.rglob(f"{slug}.tasks.md"))        # legacy flat
        candidates.extend(root.rglob(f"*{slug}*.tasks.md"))      # version-prefixed
    if not candidates:
        return None
    # Most-recently-modified wins if several.
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _find_spec_md(workspace: Path, slug: str) -> Optional[Path]:
    if not slug:
        return None
    roots = [workspace / ".agent-toolkit" / "specs", workspace / "specs"]
    candidates: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(p for p in root.rglob(f"*{slug}*.md")
                          if not p.name.endswith(".tasks.md")
                          and "tasks.md" not in p.name)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _task_status_to_item(section: str) -> str:
    """Map a tasks.md task section's recorded status to manifest item
    status (D4 — read tasks.md status directly). `passed` → done,
    `skipped` → deferred, else pending."""
    low = section.lower()
    # Look only at the status/result lines, not the whole prose.
    if re.search(r"\bstatus\s*:\s*passed\b", low) or re.search(r"\bpassed\b", low):
        return "done"
    if re.search(r"\bstatus\s*:\s*skipped\b", low) or re.search(r"\bskipped\b", low):
        return "deferred"
    return "pending"


def _derive_from_tasks(tasks_path: Path) -> List[Dict[str, Any]]:
    try:
        text = tasks_path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    headers = list(_TASK_HEADER_RE.finditer(text))
    items: List[Dict[str, Any]] = []
    now = int(time.time())
    for idx, m in enumerate(headers):
        tid = m.group(1).upper()
        desc = (m.group(2) or "").strip().rstrip(".,;")
        start = m.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        section = text[start:end]
        status = _task_status_to_item(section)
        item = {
            "id": f"S{idx + 1}",
            "ref": tid,
            "desc": desc[:200],
            "status": status,
            "resolution_ts": now if status != "pending" else None,
            "resolution_reason": "tasks.md status" if status != "pending" else None,
        }
        items.append(item)
    return items


def _derive_from_evals(spec_path: Path) -> List[Dict[str, Any]]:
    try:
        text = spec_path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    # Restrict to the frontmatter block (between first two `---`).
    parts = text.split("---", 2)
    front = parts[1] if len(parts) >= 3 else text
    if "acceptance_evals" not in front:
        return []
    items: List[Dict[str, Any]] = []
    for idx, m in enumerate(_EVAL_ID_RE.finditer(front)):
        eid = m.group(1)
        items.append({
            "id": f"S{idx + 1}",
            "ref": eid,
            "desc": eid,
            "status": "pending",
            "resolution_ts": None,
            "resolution_reason": None,
        })
    return items


def _latest_todowrite(transcript_path: Optional[str]) -> List[Dict[str, Any]]:
    """Read the session transcript, return the items of the most-recent
    TodoWrite tool call (or empty). Self-contained ad-hoc capture — no
    extra PostToolUse hook needed."""
    if not transcript_path:
        return []
    p = Path(transcript_path)
    if not p.exists():
        return []
    messages = read_jsonl_transcript(p)
    todos: List[Dict[str, Any]] = []
    for msg in messages:
        content = None
        if isinstance(msg.get("message"), dict):
            content = msg["message"].get("content")
        elif "content" in msg:
            content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "TodoWrite":
                inp = block.get("input") or {}
                cand = inp.get("todos")
                if isinstance(cand, list) and cand:
                    todos = cand  # keep latest (loop continues to end)
    return todos


def _derive_from_todos(todos: List[Dict[str, Any]], min_items: int) -> List[Dict[str, Any]]:
    if len(todos) < min_items:
        return []
    items: List[Dict[str, Any]] = []
    now = int(time.time())
    for idx, td in enumerate(todos):
        content = ""
        status_in = ""
        if isinstance(td, dict):
            content = str(td.get("content") or td.get("activeForm") or "")
            status_in = str(td.get("status") or "")
        done = status_in.lower() == "completed"
        items.append({
            "id": f"S{idx + 1}",
            "ref": f"todo{idx + 1}",
            "desc": content[:200],
            "status": "done" if done else "pending",
            "resolution_ts": now if done else None,
            "resolution_reason": "todowrite completed" if done else None,
        })
    return items


def _build_manifest(workspace: Path, autonomy: Dict[str, Any],
                    envelope: Dict[str, Any], min_items: int
                    ) -> Optional[Dict[str, Any]]:
    """Derive a fresh manifest from the highest-priority structured source
    available. Returns None if no source qualifies (→ gate stays silent)."""
    slug = (autonomy or {}).get("spec") or ""
    now = int(time.time())

    # Priority 1: tasks.md
    tasks_path = _find_tasks_md(workspace, slug)
    if tasks_path:
        items = _derive_from_tasks(tasks_path)
        if items:
            return {"version": 1, "spec": slug, "source": "tasks.md",
                    "created_ts": now, "items": items, "bypass_history": []}

    # Priority 2: acceptance_evals
    spec_path = _find_spec_md(workspace, slug)
    if spec_path:
        items = _derive_from_evals(spec_path)
        if items:
            return {"version": 1, "spec": slug, "source": "acceptance_evals",
                    "created_ts": now, "items": items, "bypass_history": []}

    # Priority 3: ad-hoc TodoWrite ≥ min_items (D1 — TodoWrite-only).
    todos = _latest_todowrite(envelope.get("transcript_path"))
    items = _derive_from_todos(todos, min_items)
    if items:
        return {"version": 1, "spec": slug or "(ad-hoc)", "source": "todowrite",
                "created_ts": now, "items": items, "bypass_history": []}

    return None


# ---------------------------------------------------------------- resolve

def _apply_markers(manifest: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    """Flip manifest items per scope-done / scope-defer / scope-cant
    markers in the response. Mutates + returns manifest."""
    items = manifest.get("items") or []
    if not isinstance(items, list):
        return manifest
    now = int(time.time())
    by_id = {it.get("id"): it for it in items if isinstance(it, dict)}

    for m in SCOPE_DONE_RE.finditer(response_text):
        it = by_id.get(f"S{m.group(1)}")
        if it and it.get("status") == "pending":
            it["status"] = "done"
            it["resolution_ts"] = now
            it["resolution_reason"] = "scope-done marker"

    for m in SCOPE_DEFER_RE.finditer(response_text):
        it = by_id.get(f"S{m.group(1)}")
        if it and it.get("status") == "pending":
            it["status"] = "deferred"
            it["resolution_ts"] = now
            it["resolution_reason"] = m.group(2).strip()[:200]

    for m in SCOPE_CANT_RE.finditer(response_text):
        it = by_id.get(f"S{m.group(1)}")
        if it and it.get("status") == "pending":
            it["status"] = "cant"
            it["resolution_ts"] = now
            it["resolution_reason"] = m.group(2).strip()[:200]

    manifest["items"] = items
    return manifest


def _consume_bypass(workspace: Path) -> Optional[str]:
    """Single-shot bypass token written by intent_router from a
    `bypass-scope-gate:` prompt. Consume (unlink) + return reason."""
    token = workspace / SKIP_TOKEN_REL
    data = _read_json(token)
    if not data:
        return None
    reason = data.get("reason") or ""
    ts = int(data.get("ts") or 0)
    try:
        token.unlink()
    except OSError:
        pass
    if not reason or int(time.time()) - ts > 600:
        return None
    return reason


# ---------------------------------------------------------------- main

def _main() -> int:
    # Recursion break.
    if os.environ.get("stop_hook_active") == "true":
        return _exit_allow(detail="stop_hook_active")

    raw = sys.stdin.read()
    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return _exit_allow(detail="bad-json")
    if not isinstance(envelope, dict):
        return _exit_allow(detail="non-dict-envelope")

    workspace = _find_workspace(envelope.get("cwd"))
    cfg = _read_config(workspace)
    if cfg.get("enabled") is False:
        return _exit_allow(detail="disabled")
    min_items = cfg.get("min_items")
    if not isinstance(min_items, int) or min_items < 1:
        min_items = DEFAULT_MIN_ITEMS

    manifest_path = workspace / MANIFEST_REL
    manifest = _read_json(manifest_path)

    # Activation boundary (us4 / D3): manifest only exists while autonomy
    # is active. Lazily derive it the first time if autonomy is active and
    # a structured source qualifies; otherwise stay SILENT.
    autonomy = _autonomy(workspace)
    if manifest is None:
        if not autonomy:
            return _exit_allow(detail="no-manifest-no-autonomy")  # silent
        manifest = _build_manifest(workspace, autonomy, envelope, min_items)
        if manifest is None:
            return _exit_allow(detail="no-source")  # silent — zero friction
        atomic_write_json(manifest_path, manifest)

    response_text = _extract_assistant_text(envelope)

    # Whole-gate single-shot bypass.
    bypass_reason = _consume_bypass(workspace)
    if bypass_reason:
        return _exit_allow(detail=f"bypass:{bypass_reason[:80]}")

    # Apply resolution markers before deciding.
    manifest = _apply_markers(manifest, response_text)

    pending = [
        it for it in manifest.get("items", [])
        if isinstance(it, dict) and it.get("status") == "pending"
    ]

    # No done/full claim → persist marker mutations + allow.
    if not DONE_FULL_CLAIM_RE.search(response_text):
        atomic_write_json(manifest_path, manifest)
        return _exit_allow(detail=f"no-done-claim;pending={len(pending)}")

    if not pending:
        atomic_write_json(manifest_path, manifest)
        return _exit_allow(detail="all-resolved")

    # Done/full claim WITH pending items → block / warn / off.
    lines = [
        f"Turn này claim done/full nhưng scope manifest còn {len(pending)} "
        f"item chưa resolve (source: {manifest.get('source','?')}):",
    ]
    for it in pending[:12]:
        sid = it.get("id", "?")
        ref = it.get("ref", "")
        desc = (it.get("desc") or "")[:110]
        lines.append(f"  {sid} ({ref}) — {desc}")
    if len(pending) > 12:
        lines.append(f"  ... và {len(pending) - 12} item khác")
    lines.append("")
    lines.append(
        "Per R9: phải resolve MỖI item (làm xong HOẶC defer/cant với reason) "
        "TRƯỚC khi claim done/full. 3 cách:"
    )
    lines.append("  1. Làm xong item → `scope-done: S<N>` (hoặc tasks.md mark passed)")
    lines.append("  2. `scope-defer: S<N> <reason ≥ 8 chars>` — punt có chủ đích")
    lines.append("  3. `scope-cant: S<N> <reason>` — escalate DEV")
    lines.append(
        "Whole-gate bypass single-shot: DEV gõ `bypass-scope-gate: <reason>` ở prompt kế."
    )
    reason = "\n".join(lines)

    atomic_write_json(manifest_path, manifest)

    # v0.27 default flipped block → warn. DEV opts back into block via
    # enforce_mode.json or AGENT_TOOLKIT_STRICT=1.
    mode = get_enforce_mode(workspace, HOOK_NAME, default="warn")
    if mode == "off":
        return _exit_allow(detail=f"off;pending={len(pending)}")
    if mode == "warn":
        return _exit_warn(reason)
    return _exit_block(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(_main))
