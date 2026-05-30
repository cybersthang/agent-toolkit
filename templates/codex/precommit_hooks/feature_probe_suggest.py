#!/usr/bin/env python
"""Pre-commit info hook — suggest probe registrations for newly added
endpoints / controller methods / model methods.

Non-blocking (always exits 0). Reads `git diff --cached` for staged
changes and surfaces:
  - New `@http.route(...)` definitions → suggest HTTP probe
  - New `def <name>(self, ...)` in `controllers/*.py` → suggest probe
  - New `@api.depends` / `@api.constrains` in models → suggest consistency probe
  - New `@api.model` cron methods → suggest idempotency probe

Output is purely informational — dev sees suggestions but commit proceeds.
The `probe_coverage.py` hook is the enforcement gate.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]


PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    ("HTTP route",
     re.compile(r"^\+\s*@http\.route\((['\"])([^'\"]+)\1"),
     "→ /probe-add <id> · falsification.runner.measurement_command = "
     "`curl -w \"%{{time_total}}\" <base>{route}` to verify behavior."),
    ("Controller method",
     re.compile(r"^\+\s*def\s+([a-z_][a-zA-Z0-9_]*)\s*\(self"),
     "→ /probe-add <id> · evidence.required_tools = "
     "[\"mcp__realdata_test__run_smoke_test\"]; method body should "
     "have a path_globs entry matching the file."),
    ("api.depends / api.constrains",
     re.compile(r"^\+\s*@api\.(depends|constrains)\("),
     "→ /probe-add <id> · evidence.required_tools = "
     "[\"mcp__realdata_test__consistency_check_eval\"]; assert "
     "deterministic output on identical input."),
    ("Cron method (@api.model + nextcall)",
     re.compile(r"^\+\s*nextcall\s*="),
     "→ /probe-add <id> · evidence.required_tools = "
     "[\"mcp__realdata_test__run_module_test\"]; verify idempotency "
     "by running 2× and comparing state."),
]


def _staged_diff() -> str:
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--unified=0"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        return proc.stdout if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main(_argv: List[str]) -> int:
    diff = _staged_diff()
    if not diff:
        return 0

    suggestions: List[str] = []
    current_file = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for label, pat, advice in PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            detail = ""
            try:
                if m.lastindex and m.lastindex >= 1:
                    detail = f" `{m.group(m.lastindex)}`"
            except IndexError:
                pass
            suggestions.append(
                f"  [{label}{detail}] in {current_file or '<unknown>'}\n"
                f"    {advice}"
            )

    if not suggestions:
        return 0

    # Dedup adjacent same-line suggestions
    seen: List[str] = []
    for s in suggestions:
        if s not in seen:
            seen.append(s)

    print("[probe-suggest] New endpoints/methods detected — consider /probe-add:",
          file=sys.stderr)
    for s in seen[:15]:
        print(s, file=sys.stderr)
    if len(seen) > 15:
        print(f"  ... +{len(seen) - 15} more.", file=sys.stderr)
    print(
        "\nThis is INFO-ONLY — commit proceeds. The probe-coverage hook "
        "may still block if a feature-scope file has no probe.\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
