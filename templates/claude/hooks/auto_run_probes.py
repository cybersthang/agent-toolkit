#!/usr/bin/env python
"""PostToolUse Edit hook — auto-run acceptance probes whose path_globs
match the file just edited.

Replaces the manual "DEV asks AGENT to run probes" loop with a
mechanical PostToolUse trigger. Whenever a probe entry has `auto_run:
true` and one of its `applies_when.path_globs` matches the edited
file path, this hook spawns `python .codex/tools/falsify.py --probe
<id>` and prints the verdict.

Config: `.agent-toolkit/auto_probes.json` (see _DEFAULT_CONFIG below).

Debounce: per-probe last-run timestamp in
`.agent-toolkit/.auto_probes_state.json`. Probes don't fire more often
than `debounce_s` (default 30s).

Fails open: any error is logged, hook exits 0 (never blocks Edit).

Wired in `.claude/settings.json` PostToolUse Edit/Write/MultiEdit.
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))
from _common import run_main_safe


if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_DEFAULT_CONFIG = {
    "enabled": True,
    "debounce_s": 30,
    "max_concurrent": 1,
    "skip_path_globs": [
        "**/tests/**", "**/test_*.py",
        ".agent-toolkit/**", ".codex/**", ".claude/**",
        "**/__pycache__/**", "**/migrations/**",
    ],
    "verdict_log": ".agent-toolkit/.auto_probes_state.json",
}


def _load_config(workspace: Path) -> Dict[str, Any]:
    path = workspace / ".agent-toolkit" / "auto_probes.json"
    config = dict(_DEFAULT_CONFIG)
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8-sig"))
            config.update(override)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def _load_probes(workspace: Path) -> List[Dict[str, Any]]:
    path = workspace / ".agent-toolkit" / "acceptance-probes.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    return [p for p in (data.get("probes") or []) if isinstance(p, dict)]


def _matches_any_glob(path: str, globs: List[str]) -> bool:
    rel = path.replace("\\", "/")
    for g in globs or []:
        if fnmatch.fnmatch(rel, g.replace("\\", "/")):
            return True
    return False


def _load_state(workspace: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    p = workspace / config["verdict_log"]
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(workspace: Path, config: Dict[str, Any],
                state: Dict[str, Any]) -> None:
    p = workspace / config["verdict_log"]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    except OSError:
        pass


def _run_probe(workspace: Path, probe_id: str, timeout_s: int = 90) -> Dict[str, Any]:
    falsify = workspace / ".codex" / "tools" / "falsify.py"
    if not falsify.exists():
        return {"status": "no-falsify", "id": probe_id}
    try:
        proc = subprocess.run(
            [sys.executable, str(falsify), "--probe", probe_id],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "id": probe_id}
    except OSError as e:
        return {"status": "error", "id": probe_id, "msg": str(e)}
    verdict = "proven" if proc.returncode == 0 else (
        "refuted" if proc.returncode == 1 else "error"
    )
    return {
        "status": verdict,
        "id": probe_id,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-300:],
        "stderr_tail": (proc.stderr or "")[-300:],
        "ts": time.time(),
    }


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
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

    config = _load_config(workspace)
    if not config.get("enabled"):
        return 0

    inp = envelope.get("tool_input") or {}
    file_path = inp.get("file_path") or inp.get("notebook_path")
    if not file_path:
        return 0
    edited = str(file_path).replace("\\", "/")

    skip_globs = config.get("skip_path_globs") or []
    if _matches_any_glob(edited, skip_globs):
        return 0

    probes = _load_probes(workspace)
    auto_run_probes = [p for p in probes if p.get("auto_run") is True]
    if not auto_run_probes:
        return 0

    matched: List[str] = []
    for p in auto_run_probes:
        path_globs = (p.get("applies_when") or {}).get("path_globs") or []
        if _matches_any_glob(edited, path_globs):
            pid = p.get("id")
            if pid:
                matched.append(pid)

    if not matched:
        return 0

    state = _load_state(workspace, config)
    debounce_s = int(config.get("debounce_s", 30))
    now = time.time()

    to_run = []
    for pid in matched:
        last = state.get(pid, {}).get("ts") or 0
        if (now - last) >= debounce_s:
            to_run.append(pid)

    if not to_run:
        return 0

    max_concurrent = int(config.get("max_concurrent", 1) or 1)
    # Simple sequential run for now; concurrent path future-proofs schema.
    results = []
    for pid in to_run[:max_concurrent]:
        result = _run_probe(workspace, pid)
        state[pid] = {
            "ts": now,
            "status": result.get("status"),
            "returncode": result.get("returncode"),
        }
        results.append(result)

    _save_state(workspace, config, state)

    # Surface verdict as systemMessage (visible to next agent turn).
    summary_lines = [
        f"[auto_run_probes] {len(results)} probe(s) fired after edit on {edited}:"
    ]
    for r in results:
        summary_lines.append(
            f"  - {r.get('id')}: {r.get('status')} "
            f"(rc={r.get('returncode')})"
        )
        tail = r.get("stdout_tail") or ""
        if tail.strip():
            summary_lines.append(f"    stdout: {tail.strip().splitlines()[-1][:200]}")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
