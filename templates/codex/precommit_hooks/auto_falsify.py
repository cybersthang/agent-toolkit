#!/usr/bin/env python
"""Pre-commit auto-falsify gate.

For each staged file, find matching non-stub probes in
`.agent-toolkit/acceptance-probes.json` and run their falsifier recipe
via `.codex/tools/falsify.py`. If any probe verdict is REFUTED, block
the commit with the verbatim falsifier output.

Skips:
  - Probes with `_stub: true` (DEV hasn't filled TODO fields yet).
  - Probes whose `falsification.runner` is missing measurement_command.
  - Probes whose runner sandbox-rejects (security feature, not a bug).

Honors AGENT_TOOLKIT_DISABLE env var. Fail-open on parse errors.

This is the missing link between "DEV plans/grills/goes" and "auto-
verified at commit time" — no manual `python falsify.py --probe X`
needed.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES_PATH = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"
FALSIFY_CLI = REPO_ROOT / ".codex" / "tools" / "falsify.py"


def _load_probes() -> List[dict]:
    if not PROBES_PATH.exists():
        return []
    try:
        data = json.loads(PROBES_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return [p for p in (data.get("probes") or []) if isinstance(p, dict)]


def _matches_any(path: str, globs: List[str]) -> bool:
    rel = path.replace("\\", "/")
    for g in globs or []:
        if fnmatch.fnmatch(rel, g.replace("\\", "/")):
            return True
    return False


def main(argv: List[str]) -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0

    files = argv[1:]
    if not files:
        return 0
    if not FALSIFY_CLI.exists():
        return 0

    probes = _load_probes()
    if not probes:
        return 0

    # Identify probes whose path_globs match any staged file.
    matched_ids: List[str] = []
    for probe in probes:
        if probe.get("_stub"):
            continue
        runner = (probe.get("falsification") or {}).get("runner") or {}
        # Skip if no runnable command (stub or incomplete)
        if not runner.get("measurement_command"):
            continue
        # measurement_command containing "TODO" placeholder is a stub-in-disguise
        if "TODO" in (runner.get("measurement_command") or "").upper():
            continue
        path_globs = (probe.get("applies_when") or {}).get("path_globs") or []
        for fp in files:
            if _matches_any(fp, path_globs):
                matched_ids.append(probe.get("id", ""))
                break

    if not matched_ids:
        return 0

    # Run falsify for each.
    refuted: List[str] = []
    errors: List[str] = []
    py = os.environ.get("{{ENV_PREFIX}}_PYTHON_BIN") or sys.executable

    print(f"[auto-falsify] {len(matched_ids)} probe(s) match staged paths; "
          f"running falsifier...", file=sys.stderr)

    for pid in matched_ids:
        try:
            proc = subprocess.run(
                [py, str(FALSIFY_CLI), "--probe", pid],
                capture_output=True, text=True, timeout=120,
                cwd=str(REPO_ROOT),
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            errors.append(f"{pid}: {e}")
            continue
        if proc.returncode == 0:
            print(f"[auto-falsify] PROVEN: {pid}", file=sys.stderr)
        elif proc.returncode == 1:
            refuted.append(f"{pid}\n{proc.stdout}\n{proc.stderr}")
        else:
            # rc=2 = sandbox-reject / missing config / live service unreachable
            errors.append(
                f"{pid} (rc={proc.returncode}): "
                f"{(proc.stderr or proc.stdout or '<no output>')[:300]}"
            )

    if not refuted and not errors:
        print(f"[auto-falsify] All {len(matched_ids)} probe(s) PROVEN.",
              file=sys.stderr)
        return 0

    if refuted:
        print(f"\n[auto-falsify] {len(refuted)} probe(s) REFUTED:",
              file=sys.stderr)
        for r in refuted:
            print(r, file=sys.stderr)
            print("---", file=sys.stderr)

    if errors:
        print(f"\n[auto-falsify] {len(errors)} probe(s) ERRORED "
              f"(infrastructure issue, NOT refutation):", file=sys.stderr)
        for e in errors[:5]:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nERROR means probe didn't run successfully (service down, "
            "sandbox reject, missing config) — review and either fix the "
            "probe config or run `git commit --no-verify` if it's a "
            "transient issue. ERRORs do NOT block commit by default; only "
            "REFUTED claims block.\n",
            file=sys.stderr,
        )

    if refuted:
        print(
            "\nBypass single commit: `git commit --no-verify`\n"
            "Fix the falsification mismatch (or update the probe's "
            "expected behavior if intentional change).\n",
            file=sys.stderr,
        )
        return 1
    # Only errors, no refutations → don't block (errors are infra issues)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
