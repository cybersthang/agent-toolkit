#!/usr/bin/env python
"""PreToolUse hook — Vibe-flow Phase 1 spec-first guard (warn-only).

Trigger: Edit / Write / MultiEdit / NotebookEdit on a feature-scope file
when the current git branch is NOT trunk (main/master/trunk) AND there
is NO spec at `.agent-toolkit/specs/**/<branch-slug>.md` with non-empty
`acceptance_evals:` frontmatter.

Behaviour:
  - **Warn-only** (does NOT block) — emits stderr line `[spec-first-guard]
    warn: ...`. Toolkit's contract is "nudge, don't gate".
  - Skips trunk branches (main/master/trunk) — trunk-based dev exempt.
  - Skips test files (tests/**, test_*.py, *_test.py, *.test.js, etc.).
  - Skips files outside feature_scope_globs (config-driven).
  - Bypass single-shot: `spec-first-guard: skip <reason>` in any envelope
    string field → silent skip (logged for gap_status aggregation).
  - Fail-open: any exception → exit 0 silent.

Config: `<workspace>/.agent-toolkit/coverage_config.json` with
`feature_scope_globs: [...]` (optional). Fallback to default seed.

Public-project safe:
  - No hardcoded module names; no project-specific paths.
  - Default globs are generic seeds for popular stacks (Odoo, Django,
    Rails, FastAPI, React/TS). Override per project via config.

State log: appends an event to
`<workspace>/.agent-toolkit/.spec_first_guard_log.json` (ring buffer
last 50 events). gap_status can show counts.

See `templates/agent_toolkit/decision-log.md` ADR-001 for rationale.
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
from _common import wrap_utf8_stdio, match_glob, run_main_safe  # noqa: E402

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/coverage_config.json"
LOG_REL = ".agent-toolkit/.spec_first_guard_log.json"
LOG_MAX_EVENTS = 50

DEFAULT_FEATURE_GLOBS: List[str] = [
    # Odoo / Django / generic Python — both flat and nested layouts.
    "**/models/*.py",
    "**/models/**/*.py",
    "**/controllers/*.py",
    "**/controllers/**/*.py",
    "**/wizards/*.py",
    "**/wizards/**/*.py",
    "**/jobs/*.py",
    "**/jobs/**/*.py",
    "**/views/*.xml",
    "**/views/**/*.xml",
    "**/security/*.csv",
    # Django / Flask / FastAPI specifics
    "**/views.py",
    "**/views/*.py",
    "**/serializers.py",
    "**/serializers/*.py",
    "**/api/*.py",
    "**/handlers/*.py",
    "**/routes/*.py",
    # Rails / Sinatra
    "**/app/controllers/*.rb",
    "**/app/controllers/**/*.rb",
    "**/app/models/*.rb",
    "**/app/models/**/*.rb",
    "**/app/services/*.rb",
    "**/app/services/**/*.rb",
    # Frontend
    "**/src/**/*.tsx",
    "**/src/**/*.ts",
    "**/src/**/*.jsx",
    "**/src/**/*.vue",
]

DEFAULT_TEST_GLOBS: List[str] = [
    "**/tests/**",
    "**/test/**",
    "**/spec/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/*.test.js",
    "**/*.test.ts",
    "**/*.test.tsx",
    "**/*.spec.js",
    "**/*.spec.ts",
    "**/__tests__/**",
]

TRUNK_BRANCHES = {"main", "master", "trunk", "develop"}

BYPASS_MARKER_RX = re.compile(r"spec-first-guard:\s*skip\b", re.IGNORECASE)


def _exit_silent() -> None:
    sys.exit(0)


def _emit_warn(msg: str) -> None:
    """Emit warn line to stderr (non-blocking)."""
    print(f"[spec-first-guard] warn: {msg}", file=sys.stderr)
    sys.exit(0)


def _resolve_branch(workspace: Path) -> str:
    """Return current git branch name; empty string if not a git repo.

    Order of attempts:
      1. `git rev-parse --abbrev-ref HEAD` — normal repos with commits.
         Returns "HEAD" + rc=128 on unborn branch (no commits yet).
      2. `git symbolic-ref --short HEAD` — works on unborn branches.
    """
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
            out = (proc.stdout or "").strip()
            if out and out != "HEAD":
                return out
        # Fallback: unborn branch / detached HEAD (rev-parse returns
        # "HEAD" with rc!=0). symbolic-ref reads .git/HEAD directly.
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
            return (proc2.stdout or "").strip()
        return ""
    except (subprocess.SubprocessError, OSError):
        return ""


def _branch_to_slug(branch: str) -> str:
    """Normalize branch name → spec-stem slug.

    Git-flow: `feature/foo-bar` → `foo-bar` (strip prefix).
    GitHub-flow: `username/feature` → `feature` (last segment after /).
    Plain: `my-feature` → `my-feature`.
    """
    if "/" in branch:
        return branch.rsplit("/", 1)[1]
    return branch


def _load_globs(workspace: Path) -> Dict[str, List[str]]:
    """Load feature_scope_globs + test_globs from config, with defaults."""
    config_path = workspace / CONFIG_REL
    feature = list(DEFAULT_FEATURE_GLOBS)
    test = list(DEFAULT_TEST_GLOBS)
    if not config_path.exists():
        return {"feature": feature, "test": test}
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"feature": feature, "test": test}
    if not isinstance(cfg, dict):
        return {"feature": feature, "test": test}
    fg = cfg.get("feature_scope_globs")
    if isinstance(fg, list) and all(isinstance(g, str) for g in fg):
        feature = fg
    tg = cfg.get("test_globs")
    if isinstance(tg, list) and all(isinstance(g, str) for g in tg):
        test = tg
    return {"feature": feature, "test": test}


def _spec_for_branch_exists(workspace: Path, branch_slug: str) -> bool:
    """True if `.agent-toolkit/specs/**/<slug>.md` exists with non-empty
    acceptance_evals."""
    specs_dir = workspace / ".agent-toolkit" / "specs"
    if not specs_dir.is_dir():
        return False
    # Candidate paths: <slug>.md anywhere under specs/
    candidates = list(specs_dir.rglob(f"{branch_slug}.md"))
    # Also any spec with frontmatter `branch: <branch_slug>`
    if not candidates:
        for path in specs_dir.rglob("*.md"):
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:2000]
            except OSError:
                continue
            if re.search(rf"^\s*branch:\s*['\"]?{re.escape(branch_slug)}['\"]?\s*$",
                         head, re.MULTILINE):
                candidates.append(path)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        rest = text[3:]
        end = rest.find("\n---")
        if end < 0:
            continue
        fm = rest[:end]
        # Crude detect: has `acceptance_evals:` followed by non-empty list
        m = re.search(r"^\s*acceptance_evals\s*:\s*\n((?:\s+- .+\n?)+)", fm, re.MULTILINE)
        if m and m.group(1).strip():
            return True
    return False


def _has_bypass_marker(envelope: Dict[str, Any]) -> bool:
    """Walk envelope nested values; return True if any string contains
    bypass marker."""
    stack: List[Any] = [envelope]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            if BYPASS_MARKER_RX.search(cur):
                return True
        elif isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


def _log_event(workspace: Path, event: Dict[str, Any]) -> None:
    """Append event to ring buffer log; silent on error."""
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


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_silent()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_silent()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_silent()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    # Bypass marker
    if _has_bypass_marker(envelope):
        _log_event(workspace, {
            "ts": int(time.time()), "kind": "bypass",
            "tool_name": envelope.get("tool_name"),
        })
        _exit_silent()

    tool_input = envelope.get("tool_input") or {}
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or ""
    )
    if not file_path:
        _exit_silent()

    branch = _resolve_branch(workspace)
    if not branch or branch in TRUNK_BRANCHES:
        _exit_silent()

    globs = _load_globs(workspace)

    # Skip if file is a test file
    if match_glob(file_path, globs["test"], workspace, empty_returns=False):
        _exit_silent()

    # Skip if file is OUTSIDE feature_scope_globs (don't warn on, e.g.,
    # docs / config edits)
    if not match_glob(file_path, globs["feature"], workspace, empty_returns=False):
        _exit_silent()

    branch_slug = _branch_to_slug(branch)
    if _spec_for_branch_exists(workspace, branch_slug):
        _exit_silent()

    # Warn: feature-edit on non-trunk branch without spec.
    rel = file_path
    try:
        rel = str(Path(file_path).resolve().relative_to(workspace))
    except (ValueError, OSError):
        pass
    msg = (
        f"branch=`{branch}` slug=`{branch_slug}` edit=`{rel}` — no spec at "
        f"`.agent-toolkit/specs/**/{branch_slug}.md` with `acceptance_evals:`. "
        f"Run `/plan` first OR add `spec-first-guard: skip <reason>` token to bypass."
    )
    _log_event(workspace, {
        "ts": int(time.time()), "kind": "warn",
        "branch": branch, "branch_slug": branch_slug,
        "file": rel, "tool_name": envelope.get("tool_name"),
    })
    _emit_warn(msg)
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
