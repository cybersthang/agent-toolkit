#!/usr/bin/env python
# v0.23 R7 — probe-coverage Stop gate
"""Stop hook — probe-coverage gate (v0.23 R7).

When the assistant claims `done | merge | ship | ready` AND the
probe-coverage of feature-scope files in the current branch falls below
a threshold (default 60%), surface (WARN) or block the response. This
is the Stop-time counterpart of the pre-commit `probe_coverage.py`
gate: it catches the "claim done without registering a probe for every
feature file" anti-pattern before the response lands, not just at
commit time.

Coverage calc (mirrors the `/probe-coverage` command + the pre-commit
hook bucketing):
  - Feature-scope file = matches a `feature_globs` glob AND not an
    `exempt_globs` glob (from `.agent-toolkit/coverage_config.json`,
    falling back to DEFAULT_* globs).
  - Covered = a feature-scope file matched by ≥1 probe's
    `applies_when.path_globs` in `.agent-toolkit/acceptance-probes.json`.
  - coverage_pct = covered / total_feature_scope * 100.

File set = files changed in the current branch
(`git diff --name-only origin/main...HEAD`), falling back to staged
files (`git diff --cached --name-only`). When no VCS file set can be
resolved the gate skips silently (fail-open).

Config: `.agent-toolkit/probe_coverage.json` (fail-open if missing):
    {
      "min_coverage_pct": 60,        // block/warn when below this %
      "base_ref": "origin/main",     // branch-diff base
      "max_listed": 15               // cap uncovered files shown
    }

Default WARN (conservative rollout). `enforce_mode.json`
`per_hook.probe_coverage_gate: "block"` promotes it to BLOCK.

Skip cases (silent allow, exit 0):
  - `AGENT_TOOLKIT_DISABLE=1` kill-switch.
  - `stop_hook_active` recursion break.
  - Config file missing (feature opt-in — no config → skip silently).
  - No acceptance-probes.json registered yet (toolkit being adopted).
  - No feature-scope files in the change set.
  - Response does not claim done/merge/ship.
  - Coverage ≥ threshold.

Fails open on any unexpected error (run_main_safe wrapper).
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import run_main_safe, emit_fire_event, get_enforce_mode  # noqa: E402
from _patterns import COMPLETION_RE  # noqa: E402
from _audit.transcript import (  # noqa: E402
    read_transcript, split_current_turn, extract_text_and_tools,
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


PROBES_REL = ".agent-toolkit/acceptance-probes.json"
COVERAGE_CONFIG_REL = ".agent-toolkit/coverage_config.json"
CONFIG_REL = ".agent-toolkit/probe_coverage.json"
HOOK_NAME = "probe_coverage_gate"

DEFAULT_MIN_COVERAGE_PCT = 60.0
DEFAULT_BASE_REF = "origin/main"
DEFAULT_MAX_LISTED = 15

# Mirror .codex/precommit_hooks/probe_coverage.py defaults so Stop-time
# and commit-time bucketing agree.
DEFAULT_FEATURE_GLOBS = [
    "*/addons/**/controllers/**.py",
    "*/addons/**/models/**.py",
    "*/addons/**/wizard/**.py",
    "*/addons/**/wizards/**.py",
    "*/addons/**/jobs/**.py",
    "**/controllers/**.py",
    "**/models/**.py",
    "**/api/**.py",
    "**/services/**.py",
    "**/views.py",
    "**/handlers/**.py",
]
DEFAULT_EXEMPT_GLOBS = [
    "**/__init__.py",
    "**/tests/**.py",
    "**/test_*.py",
    "**/*_test.py",
    "**/migrations/**.py",
    "**/conftest.py",
    "OCA/**",
    ".codex/**",
    ".claude/**",
    ".agent-toolkit/**",
]


def _exit_allow(detail: Optional[str] = None) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="allow", detail=detail)
    except Exception:
        pass
    return 0


def _exit_warn(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=reason[:200])
    except Exception:
        pass
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": reason,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.stderr.write(f"[probe-coverage-gate] warn: {reason}\n")
    return 0


def _exit_block(reason: str) -> int:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="block", detail=reason[:200])
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.stderr.write(f"[probe-coverage-gate] block: {reason}\n")
    return 2


def _find_workspace(cwd: Optional[str]) -> Path:
    if cwd:
        return Path(cwd).resolve()
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_config(workspace: Path) -> Optional[Dict[str, Any]]:
    """Return parsed config, or None when feature not opted in (missing)."""
    data = _read_json(workspace / CONFIG_REL)
    if not isinstance(data, dict):
        return None
    cfg = {
        "min_coverage_pct": DEFAULT_MIN_COVERAGE_PCT,
        "base_ref": DEFAULT_BASE_REF,
        "max_listed": DEFAULT_MAX_LISTED,
    }
    try:
        if "min_coverage_pct" in data:
            cfg["min_coverage_pct"] = float(data["min_coverage_pct"])
        if "base_ref" in data and isinstance(data["base_ref"], str):
            cfg["base_ref"] = data["base_ref"]
        if "max_listed" in data:
            cfg["max_listed"] = int(data["max_listed"])
    except (TypeError, ValueError):
        pass
    return cfg


def _load_coverage_globs(workspace: Path) -> Tuple[List[str], List[str]]:
    data = _read_json(workspace / COVERAGE_CONFIG_REL)
    feature_globs = DEFAULT_FEATURE_GLOBS
    exempt_globs = DEFAULT_EXEMPT_GLOBS
    if isinstance(data, dict):
        fg = data.get("feature_globs")
        eg = data.get("exempt_globs")
        if isinstance(fg, list) and fg:
            feature_globs = [g for g in fg if isinstance(g, str)]
        if isinstance(eg, list) and eg:
            exempt_globs = [g for g in eg if isinstance(g, str)]
    return feature_globs, exempt_globs


def _load_probes(workspace: Path) -> List[Dict[str, Any]]:
    data = _read_json(workspace / PROBES_REL)
    if not isinstance(data, dict):
        return []
    return [p for p in (data.get("probes") or []) if isinstance(p, dict)]


def _matches_any(path: str, globs: List[str]) -> bool:
    norm = path.replace("\\", "/")
    for g in globs:
        if isinstance(g, str) and fnmatch.fnmatch(norm, g.replace("\\", "/")):
            return True
    return False


def _probe_covers(file_path: str, probes: List[Dict[str, Any]]) -> bool:
    for probe in probes:
        aw = probe.get("applies_when") or {}
        globs = aw.get("path_globs") or []
        if isinstance(globs, list) and _matches_any(file_path, globs):
            return True
    return False


def _git_files(workspace: Path, base_ref: str) -> List[str]:
    """Branch-diff files, fall back to staged. Empty list on any error."""
    def _run(args: List[str]) -> List[str]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(workspace)] + args,
                capture_output=True, text=True, encoding="utf-8",
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0:
            return []
        return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]

    files = _run(["diff", "--name-only", f"{base_ref}...HEAD"])
    if files:
        return files
    return _run(["diff", "--cached", "--name-only"])


def _compute_coverage(files: List[str], feature_globs: List[str],
                      exempt_globs: List[str], probes: List[Dict[str, Any]]
                      ) -> Tuple[int, int, List[str]]:
    """Returns (covered, total_feature_scope, uncovered_paths)."""
    covered = 0
    total = 0
    uncovered: List[str] = []
    for fp in files:
        if not _matches_any(fp, feature_globs):
            continue
        if _matches_any(fp, exempt_globs):
            continue
        total += 1
        if _probe_covers(fp, probes):
            covered += 1
        else:
            uncovered.append(fp)
    return covered, total, uncovered


def _response_text(envelope: Dict[str, Any], workspace: Path) -> str:
    transcript_path = envelope.get("transcript_path")
    if transcript_path:
        try:
            messages = read_transcript(Path(transcript_path))
            turn = split_current_turn(messages)
            text, _tools = extract_text_and_tools(turn)
            if text:
                return text
        except Exception:
            pass
    # Fallback: inline response field (some envelopes carry it directly).
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


def _main() -> int:
    if os.environ.get("stop_hook_active") == "true":
        return _exit_allow(detail="stop_hook_active")

    raw = sys.stdin.read()
    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        envelope = {}

    workspace = _find_workspace(envelope.get("cwd"))

    cfg = _load_config(workspace)
    if cfg is None:
        return _exit_allow(detail="no-config")

    probes = _load_probes(workspace)
    # No probes registered yet — toolkit being adopted; don't gate.
    if not probes:
        return _exit_allow(detail="no-probes")

    response_text = _response_text(envelope, workspace)
    # Only gate when the response actually claims done/merge/ship/ready.
    if not COMPLETION_RE.search(response_text):
        return _exit_allow(detail="no-done-claim")

    feature_globs, exempt_globs = _load_coverage_globs(workspace)
    files = _git_files(workspace, str(cfg["base_ref"]))
    if not files:
        return _exit_allow(detail="no-vcs-files")

    covered, total, uncovered = _compute_coverage(
        files, feature_globs, exempt_globs, probes
    )
    if total == 0:
        return _exit_allow(detail="no-feature-files")

    coverage_pct = (covered / total) * 100.0
    threshold = float(cfg["min_coverage_pct"])
    if coverage_pct >= threshold:
        return _exit_allow(
            detail=f"covered;{coverage_pct:.0f}%>={threshold:g}%"
        )

    # Below threshold — build reason.
    max_listed = int(cfg["max_listed"])
    lines = [
        f"Probe coverage {coverage_pct:.0f}% < {threshold:g}% required "
        f"({covered}/{total} feature-scope files have a probe).",
        "Files lacking a probe:",
    ]
    for fp in uncovered[:max_listed]:
        lines.append(f"  - {fp}")
    if len(uncovered) > max_listed:
        lines.append(f"  ... and {len(uncovered) - max_listed} more")
    lines.append("")
    lines.append(
        "Run /probe-add <id> for each file above, or /probe-coverage to "
        "see the full bucket table. Permanently exempt a path via "
        "`.agent-toolkit/coverage_config.json` exempt_globs."
    )
    reason = "\n".join(lines)

    mode = get_enforce_mode(workspace, HOOK_NAME, default="warn")
    if mode == "off":
        return _exit_allow(detail=f"off;{coverage_pct:.0f}%")
    if mode == "block":
        return _exit_block(reason)
    # Default: warn (conservative rollout).
    return _exit_warn(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(_main))
