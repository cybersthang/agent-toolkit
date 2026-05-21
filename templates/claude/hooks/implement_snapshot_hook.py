#!/usr/bin/env python
"""PreToolUse hook — trigger pre-implement snapshot on first feature-scope Edit.

For each (slug, file_rel) pair, snapshot the file ONCE per session so
Layer 5 verify_lint scope check has a baseline. After snapshot, this
hook becomes a no-op for that file (idempotent).

Logic:
  1. Resolve current branch → branch_slug.
  2. Look up spec at `.agent-toolkit/specs/**/<branch_slug>.md`. If
     missing or has no `affected_modules` field → skip (grandfather).
  3. Determine file_path from envelope tool_input.
  4. Skip if file_path is in test/skip glob list.
  5. Skip if file_path is OUTSIDE feature_scope_globs (no point
     snapshotting a config file the spec didn't claim).
  6. Skip if file already snapshotted in this slug's manifest.
  7. Call implement_snapshot.snapshot_create(slug, [file_path], workspace).

Fail-open: every error path → exit 0 silent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import wrap_utf8_stdio, match_glob, run_main_safe  # noqa: E402

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/coverage_config.json"
SNAPSHOT_REL = ".agent-toolkit/.implement_snapshots"
SCOPE_TOOL_REL = ".codex/tools/implement_snapshot.py"

TRUNK_BRANCHES = {"main", "master", "trunk", "develop"}

DEFAULT_FEATURE_GLOBS: List[str] = [
    "**/models/*.py", "**/models/**/*.py",
    "**/controllers/*.py", "**/controllers/**/*.py",
    "**/wizards/*.py", "**/wizards/**/*.py",
    "**/jobs/*.py", "**/jobs/**/*.py",
    "**/views/*.xml", "**/views/**/*.xml",
    "**/security/*.csv",
    "**/views.py", "**/views/*.py",
    "**/serializers.py", "**/serializers/*.py",
    "**/api/*.py", "**/handlers/*.py", "**/routes/*.py",
    "**/app/controllers/*.rb", "**/app/controllers/**/*.rb",
    "**/app/models/*.rb", "**/app/models/**/*.rb",
    "**/app/services/*.rb", "**/app/services/**/*.rb",
    "**/src/**/*.tsx", "**/src/**/*.ts",
    "**/src/**/*.jsx", "**/src/**/*.vue",
    # Toolkit's own dogfood layout
    "templates/**/*.py", "templates/**/*.json",
    "templates/**/*.md",
    "lib/*.py",
]

DEFAULT_TEST_GLOBS: List[str] = [
    "**/tests/**", "**/test/**", "**/spec/**",
    "**/test_*.py", "**/*_test.py",
    "**/*.test.js", "**/*.test.ts", "**/*.test.tsx",
    "**/*.spec.js", "**/*.spec.ts",
    "**/__tests__/**",
]


def _exit_silent() -> None:
    sys.exit(0)


def _resolve_branch(workspace: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out and out != "HEAD":
                return out
        proc2 = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
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


def _spec_path_for_slug(workspace: Path, slug: str) -> Optional[Path]:
    sd = workspace / ".agent-toolkit" / "specs"
    if not sd.is_dir():
        return None
    for p in sd.rglob(f"{slug}.md"):
        if p.stem == slug:
            return p
    return None


def _spec_has_affected_modules(spec_path: Path) -> bool:
    """Crude regex scan — true if frontmatter declares affected_modules
    with non-empty list."""
    try:
        text = spec_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        return False
    fm = rest[:end]
    # Look for `affected_modules:` followed by a list with at least 1 item.
    import re
    m = re.search(r"^\s*affected_modules\s*:\s*\n((?:\s+- .+\n?)+)",
                  fm, re.MULTILINE)
    return bool(m and m.group(1).strip())


def _load_globs(workspace: Path) -> Dict[str, List[str]]:
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


def _already_snapshotted(workspace: Path, slug: str, rel_path: str) -> bool:
    manifest_path = (workspace / SNAPSHOT_REL / slug / "_manifest.json")
    if not manifest_path.exists():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = data.get("files") or {}
        return rel_path.replace("\\", "/") in files
    except (json.JSONDecodeError, OSError):
        return False


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

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    branch = _resolve_branch(workspace)
    if not branch or branch in TRUNK_BRANCHES:
        _exit_silent()
    slug = _branch_to_slug(branch)

    spec_path = _spec_path_for_slug(workspace, slug)
    if not spec_path:
        _exit_silent()
    if not _spec_has_affected_modules(spec_path):
        # P2 v0.8.0: grandfather → warn (not silent) so DEV knows
        # Layer 5 scope check won't engage for this spec.
        try:
            rel = str(spec_path.relative_to(workspace))
        except (ValueError, OSError):
            rel = str(spec_path)
        print(
            f"[snapshot-hook] grandfather: spec '{slug}' at {rel} missing "
            f"`affected_modules` frontmatter — Layer 5 scope check will not "
            f"engage. Add `affected_modules: [...]` to enable, or use "
            f"`migrate_specs_affected_modules.py --apply`.",
            file=sys.stderr,
        )
        _exit_silent()

    tool_input = envelope.get("tool_input") or {}
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or ""
    )
    if not file_path:
        _exit_silent()

    globs = _load_globs(workspace)
    if match_glob(file_path, globs["test"], workspace, empty_returns=False):
        _exit_silent()
    if not match_glob(file_path, globs["feature"], workspace, empty_returns=False):
        _exit_silent()

    try:
        rel = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        _exit_silent()

    if _already_snapshotted(workspace, slug, rel):
        _exit_silent()

    # Call snapshot tool via library import (cheaper than subprocess).
    snapshot_tool = workspace / SCOPE_TOOL_REL
    if not snapshot_tool.exists():
        _exit_silent()
    sys.path.insert(0, str(snapshot_tool.parent))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_snap", str(snapshot_tool))
        if spec is None or spec.loader is None:
            _exit_silent()
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.snapshot_create(slug, [rel], workspace)
    except Exception:
        pass
    _exit_silent()
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
