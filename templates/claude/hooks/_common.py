"""Shared utilities for `.claude/hooks/*.py`.

Centralizes patterns that were duplicated across 8 hooks before the
2026-05-18 refactor:

- UTF-8 stdin/stdout wrapping (Windows safety).
- Atomic JSON write (temp + os.replace) — fixes TOCTOU race between
  parallel PostToolUse hooks each updating their own state cache.
- Workspace-relative glob matching with `**` support — fnmatch alone
  doesn't handle recursive wildcards correctly.
- Workspace-root discovery — walk up from `cwd` looking for
  `.agent-toolkit/specs`.
- MCP prefix discovery — fall back to scanning `.mcp.json` when the
  static config in `.agent-toolkit/verification.json` is a generic
  placeholder. Lets the toolkit drop project-specific defaults.

The hooks all start with the snippet below (NOT a function, since `sys`
needs to be wrapped at module init time before stdin is read):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from _common import wrap_utf8_stdio, atomic_write_json, match_glob, ...
    wrap_utf8_stdio()

Toolkit-invariant: this module ships from agent-toolkit; project-specific
data lives in `.agent-toolkit/*.json` and `.codex/canonical_decisions.json`.
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def wrap_utf8_stdio() -> None:
    """Wrap stdin/stdout as UTF-8 so Vietnamese / non-Latin text survives
    on Windows (default cp1252) and broken locales."""
    if hasattr(sys.stdin, "buffer"):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8",
                                     errors="replace")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")


def atomic_write_json(path: Path, data: Any) -> bool:
    """Atomic JSON write via temp file + os.replace.

    Concurrent PostToolUse hooks (3 fire in parallel) each maintain their
    own state cache. Without atomic write, `path.write_text` can interleave
    between read and write, corrupting the JSON file. `os.replace` is
    atomic on POSIX and Windows (≥ Vista). Worst case: last writer wins;
    file is never corrupted.

    Returns True on success, False on any IO error (fail-open).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Use NamedTemporaryFile in same dir so os.replace stays on same FS.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False,
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp",
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, str(path))
        return True
    except OSError:
        # Clean up temp file if rename failed.
        try:
            os.unlink(tmp_path)  # type: ignore[name-defined]
        except (OSError, NameError):
            pass
        return False


def match_glob(
    file_path: str,
    globs: Iterable[str],
    workspace: Path,
    empty_returns: bool = True,
) -> bool:
    """True if `file_path` matches any glob in `globs`.

    Handles both workspace-relative and absolute paths. Empty/missing
    globs default to "applies to all" (`empty_returns=True`) — set to
    False for callers that want "no globs = don't match".

    Adds lenient `**` matching since `fnmatch.fnmatch` only supports
    shell-style wildcards.
    """
    globs = list(globs or [])
    if not globs:
        return empty_returns
    try:
        rel = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel = file_path.replace("\\", "/")
    abs_path = file_path.replace("\\", "/")
    for pattern in globs:
        pat = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(abs_path, pat):
            return True
        if "**" in pat:
            head = pat.split("**", 1)[0].rstrip("/")
            tail = pat.split("**", 1)[1].lstrip("/")
            if (not head or rel.startswith(head)) and (
                not tail or rel.endswith(tail.lstrip("*").lstrip("/"))
            ):
                return True
    return False


def find_workspace_root(start: Path) -> Optional[Path]:
    """Walk up from `start` looking for a directory containing
    `.agent-toolkit/specs` (the canonical toolkit marker). Returns the
    first such directory, or None if not found."""
    cursor = start.resolve()
    while True:
        if (cursor / ".agent-toolkit" / "specs").is_dir():
            return cursor
        if cursor.parent == cursor:
            return None
        cursor = cursor.parent


def discover_mcp_prefix(
    workspace: Path,
    config_value: Optional[str] = None,
    exclude_servers: Iterable[str] = ("playwright",),
) -> str:
    """Discover the MCP tool-name prefix for the current project.

    Order of preference:
    1. `config_value` if it's a concrete prefix (not a placeholder /
       generic default).
    2. First MCP server declared in `.mcp.json` (excluding generic ones
       like `playwright` that ship cross-project).
    3. Fall back to `mcp__` (matches any MCP tool — broadest).

    Returns the prefix string ending with `__`.
    """
    # 1. Trust explicit config if it doesn't look like a placeholder.
    if config_value:
        cfg = config_value.strip()
        # Placeholder shapes we should not trust.
        placeholders = ("<", "{{", "${", "mcp__<", "PROJECT-STACK")
        if cfg.endswith("__") and not any(p in cfg for p in placeholders):
            return cfg

    # 2. Scan `.mcp.json` for the first stdio server name.
    mcp_path = workspace / ".mcp.json"
    if mcp_path.exists():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers") if isinstance(data, dict) else None
            if isinstance(servers, dict):
                for name in servers:
                    if name in exclude_servers:
                        continue
                    if isinstance(name, str) and name.strip():
                        return f"mcp__{name}__"
        except (OSError, json.JSONDecodeError):
            pass

    # 3. Last resort: broad prefix.
    return "mcp__"


def emit_post_tool_context(text: str) -> None:
    """PostToolUse hook stdout envelope. Exits 0 after print."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def emit_stop_context(text: str) -> None:
    """Stop hook stdout envelope (non-blocking warning)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def emit_stop_block(reason: str) -> None:
    """Stop hook block envelope. Exits 0 after print."""
    print(json.dumps({"decision": "block", "reason": reason},
                     ensure_ascii=False))
    sys.exit(0)


# ============================================================
# P9 v0.8.0 — hook crash policy wrapper
#
# Each hook's main() can be wrapped via `run_main_safe(main)` so any
# uncaught exception is logged to `.agent-toolkit/.hook_crash_log.json`
# (ring buffer last 50 events) and the hook exits 0 (fail-open). DEV
# can grep the log to find hooks misbehaving.
# ============================================================
import traceback as _traceback  # noqa: E402

_CRASH_LOG_REL = ".agent-toolkit/.hook_crash_log.json"
_CRASH_LOG_MAX = 50


def _resolve_crash_workspace() -> "Path":
    """Best-effort workspace root resolution for crash logging.
    Falls back to cwd if .agent-toolkit/ not found."""
    cursor = Path.cwd().resolve()
    while True:
        if (cursor / ".agent-toolkit").is_dir():
            return cursor
        if cursor.parent == cursor:
            return Path.cwd()
        cursor = cursor.parent


def _log_hook_crash(hook_name: str, exc: BaseException) -> None:
    """Append crash event to ring buffer. Silent on failure."""
    import time
    try:
        workspace = _resolve_crash_workspace()
        log_path = workspace / _CRASH_LOG_REL
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
        existing.append({
            "ts": int(time.time()),
            "hook": hook_name,
            "exc_type": type(exc).__name__,
            "exc_msg": str(exc)[:500],
            "traceback_tail": _traceback.format_exc()[-1500:],
        })
        existing = existing[-_CRASH_LOG_MAX:]
        # v0.21 T01 (B2): atomic write — prevent telemetry corruption from
        # concurrent hook crashes.
        atomic_write_json(log_path, {"events": existing})
    except (OSError, Exception):  # noqa: BLE001
        pass  # crash logger crashed — give up silently


def parse_expires_at(ts_str: str) -> "Optional[Any]":
    """Parse ISO 8601 datetime string handling 5 formats safely.

    Handles: naive ISO, +HH:MM, +HHMM (bare offset), Z suffix, UTC.
    Returns None on any parse failure — never raises.

    Usage pattern for expiry check:
        exp_dt = parse_expires_at(data.get("expires_at") or "")
        if exp_dt is None:
            return True  # treat as active (fail-open)
        now = datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now()
        return now < exp_dt
    """
    from datetime import datetime
    import re as _re
    if not ts_str:
        return None
    normalized = ts_str.strip()
    # Insert colon into bare offset like +0700 → +07:00 for fromisoformat.
    normalized = _re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", normalized)
    # Normalize Z suffix to +00:00.
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        pass
    # Fallback: strip tz suffix + strptime as naive.
    bare = ts_str.split(".")[0].split("+")[0].split("Z")[0].strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(bare, fmt)
        except ValueError:
            continue
    return None


def is_strict_mode() -> bool:
    """v0.20.0 — fail-CLOSED by default. Set AGENT_TOOLKIT_NO_STRICT=1
    to revert to fail-open (legacy dev-friendly behavior).

    Breaking change from v0.9.0: the old AGENT_TOOLKIT_STRICT=1 opt-in
    is replaced by AGENT_TOOLKIT_NO_STRICT=1 opt-out. Existing installs
    that relied on fail-open behavior MUST set AGENT_TOOLKIT_NO_STRICT=1
    — hook crashes will now block instead of silently allowing.
    See QUICKSTART.odoo.md §Breaking change v0.20.
    """
    return os.environ.get("AGENT_TOOLKIT_NO_STRICT") != "1"


def get_enforce_mode(workspace: Path, hook_name: str,
                     default: str = "warn") -> str:
    """Phase D v0.9.0 — return per-hook enforce mode from
    `.agent-toolkit/enforce_mode.json`. Falls back to `default`.

    Schema:
        {
          "default": "warn",
          "per_hook": {
            "spec_first_guard": "warn",
            "implement_notes_gate": "block",
            ...
          }
        }

    STRICT mode (AGENT_TOOLKIT_STRICT=1) globally overrides → "block"
    regardless of config (CI safety).
    """
    if is_strict_mode():
        return "block"
    config_path = workspace / ".agent-toolkit" / "enforce_mode.json"
    if not config_path.exists():
        return default
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return default
    if not isinstance(cfg, dict):
        return default
    per_hook = cfg.get("per_hook") or {}
    if isinstance(per_hook, dict) and hook_name in per_hook:
        mode = per_hook[hook_name]
        if mode in ("warn", "block"):
            return mode
    fallback = cfg.get("default")
    if fallback in ("warn", "block"):
        return fallback
    return default


_FIRE_LOG_REL = ".agent-toolkit/.hook_fire_log.json"
_FIRE_LOG_MAX = 1000


def emit_fire_event(hook_name: str, verdict: str = "ok",
                    duration_ms: Optional[int] = None,
                    detail: Optional[str] = None) -> None:
    """Phase C v0.9.0 — log a hook fire event to ring buffer.

    Called by hooks to record that they fired + what verdict + how long.
    Aggregator `hook_health.py` reads this buffer to surface health
    metrics. Silent on failure (logging is best-effort).
    """
    import time
    try:
        workspace = _resolve_crash_workspace()
        log_path = workspace / _FIRE_LOG_REL
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
        event = {"ts": int(time.time()), "hook": hook_name, "verdict": verdict}
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        if detail:
            event["detail"] = detail[:200]
        existing.append(event)
        existing = existing[-_FIRE_LOG_MAX:]
        # v0.21 T01 (B2): atomic write — telemetry log shared by all hooks.
        atomic_write_json(log_path, {"events": existing})
    except (OSError, Exception):  # noqa: BLE001
        pass


def emit_timed_fire(hook_name: str, verdict: str,
                    start_monotonic: float,
                    detail: Optional[str] = None) -> None:
    """v0.21 T07 — emit_fire_event with duration_ms auto-computed.

    Usage at hook exit paths:
        import time
        _start = time.monotonic()
        ...
        emit_timed_fire("my_hook.py", "allow", _start)

    Mitigates B3 (Stop chain latency invisibility): hook_health aggregator
    surfaces hooks with high p50/p99 duration so DEV knows which hook to
    tune. Helper auto-handles `time.monotonic() - start` in ms.
    """
    import time
    duration_ms = int((time.monotonic() - start_monotonic) * 1000)
    emit_fire_event(hook_name, verdict=verdict,
                    duration_ms=duration_ms, detail=detail)


def run_main_safe(main_fn) -> int:
    """Wrap a hook's main() with try/except + timing telemetry.

    Usage at the bottom of each hook:
        if __name__ == "__main__":
            sys.exit(run_main_safe(main))

    Default (fail-CLOSED from v0.20.0): uncaught exception → log to
    .hook_crash_log.json + exit 1 (hook crash blocks the response).
    Set AGENT_TOOLKIT_NO_STRICT=1 to revert to fail-open (exit 0).

    v0.21 (T08+T09 — H6 + S9): EVERY hook now auto-emits a fire event
    with `duration_ms` at exit. Closes 15-hook telemetry blind spot
    + B3 timing-visibility mitigation in one wrapper update.
    """
    import inspect
    import time
    start_monotonic = time.monotonic()
    hook_name = "unknown"
    try:
        src = inspect.getsourcefile(main_fn) or ""
        hook_name = Path(src).name
    except (TypeError, OSError):
        pass

    try:
        rv = main_fn()
        code = int(rv) if isinstance(rv, int) else 0
        verdict = "block" if code == 2 else ("error" if code == 1 else "ok")
        try:
            emit_timed_fire(hook_name, verdict, start_monotonic,
                            detail="run_main_safe")
        except Exception:
            pass
        return code
    except SystemExit as exit_exc:
        # honor explicit sys.exit() calls from inside main
        code = exit_exc.code
        code_int = int(code) if isinstance(code, int) else 0
        verdict = "block" if code_int == 2 else ("error" if code_int == 1 else "ok")
        try:
            emit_timed_fire(hook_name, verdict, start_monotonic,
                            detail="sys.exit")
        except Exception:
            pass
        return code_int
    except BaseException as exc:  # noqa: BLE001
        _log_hook_crash(hook_name, exc)
        try:
            emit_timed_fire(hook_name, "crash", start_monotonic,
                            detail=type(exc).__name__[:50])
        except Exception:
            pass
        # Phase E: STRICT mode → propagate exit 1; default fail-open → exit 0
        if is_strict_mode():
            return 1
        return 0


def read_jsonl_transcript(path: Path) -> List[Dict[str, Any]]:
    """Parse a JSONL transcript file. Lines that fail JSON parse are
    silently skipped (Claude Code occasionally writes partial lines)."""
    out: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def split_current_turn(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return messages from the most-recent user prompt to the end.
    If no user message found, returns all messages."""
    last_user = -1
    for idx in range(len(messages) - 1, -1, -1):
        m = messages[idx]
        if m.get("type") == "user" or m.get("role") == "user":
            last_user = idx
            break
    return messages[last_user:] if last_user >= 0 else messages
