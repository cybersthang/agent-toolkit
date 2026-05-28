#!/usr/bin/env python
"""Agent resilience supervisor (v0.24.0) — external, cross-platform.

Two modes:
  - DEFAULT (read-only watcher): observe the active session transcript +
    autonomy state. When autonomy is active and the transcript has been
    stale beyond `stall_seconds` (or the claude process is gone), NOTIFY the
    DEV (via tools/notify) so they can resume. NEVER kills/relaunches —
    works for BOTH the VSCode extension and the CLI. Safe; false-alarms are
    cheap because it only notifies.
  - `--relaunch` (CLI-only, opt-in): additionally auto-relaunch
    `claude -c -p "<resume brief>"` up to `relaunch_cap` times with
    exponential backoff; on cap exhaustion → notify DEV. (See T4.)

The read-only detect path (`check_once`) contains NO process kill / Popen —
that is asserted by the test suite (us2). Cross-platform: process-liveness
via `psutil` when available, else degrades to transcript-mtime only.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Import shared resume-state core (hooks dir) + notify (tools dir).
_HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(_HERE))  # tools/
sys.path.insert(0, str(_HERE.parent / "templates" / "claude" / "hooks"))
import notify  # noqa: E402
try:
    import _resume_state  # noqa: E402
except ImportError:  # pragma: no cover — degrade if hooks not on path
    _resume_state = None  # type: ignore

CONFIG_REL = ".agent-toolkit/resilience.json"

DEFAULTS: Dict[str, Any] = {
    "stall_seconds": 180,
    "notify_cooldown": 300,
    "relaunch_cap": 10,
    "backoff_base": 2,
    "cpu_idle_pct": 2.0,
    "notify": {"channels": ["log", "toast"]},
}


def load_config(workspace: Path) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    path = workspace / CONFIG_REL
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def encode_project_path(project_dir: Path) -> str:
    """Encode an absolute project path the way Claude Code names its
    `~/.claude/projects/<encoded>/` dir: lowercase drive, every non-alnum
    char → '-'. Best-effort (used only to auto-find the transcript)."""
    raw = str(project_dir.resolve())
    return re.sub(r"[^A-Za-z0-9]", "-", raw)


def find_active_transcript(project_dir: Path,
                           projects_root: Optional[Path] = None) -> Optional[Path]:
    """Return the most-recently-modified `.jsonl` transcript for this project
    under `~/.claude/projects/<encoded>/`, or None."""
    if projects_root is None:
        projects_root = Path.home() / ".claude" / "projects"
    enc = encode_project_path(project_dir)
    proj = projects_root / enc
    if not proj.is_dir():
        return None
    jsonls = list(proj.glob("*.jsonl"))
    return max(jsonls, key=lambda p: p.stat().st_mtime) if jsonls else None


def autonomy_active(workspace: Path, now: Optional[float] = None) -> bool:
    """True if `.autonomy_active.json` exists and not expired."""
    if _resume_state is None:
        return False
    data = _resume_state.read_autonomy(workspace)
    if not data:
        return False
    expires = data.get("expires_at")
    if not expires:
        return True
    from datetime import datetime
    try:
        sys.path.insert(0, str(_HERE.parent / "templates" / "claude" / "hooks"))
        from _common import parse_expires_at  # noqa: E402
        exp = parse_expires_at(expires)
    except Exception:
        return True
    if exp is None:
        return True
    now_dt = datetime.now(exp.tzinfo) if exp.tzinfo else datetime.now()
    return now_dt < exp


def is_stalled(transcript_path: Optional[Path], autonomy_on: bool,
               stall_seconds: int, now: float, proc_alive: bool = True) -> bool:
    """READ-ONLY stall decision. Stalled when autonomy is on AND (the claude
    process is gone OR the transcript has not advanced for > stall_seconds).
    Busy-but-silent long tasks keep writing the transcript → not stalled."""
    if not autonomy_on:
        return False
    if not proc_alive:
        return True
    if transcript_path is None or not transcript_path.exists():
        return False  # can't tell → don't false-alarm
    try:
        age = now - transcript_path.stat().st_mtime
    except OSError:
        return False
    return age > stall_seconds


def check_once(workspace: Path, transcript_path: Optional[Path],
               config: Dict[str, Any], now: Optional[float] = None,
               proc_alive: bool = True, last_notify_ts: float = 0.0
               ) -> Tuple[str, float]:
    """One read-only detection cycle. Returns (action, last_notify_ts).
    action ∈ {ok, notify, stalled-cooldown}. NEVER kills/relaunches."""
    if now is None:
        now = time.time()
    on = autonomy_active(workspace, now)
    if not is_stalled(transcript_path, on, int(config.get("stall_seconds", 180)),
                      now, proc_alive):
        return ("ok", last_notify_ts)
    cooldown = float(config.get("notify_cooldown", 300))
    if now - last_notify_ts < cooldown:
        return ("stalled-cooldown", last_notify_ts)
    brief = _resume_state.build_brief(workspace) if _resume_state else None
    idle = None
    if transcript_path and transcript_path.exists():
        try:
            idle = int(now - transcript_path.stat().st_mtime)
        except OSError:
            idle = None
    data = _resume_state.read_autonomy(workspace) if _resume_state else {}
    alert = {
        "spec": (data or {}).get("spec", "?"),
        "reason": "process exited" if not proc_alive else "transcript stale",
        "idle_seconds": idle,
        "brief": brief,
    }
    notify.dispatch(alert, config, workspace)
    return ("notify", now)


def build_relaunch_command(brief: Optional[str]) -> list:
    """`claude -c -p "<resume brief>"` — continue most-recent conversation
    headlessly with a resume prompt (bare `-c` would go interactive)."""
    prompt = brief or "Tiếp tục công việc autonomous đang dở (đọc scope manifest)."
    return ["claude", "-c", "-p", prompt]


def _default_run_claude(brief: Optional[str]) -> bool:
    """Run `claude -c -p`; True if it completed cleanly, False on a failure
    exit (529 exhaustion / crash). Detects API error in output as a hint."""
    import subprocess
    try:
        proc = subprocess.run(build_relaunch_command(brief),
                              capture_output=True, text=True, timeout=None)
    except (OSError, subprocess.SubprocessError):
        return False
    blob = f"{proc.stdout}\n{proc.stderr}".lower()
    if proc.returncode != 0:
        return False
    if "529" in blob or "api error" in blob or "overloaded" in blob:
        return False
    return True


def relaunch_loop(workspace: Path, config: Dict[str, Any],
                  run_claude=None, sleep_fn=None) -> Tuple[str, int]:
    """CLI-only (--relaunch): auto-relaunch `claude -c -p "<brief>"` up to
    `relaunch_cap` times with exponential backoff. On success → ('done', n).
    On cap exhaustion → notify DEV + return ('cap-exhausted', n).

    `run_claude` / `sleep_fn` injectable for tests. NOTE: this path DOES spawn
    a subprocess (relaunch) — distinct from the read-only `check_once`."""
    if run_claude is None:
        run_claude = _default_run_claude
    if sleep_fn is None:
        sleep_fn = time.sleep
    cap = int(config.get("relaunch_cap", 10))
    base = int(config.get("backoff_base", 2))
    attempts = 0
    for attempt in range(cap):
        brief = _resume_state.build_brief(workspace) if _resume_state else None
        attempts += 1
        if run_claude(brief):
            return ("done", attempts)
        if attempt < cap - 1:
            sleep_fn(base ** (attempt + 1))
    # All `cap` relaunches failed → give up + notify (do NOT relaunch again).
    data = _resume_state.read_autonomy(workspace) if _resume_state else {}
    notify.dispatch({
        "spec": (data or {}).get("spec", "?"),
        "reason": f"auto-relaunch cạn cap ({cap} lần) — cần DEV xử lý",
        "idle_seconds": None,
        "brief": _resume_state.build_brief(workspace) if _resume_state else None,
    }, config, workspace)
    return ("cap-exhausted", attempts)


def _proc_alive_by_name(name: str = "claude") -> bool:
    """Best-effort: is there a live `claude` process? Uses psutil if present,
    else assume alive (degrade — transcript-mtime path still works)."""
    try:
        import psutil  # type: ignore
    except ImportError:
        return True
    try:
        for p in psutil.process_iter(["name"]):
            if name in (p.info.get("name") or "").lower():
                return True
        return False
    except Exception:  # noqa: BLE001
        return True


if __name__ == "__main__":  # pragma: no cover — CLI loop
    import argparse
    ap = argparse.ArgumentParser(description="Agent resilience supervisor")
    ap.add_argument("--project-dir", default=os.getcwd())
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--relaunch", action="store_true",
                    help="CLI-only: auto-relaunch claude (see T4)")
    args = ap.parse_args()
    ws = Path(args.project_dir).resolve()
    cfg = load_config(ws)
    tp = Path(args.transcript) if args.transcript else find_active_transcript(ws)
    last = 0.0
    while True:
        tp = tp or find_active_transcript(ws)
        action, last = check_once(ws, tp, cfg, proc_alive=_proc_alive_by_name(),
                                  last_notify_ts=last)
        time.sleep(max(5, args.interval))
