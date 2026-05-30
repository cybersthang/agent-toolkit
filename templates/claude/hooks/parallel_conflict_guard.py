#!/usr/bin/env python
"""PreToolUse hook — parallel-subagent conflict guard (v0.25.0, status
DEGRADED v0.27 — see KNOWN LIMITATION below).

When the main agent has declared a wave of concurrent sub-agents via
`tools/parallel_wave.py emit` (writing `.agent-toolkit/.parallel_wave.json`),
this hook BLOCKs any Edit/Write/MultiEdit whose target file is owned by a
DIFFERENT agent than the one making the call.

Rule (D8): for the incoming PreToolUse envelope:
  - `agent_id` field present → sub-agent (docs: hooks.md "Common Input Fields"
    "Only in subagents").
  - `agent_id` field absent → main agent.
A file F is "in zone Z" when it matches any pattern in `Z.owned` (D4 smart
match: glob with `*`, dir-prefix with trailing `/`, else exact path). If
F ∈ Z and `envelope.agent_id != Z.agent_id` → BLOCK.

KNOWN LIMITATION (B2, field-verified 2026-05-28, v0.27 audit):
  Claude Code currently does NOT include `agent_id` in PreToolUse /
  PostToolUse envelopes — it only appears in SubagentStart / SubagentStop
  events. See anthropics/claude-code#40140 (feature request open). Effect:
  `envelope.agent_id` is None for every Edit/Write call, so the guard
  treats every edit as the "main agent" and cross-zone edits from
  sub-agents are NOT blocked in real-world Claude Code today. The guard
  remains correct + tested for the *future* envelope shape via synthetic
  fixtures; it is currently advisory at runtime.
  Mitigations until upstream adds the field:
    1. Treat parallel-batching as conventional/honor-system, not enforced.
    2. Use `tools/parallel_wave.py emit` to declare zones so DEV review
       can spot violations in the transcript even if the guard didn't fire.
    3. Watch the linked issue and remove this limitation block once the
       field lands.

Silent allow (exit 0, zero output) when:
  - Kill-switch `AGENT_TOOLKIT_DISABLE=1`.
  - Manifest missing / TTL expired / `wave_done: true` (lifecycle, D5).
  - Target file outside every declared zone (us5 zero-friction).
  - Same-owner edit (us4).
  - Bypass token `.skip_parallel_guard_next.json` fresh (consumed).

Enforce mode via `get_enforce_mode(workspace, "parallel_conflict_guard")`:
  - `block` (default — D3, matches sibling guards).
  - `warn` (additionalContext nudge + permissionDecision allow).
  - `off` (silent allow).

Fail-open on unexpected error (wrapped by run_main_safe).
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    run_main_safe, emit_fire_event, get_enforce_mode,
)

# UTF-8 stdin/stdout/stderr — Vietnamese-friendly + Windows-safe.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Kill-switch.
if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
    sys.exit(0)


MANIFEST_REL = ".agent-toolkit/.parallel_wave.json"
SKIP_TOKEN_REL = ".agent-toolkit/.skip_parallel_guard_next.json"
HOOK_NAME = "parallel_conflict_guard"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


# ---------------------------------------------------------------- exits

def _exit_allow(detail: Optional[str] = None) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="allow", detail=detail)
    except Exception:
        pass
    # PreToolUse: an empty exit-0 means "no decision, defer" — that's what we
    # want for silent allow. For explicit allow we could emit a JSON envelope,
    # but exit-0 silent is the standard pattern for PreToolUse permit.
    return 0


def _exit_block(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="block", detail=reason[:200])
    except Exception:
        pass
    # PreToolUse block envelope.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    return 0


def _exit_warn(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=reason[:200])
    except Exception:
        pass
    sys.stderr.write(f"[parallel-conflict-guard] warn: {reason}\n")
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
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _manifest_active(manifest: Dict[str, Any], now: float) -> bool:
    """Manifest is active when wave_done is false and TTL has not expired.

    A manifest with a missing / zero `ttl_seconds` previously short-circuited
    the expiry check (`created and ttl and ...`) and was treated as active
    FOREVER. Apply a 1h default TTL so a stale, un-TTL'd manifest expires."""
    if manifest.get("wave_done"):
        return False
    DEFAULT_TTL_SECONDS = 3600
    ttl = manifest.get("ttl_seconds")
    ttl = int(ttl) if ttl else DEFAULT_TTL_SECONDS
    created = int(manifest.get("created_ts") or 0)
    if created and now > created + ttl:
        return False
    return True


def _zone_matches(file_rel: str, owned: List[str]) -> bool:
    """D4 smart match: glob with `*`, dir-prefix with trailing `/`, else
    exact path. All compared as forward-slash relative paths."""
    file_rel = file_rel.replace("\\", "/")
    for raw in owned or []:
        pat = str(raw).replace("\\", "/")
        if "*" in pat or "?" in pat or "[" in pat:
            if fnmatch.fnmatch(file_rel, pat):
                return True
        elif pat.endswith("/"):
            if file_rel == pat.rstrip("/") or file_rel.startswith(pat):
                return True
        else:
            if file_rel == pat:
                return True
    return False


def _normalize_target(workspace: Path, raw: Any) -> Optional[str]:
    """Return workspace-relative forward-slash path, or None."""
    if not isinstance(raw, str) or not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        # tool_input.file_path is usually absolute; if relative, resolve vs cwd.
        p = (workspace / p).resolve()
    else:
        try:
            p = p.resolve()
        except OSError:
            return None
    try:
        rel = p.relative_to(workspace)
    except ValueError:
        # Outside workspace — use absolute as-is for owned comparison.
        return str(p).replace("\\", "/")
    return str(rel).replace("\\", "/")


def _owner_of(file_rel: str, zones: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for z in zones:
        if not isinstance(z, dict):
            continue
        if _zone_matches(file_rel, z.get("owned") or []):
            return z
    return None


def _consume_bypass(workspace: Path) -> Optional[str]:
    """Mirror sibling tokens (gap-gate / git-guard): mtime TTL 600s, single-shot."""
    token = workspace / SKIP_TOKEN_REL
    if not token.exists():
        return None
    try:
        st = token.stat()
        if time.time() - st.st_mtime > 600:
            token.unlink()
            return None
        data = json.loads(token.read_text(encoding="utf-8-sig"))
        reason = (data or {}).get("reason") if isinstance(data, dict) else None
        token.unlink()
        return reason or "bypass"
    except (OSError, json.JSONDecodeError):
        try:
            token.unlink()
        except OSError:
            pass
        return None


# ---------------------------------------------------------------- main

def _main() -> int:
    raw = sys.stdin.read()
    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return _exit_allow(detail="bad-json")

    tool_name = envelope.get("tool_name") or ""
    if tool_name not in EDIT_TOOLS:
        return _exit_allow(detail=f"skip:{tool_name}")

    workspace = _find_workspace(envelope.get("cwd"))
    manifest = _read_json(workspace / MANIFEST_REL)
    if not manifest:
        return _exit_allow(detail="no-manifest")
    if not _manifest_active(manifest, time.time()):
        return _exit_allow(detail="inactive")

    zones = manifest.get("zones") or []
    if not isinstance(zones, list) or not zones:
        return _exit_allow(detail="empty-zones")

    tool_input = envelope.get("tool_input") or {}
    target_raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    file_rel = _normalize_target(workspace, target_raw)
    if not file_rel:
        return _exit_allow(detail="no-target")

    owner = _owner_of(file_rel, zones)
    if owner is None:
        return _exit_allow(detail="outside-zone")  # us5

    editor_id = envelope.get("agent_id")  # None for main agent (D1)
    owner_id = owner.get("agent_id")
    if editor_id == owner_id:
        return _exit_allow(detail=f"same-owner:{owner_id}")  # us4

    # Cross-zone conflict (D8) — try bypass first.
    bypass_reason = _consume_bypass(workspace)
    if bypass_reason:
        return _exit_allow(detail=f"bypass:{bypass_reason[:80]}")

    reason_lines = [
        f"Edit '{file_rel}' bị BLOCK: file thuộc zone của agent "
        f"`{owner_id}` (wave `{manifest.get('wave','?')}`)",
        f"Editor hiện tại: `{editor_id or 'main-agent'}` — KHÁC owner → "
        f"cross-zone conflict (xem v0.25 parallel-subagent-guard).",
        "Cách xử lý:",
        f"  1. Đổi sub-agent: chỉ `{owner_id}` được sửa file này trong wave.",
        "  2. Bypass 1 lần: DEV gõ `bypass-parallel-guard: <reason ≥ 8 chars>`.",
        "  3. Wave xong: `python tools/parallel_wave.py declare-done` (hoặc `clear`).",
    ]
    reason = "\n".join(reason_lines)

    mode = get_enforce_mode(workspace, HOOK_NAME, default="block")
    if mode == "off":
        return _exit_allow(detail=f"off;owner={owner_id}")
    if mode == "warn":
        return _exit_warn(reason)
    return _exit_block(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(_main))
