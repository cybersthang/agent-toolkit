#!/usr/bin/env python
"""Stop hook — implement-notes advisory (warn-only).

After a turn ends, if the assistant text contains an "implement done"
style claim (vd: "implement done", "implement xong", "sprint hoàn tất",
"feature ready for review"), the hook checks for the existence of
`<workspace>/.agent-toolkit/specs/**/<slug>.implement-noted.md` for
the current git branch's slug.

If missing → emit `additionalContext` line:
  [implement-notes-gate] Turn này claim implement done nhưng
  `.agent-toolkit/specs/<branch>/<slug>.implement-noted.md` chưa có.
  Chạy `/implement-notes <slug>` để AGENT generate file.

The hook is **warn-only**. It NEVER blocks Stop. Honor-system
enforcement; promoted to hard-block only when DEV opts in via
`<workspace>/.agent-toolkit/implement_notes.json` `"enforce": "block"`.

Bypass single-shot: response containing `implement-notes: skip
<reason>` (anywhere in text) → silent skip + log event.

Fails open: any exception → exit 0 silent.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, split_current_turn,
    run_main_safe, get_enforce_mode,
)

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/implement_notes.json"
LOG_REL = ".agent-toolkit/.implement_notes_gate_log.json"
LOG_MAX_EVENTS = 50

DONE_CLAIM_RE = re.compile(
    r"\b("
    r"implement\s+done"
    r"|implement\s+xong"
    r"|implementation\s+(?:done|complete|finished)"
    r"|sprint\s+(?:hoàn\s*tất|done|complete|finished)"
    r"|feature\s+ready\s+for\s+(?:review|/verify)"
    r"|(?:R[1-9]|S[1-9])(?:\.\d+)?(?:\s+all)?\s+(?:hoàn\s*tất|done|complete)"
    r")\b",
    re.IGNORECASE,
)

BYPASS_MARKER_RE = re.compile(
    r"implement-notes\s*:\s*skip\b", re.IGNORECASE,
)

TRUNK_BRANCHES = {"main", "master", "trunk", "develop"}


def _exit_silent() -> None:
    sys.exit(0)


def _emit_warn(message: str) -> None:
    """Non-blocking; emit additionalContext per Stop hook contract."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _emit_block(reason: str) -> None:
    """Phase D v0.9.0: blocking variant per enforce_mode.json `block`."""
    print(json.dumps({"decision": "block", "reason": reason},
                     ensure_ascii=False))
    sys.exit(0)


def _resolve_branch(workspace: Path) -> str:
    """Return current git branch; empty string if not a repo."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out and out != "HEAD":
                return out
        proc2 = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if proc2.returncode == 0:
            return proc2.stdout.strip()
        return ""
    except (subprocess.SubprocessError, OSError):
        return ""


def _branch_to_slug(branch: str) -> str:
    if "/" in branch:
        return branch.rsplit("/", 1)[1]
    return branch


def _spec_for_branch(workspace: Path, branch_slug: str) -> Optional[Path]:
    """Return path to `<slug>.md` if exists under .agent-toolkit/specs/, else None."""
    specs_dir = workspace / ".agent-toolkit" / "specs"
    if not specs_dir.is_dir():
        return None
    for p in specs_dir.rglob(f"{branch_slug}.md"):
        if p.stem == branch_slug:
            return p
    return None


def _implement_notes_path(spec_path: Path) -> Path:
    """Return expected implement-noted sidecar path next to spec."""
    return spec_path.parent / f"{spec_path.stem}.implement-noted.md"


def _extract_assistant_text(turn: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text") or "")
    return "\n".join(parts)


def _has_done_claim(text: str) -> bool:
    return bool(DONE_CLAIM_RE.search(text))


def _has_bypass_marker(text: str) -> bool:
    return bool(BYPASS_MARKER_RE.search(text))


def _log_event(workspace: Path, event: Dict[str, Any]) -> None:
    log_path = workspace / LOG_REL
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        existing: List[Dict[str, Any]] = []
        if log_path.exists():
            try:
                data = json.loads(log_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    existing = data.get("events") or []
                elif isinstance(data, list):
                    existing = data
            except (json.JSONDecodeError, OSError):
                existing = []
        existing.append(event)
        existing = existing[-LOG_MAX_EVENTS:]
        log_path.write_text(
            json.dumps({"events": existing}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _load_config(workspace: Path) -> Dict[str, Any]:
    path = workspace / CONFIG_REL
    cfg: Dict[str, Any] = {"enabled": True, "enforce": "warn"}
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(override, dict):
                cfg.update(override)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_silent()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_silent()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_silent()

    if envelope.get("stop_hook_active"):
        _exit_silent()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    cfg = _load_config(workspace)
    if not cfg.get("enabled"):
        _exit_silent()

    transcript_path = envelope.get("transcript_path")
    if not transcript_path:
        _exit_silent()
    tpath = Path(transcript_path)
    if not tpath.exists():
        _exit_silent()

    messages = read_jsonl_transcript(tpath)
    if not messages:
        _exit_silent()

    turn = split_current_turn(messages)
    asst_text = _extract_assistant_text(turn)

    if not asst_text:
        _exit_silent()

    if _has_bypass_marker(asst_text):
        _log_event(workspace, {
            "ts": int(time.time()),
            "kind": "bypass",
        })
        _exit_silent()

    if not _has_done_claim(asst_text):
        _exit_silent()

    branch = _resolve_branch(workspace)
    if not branch or branch in TRUNK_BRANCHES:
        _exit_silent()

    branch_slug = _branch_to_slug(branch)
    spec_path = _spec_for_branch(workspace, branch_slug)
    if not spec_path:
        _exit_silent()

    notes_path = _implement_notes_path(spec_path)
    if notes_path.exists():
        _log_event(workspace, {
            "ts": int(time.time()),
            "kind": "ok",
            "slug": branch_slug,
        })
        _exit_silent()

    _log_event(workspace, {
        "ts": int(time.time()),
        "kind": "warn",
        "slug": branch_slug,
        "expected_path": str(notes_path),
    })

    rel = str(notes_path)
    try:
        rel = str(notes_path.relative_to(workspace))
    except (ValueError, OSError):
        pass

    message = (
        f"[implement-notes-gate] Turn này claim implement done nhưng "
        f"`{rel}` chưa có. Chạy `/implement-notes {branch_slug}` để AGENT "
        f"walk transcript + emit file 4-section (scope deviations + "
        f"in-transcript trade-offs + open follow-ups + confidence summary). "
        f"Bypass single-shot: thêm `implement-notes: skip <reason>` vào "
        f"response."
    )
    # Phase D v0.9.0: honor enforce_mode.json — escalate to block if configured
    mode = get_enforce_mode(workspace, "implement_notes_gate",
                            default=cfg.get("enforce") or "warn")
    if mode == "block":
        _emit_block(message)
    _emit_warn(message)
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
