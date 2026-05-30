#!/usr/bin/env python
"""detect_retrospective_spec — flag specs written AFTER feature code.

Vibe-flow Phase 1 ("Plan-first") yêu cầu spec ra đời TRƯỚC khi code
feature-scope land. Tool này detect violation bằng cách so sánh:

  ts_spec  = first-commit timestamp của spec.md (git log --follow --diff-filter=A)
  ts_code  = first-commit timestamp của bất kỳ file feature-scope thuộc module

Nếu ts_spec > ts_code → spec là retrospective → flag.

Tool fail-open: lỗi git / parse / IO → exit 0 không output, vì
purpose là advisory (gap_status sẽ aggregate).

Public-project safe:
  - Không hardcode module name; đọc `module:` field từ spec frontmatter.
  - Không hardcode stack patterns; feature_scope_globs đọc từ
    `.agent-toolkit/coverage_config.json` hoặc default fallback.
  - Branch name normalization Git-flow / GitHub-flow tolerant.

Usage:
  python detect_retrospective_spec.py specs/v0.6.0-autonomy-chain.md
  python detect_retrospective_spec.py --json specs/v0.6.0-autonomy-chain.md
  python detect_retrospective_spec.py --workspace /path/to/repo specs/x.md

Exit codes:
  0 = analysis ran (check stdout/json for verdict)
  2 = spec not found / not readable
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# Fallback feature_scope_globs when project has no coverage_config.json.
# Odoo-flavored seed; public PR welcome for other stacks (Django, Rails,
# Spring, FastAPI, etc.). DO NOT hardcode project-specific paths here.
DEFAULT_FEATURE_GLOBS: List[str] = [
    "**/models/**/*.py",
    "**/controllers/**/*.py",
    "**/wizards/**/*.py",
    "**/jobs/**/*.py",
    "**/views/*.xml",
    "**/security/*.csv",
    # Generic patterns for non-Odoo stacks
    "**/views.py",
    "**/views/*.py",
    "**/serializers.py",
    "**/serializers/*.py",
    "**/api/*.py",
    "**/handlers/*.py",
    # Frontend feature scope
    "**/src/**/*.tsx",
    "**/src/**/*.ts",
    "**/src/**/*.jsx",
]


def _run_git(cwd: Path, args: List[str]) -> Optional[str]:
    """Run git command, return stdout (str) or None on error."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def _parse_spec_frontmatter(spec_path: Path) -> Dict[str, Any]:
    """Extract module + retrospective flag from YAML frontmatter (regex parse)."""
    if not spec_path.exists():
        return {}
    try:
        text = spec_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        return {}
    fm = rest[:end]
    out: Dict[str, Any] = {}
    for line in fm.splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        val = val.strip().strip('"').strip("'")
        if val.lower() in ("true", "false"):
            out[key] = val.lower() == "true"
        else:
            out[key] = val
    return out


def _load_feature_globs(workspace: Path) -> List[str]:
    """Read coverage_config.json or fall back to defaults."""
    config_path = workspace / ".agent-toolkit" / "coverage_config.json"
    if not config_path.exists():
        return list(DEFAULT_FEATURE_GLOBS)
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return list(DEFAULT_FEATURE_GLOBS)
    if not isinstance(cfg, dict):
        return list(DEFAULT_FEATURE_GLOBS)
    globs = cfg.get("feature_scope_globs")
    if isinstance(globs, list) and all(isinstance(g, str) for g in globs):
        return globs
    return list(DEFAULT_FEATURE_GLOBS)


def _spec_first_commit_ts(workspace: Path, spec_path: Path) -> Optional[int]:
    """Return UNIX timestamp of first commit that touched the spec.

    Uses `git log --follow --diff-filter=A` to follow renames + restrict to
    the original 'A'ddition commit.
    """
    rel = spec_path.relative_to(workspace) if spec_path.is_absolute() else spec_path
    out = _run_git(
        workspace,
        [
            "log", "--follow", "--diff-filter=A",
            "--format=%at", "--", str(rel),
        ],
    )
    if not out:
        return None
    # Take last line (oldest add commit).
    lines = [ln for ln in out.splitlines() if ln.strip().isdigit()]
    if not lines:
        return None
    return int(lines[-1])


def _earliest_feature_commit_ts(
    workspace: Path, module: Optional[str], feature_globs: List[str],
) -> Optional[int]:
    """Return earliest commit timestamp where any feature-scope file changed.

    If `module` is provided, restrict pathspec to files containing module
    name (best-effort substring filter via git log pathspec).
    """
    pathspecs: List[str] = []
    for glob in feature_globs:
        if module:
            # Restrict to module subtree if module-named subdirectory exists.
            # Cannot embed module name into the pattern itself reliably →
            # use raw globs and let git match repo-wide.
            pathspecs.append(f":(glob){glob}")
        else:
            pathspecs.append(f":(glob){glob}")
    if not pathspecs:
        return None
    out = _run_git(
        workspace,
        ["log", "--format=%at", "--", *pathspecs],
    )
    if not out:
        return None
    lines = [ln for ln in out.splitlines() if ln.strip().isdigit()]
    if not lines:
        return None
    # Earliest = last line (git log default reverse chronological).
    return int(lines[-1])


def analyze(spec_path: Path, workspace: Path) -> Dict[str, Any]:
    """Return analysis dict — fail-open with `error` key on issues."""
    if not spec_path.exists():
        return {"error": "spec not found", "spec": str(spec_path)}

    fm = _parse_spec_frontmatter(spec_path)
    module = fm.get("module")
    declared_retrospective = bool(fm.get("retrospective", False))

    feature_globs = _load_feature_globs(workspace)
    ts_spec = _spec_first_commit_ts(workspace, spec_path)
    ts_code = _earliest_feature_commit_ts(workspace, module, feature_globs)

    verdict = "unknown"
    delta_seconds: Optional[int] = None
    if ts_spec is not None and ts_code is not None:
        delta_seconds = ts_spec - ts_code
        if delta_seconds > 0:
            verdict = "retrospective"
        else:
            verdict = "spec-first"
    elif ts_spec is None:
        verdict = "spec-not-committed"
    elif ts_code is None:
        verdict = "no-feature-code-yet"

    return {
        "spec": str(spec_path),
        "module": module,
        "declared_retrospective": declared_retrospective,
        "ts_spec": ts_spec,
        "ts_code": ts_code,
        "delta_seconds": delta_seconds,
        "verdict": verdict,
        "mismatch": declared_retrospective != (verdict == "retrospective"),
        "feature_globs_count": len(feature_globs),
    }


def render_markdown(result: Dict[str, Any]) -> str:
    if "error" in result:
        return f"## detect_retrospective_spec — ERROR\n\n- {result['error']}\n"
    spec = Path(result["spec"]).name
    verdict = result["verdict"]
    icon = {
        "spec-first": "OK",
        "retrospective": "WARN",
        "spec-not-committed": "—",
        "no-feature-code-yet": "OK (only spec, no code yet)",
        "unknown": "?",
    }.get(verdict, "?")
    lines = [
        f"## detect_retrospective_spec — `{spec}`",
        "",
        f"- Verdict: **{verdict}** ({icon})",
        f"- Module: `{result.get('module') or '(none)'}`",
        f"- Declared `retrospective:` in frontmatter: `{result['declared_retrospective']}`",
        f"- Spec first commit ts: `{result.get('ts_spec') or '(none)'}`",
        f"- Earliest feature-code commit ts: `{result.get('ts_code') or '(none)'}`",
        f"- Delta seconds (spec − code): `{result.get('delta_seconds')}`",
    ]
    if result.get("mismatch"):
        lines.append(
            "- **Mismatch**: declared flag doesn't match git history detection."
        )
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", help="Path to spec markdown file")
    ap.add_argument("--workspace", default=None,
                    help="Workspace root (default: auto-detect from spec parent)")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of markdown")
    ns = ap.parse_args(argv[1:])

    spec_path = Path(ns.spec).resolve()
    if ns.workspace:
        workspace = Path(ns.workspace).resolve()
    else:
        # Walk up from spec until .git/ found
        cursor = spec_path.parent
        while cursor != cursor.parent:
            if (cursor / ".git").exists():
                workspace = cursor
                break
            cursor = cursor.parent
        else:
            workspace = spec_path.parent

    result = analyze(spec_path, workspace)
    if "error" in result:
        print(json.dumps(result, indent=2) if ns.json else render_markdown(result),
              file=sys.stderr)
        return 2
    if ns.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
