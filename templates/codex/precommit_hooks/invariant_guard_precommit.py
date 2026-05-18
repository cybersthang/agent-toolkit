#!/usr/bin/env python
"""Pre-commit mirror of `.claude/hooks/invariant_guard.py`.

Runs over each staged file. If the staged diff (HEAD vs working tree)
strips a `must_keep_regex` pattern marked severity=blocker, the commit
is rejected.

Exits:
  0 — clean
  1 — at least one blocker violation

Bypass: `git commit --no-verify` (audit logged by git itself).

Stack-agnostic: reads `.agent-toolkit/invariants.json` from repo root.
"""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
INVARIANTS_PATH = REPO_ROOT / ".agent-toolkit" / "invariants.json"


def _load_invariants() -> List[dict]:
    if not INVARIANTS_PATH.exists():
        return []
    try:
        # utf-8-sig tolerates BOM produced by PowerShell Out-File -Encoding utf8.
        data = json.loads(INVARIANTS_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[invariant-guard-precommit] WARNING: failed to parse "
              f"{INVARIANTS_PATH}: {e}", file=sys.stderr)
        return []
    return [inv for inv in (data.get("invariants") or []) if isinstance(inv, dict)]


def _matches_path(file_path: str, globs: Iterable[str]) -> bool:
    globs = list(globs or [])
    if not globs:
        return True
    rel = file_path.replace("\\", "/")
    for pattern in globs:
        if fnmatch.fnmatch(rel, pattern.replace("\\", "/")):
            return True
    return False


def _staged_diff(file_path: str) -> Tuple[str, str]:
    """Return (old_content, new_content) for a staged file. Old is HEAD;
    new is the staged version (which becomes the next commit)."""
    try:
        old = subprocess.run(
            ["git", "show", f"HEAD:{file_path}"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        old_content = old.stdout if old.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        old_content = ""
    try:
        new = subprocess.run(
            ["git", "show", f":{file_path}"],  # `:path` is the staged version
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        new_content = new.stdout if new.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        new_content = ""
    return old_content, new_content


def _compile_patterns(rules: dict) -> List[Tuple[str, re.Pattern]]:
    out: List[Tuple[str, re.Pattern]] = []
    for raw in rules.get("must_keep_regex") or []:
        try:
            out.append((raw, re.compile(raw, re.IGNORECASE | re.MULTILINE)))
        except re.error:
            continue
    for name in rules.get("must_keep_call") or []:
        if not isinstance(name, str) or not name.strip():
            continue
        pattern = r"(?:\b|\.)" + re.escape(name.strip()) + r"\s*\("
        try:
            out.append((f"call:{name}", re.compile(pattern, re.MULTILINE)))
        except re.error:
            continue
    return out


def _check_file(file_path: str, invariants: List[dict]) -> List[str]:
    violations: List[str] = []
    old, new = _staged_diff(file_path)
    if not old and not new:
        return violations
    for inv in invariants:
        if (inv.get("severity") or "warn").lower() != "blocker":
            continue
        if not _matches_path(file_path, inv.get("applies_to") or []):
            continue
        patterns = _compile_patterns(inv.get("rules") or {})
        for label, regex in patterns:
            had = bool(regex.search(old))
            still = bool(regex.search(new))
            if had and not still:
                violations.append(
                    f"  - {inv.get('id', '?')}: pattern `{label}` removed from "
                    f"{file_path} (rationale: {inv.get('rationale', '')[:120]})"
                )
    return violations


def main(argv: List[str]) -> int:
    files = argv[1:]
    if not files:
        return 0
    invariants = _load_invariants()
    if not invariants:
        return 0
    all_violations: List[str] = []
    for fp in files:
        v = _check_file(fp, invariants)
        if v:
            all_violations.extend(v)
    if not all_violations:
        return 0
    print("[invariant-guard-precommit] BLOCKER invariant violations:", file=sys.stderr)
    for v in all_violations:
        print(v, file=sys.stderr)
    print("\nBypass single commit: `git commit --no-verify`", file=sys.stderr)
    print("Update invariant: /inv-add or /adr-add in Claude Code first.\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
