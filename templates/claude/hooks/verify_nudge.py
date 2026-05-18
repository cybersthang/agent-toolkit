#!/usr/bin/env python
"""PostToolUse hook — nudge `/verify` after Edit on file referenced by a spec
at status `implementing`.

Closes enforcement gap: previously agent could Edit production code, claim
done, never run /verify. This hook scans `.agent-toolkit/specs/*.md` for any
spec with `status: implementing` whose section `## 3. Affected Modules /
Files` (or any code-fence path) references the edited file path. If match
→ emit reminder.

Behaviour
---------
- Silent when: no specs / no spec at status=implementing / no path match.
- Duplicate suppression: don't re-nudge the same (file, spec) pair within
  60s window.
- Fail-open on any error.
- Never blocks; only emits `additionalContext`.

Performance note (R2-2, 2026-05-17): scans ALL specs in `.agent-toolkit/specs/`
on every Edit/Write/MultiEdit. Cost O(N) where N = spec count. For typical
project (< 50 specs) this is ~5-10 ms; acceptable. If N grows > 200 specs,
consider caching the implementing-status spec list with file mtime
invalidation. For now: pre-filter via mtime stat reduces parse to O(active).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import wrap_utf8_stdio, atomic_write_json  # noqa: E402
from _patterns import (  # noqa: E402
    SPEC_STATUS_RE as _STATUS_RE,
    SPEC_SLUG_RE as _SPEC_SLUG_RE,
    IMPLEMENTING_STATUSES,
)

wrap_utf8_stdio()


SUPPORTED_TOOLS = {"Edit", "Write", "MultiEdit"}
STATE_REL = ".agent-toolkit/.verify_nudge_last.json"
CACHE_REL = ".agent-toolkit/.verify_nudge_cache.json"
TTL_SECONDS = 60


def _exit_silent() -> None:
    sys.exit(0)


def _emit(text: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _load_cache(workspace: Path) -> Dict[str, Any]:
    path = workspace / CACHE_REL
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(workspace: Path, cache: Dict[str, Any]) -> None:
    atomic_write_json(workspace / CACHE_REL, cache)


def _scan_specs(workspace: Path) -> List[Tuple[str, Path, str]]:
    """Return (slug, spec_path, body_text) for each spec at implementing status.

    FIX-1 (2026-05-17): mtime cache reduces O(N) per Edit to O(changed) — only
    re-read spec files whose mtime differs from cached. Saves ~3-5ms per spec
    on projects with many specs.
    """
    specs_dir = workspace / ".agent-toolkit" / "specs"
    if not specs_dir.is_dir():
        return []
    cache = _load_cache(workspace)
    new_cache: Dict[str, Any] = {}
    out: List[Tuple[str, Path, str]] = []
    cache_dirty = False
    for path in specs_dir.glob("*.md"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        key = str(path)
        cached = cache.get(key)
        if cached and cached.get("mtime") == mtime:
            # Reuse cached parse result.
            entry = cached
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
            if not fm_match:
                entry = {"mtime": mtime, "status": "", "slug": path.stem, "body": ""}
            else:
                fm = fm_match.group(1)
                status_m = _STATUS_RE.search(fm)
                status = status_m.group(1).lower() if status_m else ""
                slug_m = _SPEC_SLUG_RE.search(fm)
                slug = slug_m.group(1) if slug_m else path.stem
                entry = {"mtime": mtime, "status": status, "slug": slug, "body": text}
            cache_dirty = True
        new_cache[key] = entry
        if entry.get("status", "") in IMPLEMENTING_STATUSES:
            out.append((entry["slug"], path, entry["body"]))
    if cache_dirty or len(new_cache) != len(cache):
        _save_cache(workspace, new_cache)
    return out


def _file_referenced_in_spec(file_path: str, spec_body: str, workspace: Path) -> bool:
    """Heuristic: does spec body mention this file's relative path or basename?"""
    try:
        rel = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel = file_path.replace("\\", "/")
    basename = Path(file_path).name
    # Substring check on rel-path is strongest signal; fall back to basename
    # but only if basename is reasonably unique (≥ 10 chars or has underscore).
    if rel in spec_body:
        return True
    if (len(basename) >= 12 or "_" in basename) and basename in spec_body:
        return True
    return False


def _is_duplicate(workspace: Path, key: str) -> bool:
    path = workspace / STATE_REL
    state: Dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    now = int(time.time())
    last = state.get(key, 0)
    if (now - int(last)) < TTL_SECONDS:
        return True
    state[key] = now
    # Trim state to last 50 entries (oldest first by timestamp).
    if len(state) > 50:
        kept = sorted(state.items(), key=lambda kv: kv[1])[-50:]
        state = dict(kept)
    atomic_write_json(path, state)
    return False


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        _exit_silent()
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_silent()

    tool_name = envelope.get("tool_name") or ""
    if tool_name not in SUPPORTED_TOOLS:
        _exit_silent()

    tool_input = envelope.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        _exit_silent()

    workspace_str = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(workspace_str).resolve()

    specs = _scan_specs(workspace)
    if not specs:
        _exit_silent()

    matches: List[str] = []
    for slug, _path, body in specs:
        if _file_referenced_in_spec(file_path, body, workspace):
            matches.append(slug)

    if not matches:
        _exit_silent()

    # Dedupe per (file, spec_slug) tuple.
    rel = file_path
    try:
        rel = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        pass
    key = rel + "|" + ",".join(sorted(matches))
    if _is_duplicate(workspace, key):
        _exit_silent()

    spec_list = ", ".join(f"`{s}`" for s in matches[:3])
    lines = [
        f"[verify-nudge] File vừa Edit `{rel}` được reference bởi spec đang "
        f"`status: implementing|gaps-found`: {spec_list}",
        "",
        "Trước khi claim done, BẮT BUỘC chạy:",
    ]
    for slug in matches[:3]:
        lines.append(f"  · `/verify {slug}`")
    lines.extend([
        "",
        "Verify sẽ chạy lại acceptance_evals (nếu có) + emit Gap/Blocker/Pass "
        "table. Sau Verify clean → có thể commit + set spec `status: verified`.",
        "Tắt nhắc: rename `.claude/hooks/verify_nudge.py` hoặc remove khỏi "
        "settings.json (không phải tắt mỗi spec).",
    ])
    _emit("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
