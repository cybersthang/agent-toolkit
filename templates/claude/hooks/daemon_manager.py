#!/usr/bin/env python
"""PostToolUse Edit hook — auto kill+restart project test daemon.

Replaces the manual "DEV bảo kill rồi chạy lại" loop. When DEV edits a
feature-scope source file and the project has a `process_manager`
defined in `.agent-toolkit/test_env.json` (schema v2), this hook:

  1. Reads the PID from `pid_track_file`.
  2. Kills it via `shutdown_signal`.
  3. Re-spawns via `start_cmd` (background, detached).
  4. Waits for `health_check_url` to respond (up to `health_timeout_s`).
  5. Writes new PID back to `pid_track_file`.

Skips when edit is in tests/, .agent-toolkit/, .codex/, .claude/ —
those don't require daemon restart.

Coverage detection respects `.agent-toolkit/coverage_config.json`
feature_globs; only restarts when edit matches feature scope.

Fails open: never blocks Edit. All errors logged + skipped.
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import run_main_safe


if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_DEFAULT_SKIP_GLOBS = [
    "**/tests/**", "**/test_*.py",
    ".agent-toolkit/**", ".codex/**", ".claude/**",
    "**/__pycache__/**", "**/migrations/**",
    "**/*.md", "**/*.json", "**/*.yaml", "**/*.yml"
]


def _matches_any_glob(path: str, globs: List[str]) -> bool:
    rel = path.replace("\\", "/")
    for g in globs or []:
        if fnmatch.fnmatch(rel, g.replace("\\", "/")):
            return True
    return False


def _load_test_env(workspace: Path) -> Optional[Dict[str, Any]]:
    p = workspace / ".agent-toolkit" / "test_env.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("schema_version") != 2:
        return None
    return data


def _load_feature_globs(workspace: Path) -> List[str]:
    p = workspace / ".agent-toolkit" / "coverage_config.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("feature_globs") or []


def _read_pid(pid_file: Path) -> Optional[int]:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in (result.stdout or "")
        except (subprocess.SubprocessError, OSError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _proc_cmdline(pid: int) -> str:
    """P6 v0.8.0: read process command-line for PID safety check.
    Returns empty string on failure (fail-safe = refuse kill)."""
    if platform.system() == "Windows":
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\""
                 ").CommandLine"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5,
            )
            return (proc.stdout or "").strip()
        except (subprocess.SubprocessError, OSError):
            return ""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\x00", b" ").decode(
                "utf-8", errors="replace").strip()
    except OSError:
        return ""


def _verify_pid_matches_start_cmd(pid: int, start_cmd: List[str]) -> bool:
    """P6 v0.8.0: confirm process at PID was launched by expected start_cmd.
    Compares first non-trivial token of start_cmd (binary name) with
    proc cmdline. Returns True if matches OR cmdline unavailable
    (lenient default to avoid breaking legitimate kills when proc info
    not readable). Set strict mode via env STRICT_DAEMON_PID_MATCH=1."""
    if not start_cmd:
        return True  # can't verify; allow
    expected = ""
    for tok in start_cmd:
        if tok and not tok.startswith("-") and tok != "--":
            expected = str(tok)
            break
    if not expected:
        return True
    cmdline = _proc_cmdline(pid)
    if not cmdline:
        # Strict mode: refuse if can't verify
        if os.environ.get("STRICT_DAEMON_PID_MATCH") == "1":
            return False
        return True
    expected_basename = Path(expected).name.lower()
    return expected_basename in cmdline.lower()


def _terminate(pid: int, signal_name: str,
               start_cmd: Optional[List[str]] = None) -> bool:
    if not _is_alive(pid):
        return True
    # P6 v0.8.0: PID safety check
    if start_cmd and not _verify_pid_matches_start_cmd(pid, start_cmd):
        print(
            f"[daemon-manager] PID {pid} cmdline does not match expected "
            f"start_cmd {start_cmd!r} — refusing kill (set "
            f"STRICT_DAEMON_PID_MATCH=0 to disable verification).",
            file=sys.stderr,
        )
        return False
    try:
        if signal_name == "Stop-Process" or platform.system() == "Windows":
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
                capture_output=True, timeout=10,
            )
        else:
            sig = 15 if signal_name == "SIGTERM" else 9
            os.kill(pid, sig)
        # Give it a moment.
        for _ in range(10):
            if not _is_alive(pid):
                return True
            time.sleep(0.5)
        # Force kill if still alive.
        if platform.system() != "Windows":
            try:
                os.kill(pid, 9)
            except OSError:
                pass
        return not _is_alive(pid)
    except OSError:
        return False


def _interpolate_cmd(cmd: List[str], placeholders: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for tok in cmd or []:
        s = str(tok)
        for k, v in placeholders.items():
            s = s.replace("{" + k + "}", str(v or ""))
        out.append(s)
    return out


def _spawn_daemon(cmd: List[str], env_passthrough: List[str]) -> Optional[int]:
    env = {k: os.environ[k] for k in (env_passthrough or ["PATH"])
           if k in os.environ}
    try:
        if platform.system() == "Windows":
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            proc = subprocess.Popen(
                cmd, env=env,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen(
                cmd, env=env, start_new_session=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return proc.pid
    except (OSError, ValueError):
        return None


def _wait_healthy(base_url: str, path: str, timeout_s: int) -> bool:
    if not base_url or not path:
        return True
    target = base_url.rstrip("/") + path
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            req = urllib.request.Request(target, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            pass
        time.sleep(1)
    return False


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0
    if os.environ.get("AGENT_TOOLKIT_DAEMON_MANAGER_DISABLE") == "1":
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    test_env = _load_test_env(workspace)
    if not test_env:
        return 0
    pm = test_env.get("process_manager") or {}
    if not pm or not pm.get("start_cmd"):
        return 0

    inp = envelope.get("tool_input") or {}
    file_path = inp.get("file_path") or inp.get("notebook_path")
    if not file_path:
        return 0
    edited = str(file_path).replace("\\", "/")

    if _matches_any_glob(edited, _DEFAULT_SKIP_GLOBS):
        return 0

    feature_globs = _load_feature_globs(workspace)
    if feature_globs and not _matches_any_glob(edited, feature_globs):
        return 0

    pid_file_rel = pm.get("pid_track_file") or ".agent-toolkit/.daemon_pid"
    pid_file = workspace / pid_file_rel
    pid = _read_pid(pid_file)

    placeholders: Dict[str, str] = {}
    config_path = workspace / ".agent-toolkit" / "agent_toolkit.config.json"
    # Env-key list is stack-aware: `test_env.json` may declare
    # `daemon_env_keys` (e.g. `["PYTHON_BIN","ODOO_CONF","DB"]` for Odoo,
    # `["PYTHON_BIN","DJANGO_SETTINGS_MODULE","DB"]` for Django).
    # Defaults stay stack-agnostic — just the universal ones.
    DEFAULT_KEYS = ("PYTHON_BIN", "DB")
    env_keys = test_env.get("daemon_env_keys") or DEFAULT_KEYS
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
            for k in env_keys:
                v = cfg.get(k) or cfg.get(k.lower())
                if v:
                    placeholders[k] = str(v)
        except (json.JSONDecodeError, OSError):
            pass
    placeholders.setdefault("DB", test_env.get("db") or "")

    cmd = _interpolate_cmd(pm.get("start_cmd") or [], placeholders)
    env_passthrough = pm.get("start_cmd_env_passthrough") or ["PATH"]
    shutdown_signal = pm.get("shutdown_signal") or "SIGTERM"

    # If daemon currently dead, only restart if test_env opted-in
    # (defaults to skip — DEV may not want auto-start when daemon was
    # manually stopped).
    if not pid or not _is_alive(pid):
        if not pm.get("auto_start_if_dead"):
            return 0

    if pid and _is_alive(pid):
        # P6 v0.8.0: pass start_cmd for PID-safety verification
        ok_kill = _terminate(pid, shutdown_signal, start_cmd=cmd)
        if not ok_kill:
            print(f"[daemon_manager] could not kill PID {pid} — skipping restart",
                  file=sys.stderr)
            return 0

    new_pid = _spawn_daemon(cmd, env_passthrough)
    if not new_pid:
        print(f"[daemon_manager] spawn failed: {cmd[:3]}...", file=sys.stderr)
        return 0

    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(new_pid), encoding="utf-8")
    except OSError:
        pass

    base_url = test_env.get("url") or ""
    health_path = pm.get("health_check_url") or ""
    health_timeout = int(pm.get("health_timeout_s", 60))
    healthy = _wait_healthy(base_url, health_path, health_timeout)

    print(f"[daemon_manager] restarted daemon PID={new_pid} "
          f"healthy={healthy} (was PID={pid}) after edit on {edited}")
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
