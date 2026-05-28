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


# ============================================================
# v0.26.0 — sub-agent multi-transcript stall watcher
#
# Extends the single-transcript main-session path with a second mode that
# auto-activates when v0.25 `.parallel_wave.json` declares an active wave
# of concurrent sub-agents. Each sub-agent has its own `<session>.jsonl`
# under the same `~/.claude/projects/<encoded>/` dir (verified per Claude
# Code docs sessions.md). When any sub-agent's transcript goes stale past
# the (sub-agent) stall threshold, dispatch ONE aggregate notify per tick
# listing all stalled transcripts. Notify-only — sub-agents are Agent-tool
# spawned (model-only) so the toolkit cannot relaunch them.
#
# Closes the gap documented at v0.24 §5 D11 + v0.25 §7 Out-of-scope.
# ============================================================

PARALLEL_WAVE_REL = ".agent-toolkit/.parallel_wave.json"


def read_parallel_wave_manifest(workspace: Path) -> Optional[Dict[str, Any]]:
    """Read the v0.25 wave manifest if present + active (not done, not TTL-
    expired). Returns the dict or None. Used as activation guard for the
    sub-agent multi-transcript watcher (D4)."""
    path = workspace / PARALLEL_WAVE_REL
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return None
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("wave_done"):
        return None
    created = int(data.get("created_ts") or 0)
    ttl = int(data.get("ttl_seconds") or 0)
    if created and ttl and time.time() > created + ttl:
        return None
    return data


def discover_sub_agent_transcripts(workspace: Path,
                                   manifest: Dict[str, Any],
                                   projects_root: Optional[Path] = None
                                   ) -> List[Path]:
    """List sub-agent `.jsonl` transcripts in the project's transcript dir
    that (a) appeared/were modified AFTER the wave was emitted and (b) are
    NOT the main-session transcript. Per D1 we do not bridge agent_id →
    session_id in Phase 1 — DEV correlates via the filename in notify."""
    if projects_root is None:
        projects_root = Path.home() / ".claude" / "projects"
    enc = encode_project_path(workspace)
    proj = projects_root / enc
    if not proj.is_dir():
        return []
    main = find_active_transcript(workspace, projects_root=projects_root)
    created = int((manifest or {}).get("created_ts") or 0)
    out: List[Path] = []
    for p in proj.glob("*.jsonl"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if created and mtime < created:
            continue
        if main is not None and p.resolve() == main.resolve():
            continue
        out.append(p)
    return out


def _subagent_stall_seconds(config: Dict[str, Any]) -> int:
    """D4: optional `subagent_stall_seconds` override; fallback to main
    `stall_seconds`."""
    sub = config.get("subagent_stall_seconds")
    if isinstance(sub, int) and sub > 0:
        return sub
    return int(config.get("stall_seconds", 180))


def check_subagent_transcripts(workspace: Path,
                               manifest: Optional[Dict[str, Any]],
                               config: Dict[str, Any],
                               now: Optional[float] = None,
                               last_notify_per_transcript: Optional[Dict[str, float]] = None,
                               projects_root: Optional[Path] = None
                               ) -> Optional[Dict[str, Any]]:
    """Per-tick sub-agent stall detection. Returns None when the multi-
    transcript mode is inactive (D4 activation guard: no manifest / done /
    TTL / autonomy off). Otherwise returns
    `{stalled: [paths], last_notify_per_transcript: {...}}` and may have
    dispatched a notify side-effect.

    Aggregate semantics (D2): ONE dispatch per tick listing every stalled
    transcript that has passed its per-transcript cooldown (D3). NEVER kills
    or relaunches — Phase 1 notify-only (D8)."""
    if manifest is None:
        return None
    if not autonomy_active(workspace, now):
        return None
    if now is None:
        now = time.time()
    if last_notify_per_transcript is None:
        last_notify_per_transcript = {}
    transcripts = discover_sub_agent_transcripts(workspace, manifest,
                                                 projects_root=projects_root)
    if not transcripts:
        return {"stalled": [], "last_notify_per_transcript": last_notify_per_transcript}

    threshold = _subagent_stall_seconds(config)
    cooldown = float(config.get("notify_cooldown", 300))
    stalled: List[Dict[str, Any]] = []
    for tp in transcripts:
        try:
            idle = now - tp.stat().st_mtime
        except OSError:
            continue
        if idle <= threshold:
            continue
        key = str(tp)
        if now - last_notify_per_transcript.get(key, 0.0) < cooldown:
            continue
        stalled.append({"path": tp, "idle_seconds": int(idle)})

    if stalled:
        worst = max(s["idle_seconds"] for s in stalled)
        alert = {
            "kind": "sub-agent",
            "spec": (manifest or {}).get("wave", "?"),
            "wave": manifest.get("wave", "?"),
            "transcript": ", ".join(str(s["path"]) for s in stalled),
            "stalled_count": len(stalled),
            "idle_seconds": worst,
            "reason": f"{len(stalled)} sub-agent transcript stale > {threshold}s",
            "brief": _resume_state.build_brief(workspace) if _resume_state else None,
        }
        notify.dispatch(alert, config, workspace)
        for s in stalled:
            last_notify_per_transcript[str(s["path"])] = now

    return {"stalled": [str(s["path"]) for s in stalled],
            "last_notify_per_transcript": last_notify_per_transcript}


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
    last_per_transcript: Dict[str, float] = {}
    while True:
        tp = tp or find_active_transcript(ws)
        # v0.24 main-session path (unchanged).
        action, last = check_once(ws, tp, cfg, proc_alive=_proc_alive_by_name(),
                                  last_notify_ts=last)
        # v0.26 sub-agent multi-transcript path (D6 single-loop two-mode).
        # Auto-activates only when a v0.25 wave manifest is active; otherwise
        # returns None and the loop continues exactly like v0.24.
        manifest = read_parallel_wave_manifest(ws)
        if manifest is not None:
            result = check_subagent_transcripts(
                ws, manifest, cfg, last_notify_per_transcript=last_per_transcript)
            if result is not None:
                last_per_transcript = result["last_notify_per_transcript"]
        time.sleep(max(5, args.interval))
