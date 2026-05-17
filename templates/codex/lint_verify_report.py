#!/usr/bin/env python
"""Lint a /verify Report against spec.acceptance_evals (enforces ADR-007 Bước 1.5).

Purpose
-------
After agent runs /verify and emits a Verify Report (markdown), this script
verifies that every entry in the spec's `acceptance_evals:` frontmatter block
was referenced in the report. If any eval id is missing → exit non-zero, list
the missing ids. Stop hook + agent can then re-emit with full coverage.

Usage
-----
    # Pipe report stdin → lint
    cat verify_report.md | python lint_verify_report.py <spec-slug>

    # Or pass a file
    python lint_verify_report.py <spec-slug> --report path/to/report.md

Exit codes
----------
0 = report covers all acceptance_evals
1 = missing eval(s) from report
2 = spec not found / not readable
3 = no acceptance_evals in spec (lint not applicable)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


def _find_workspace_root(start: Path) -> Path:
    """Walk up looking for .agent-toolkit/specs/ dir (M2 fix: walk to FS root)."""
    cursor = start.resolve()
    while True:
        if (cursor / ".agent-toolkit" / "specs").is_dir():
            return cursor
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    # Fallback: cwd
    return Path.cwd()


def _load_spec_evals(spec_slug: str, workspace: Path) -> list[dict]:
    """Return list of acceptance_evals entries from spec frontmatter.

    Returns [] if spec has no acceptance_evals block.
    """
    spec_path = workspace / ".agent-toolkit" / "specs" / f"{spec_slug}.md"
    if not spec_path.exists():
        print(f"error: spec not found: {spec_path}", file=sys.stderr)
        sys.exit(2)
    text = spec_path.read_text(encoding="utf-8")
    # Extract YAML frontmatter (between first --- and second ---).
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        print(f"error: spec has no YAML frontmatter: {spec_path}", file=sys.stderr)
        sys.exit(2)
    fm_text = m.group(1)
    if yaml is None:
        # Fallback: crude regex parse of `- id: <slug>` lines under acceptance_evals.
        if "acceptance_evals:" not in fm_text:
            return []
        after = fm_text.split("acceptance_evals:", 1)[1]
        ids = re.findall(r"^\s*-\s*id:\s*([^\s]+)\s*$", after, re.MULTILINE)
        return [{"id": i} for i in ids]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        print(f"error: spec frontmatter not valid YAML: {exc}", file=sys.stderr)
        sys.exit(2)
    evals = fm.get("acceptance_evals") or []
    return [e for e in evals if isinstance(e, dict) and e.get("id")]


def _scan_report_for_ids(report_text: str, eval_ids: list[str]) -> dict:
    """Check which eval_ids appear as standalone tokens in the report.

    M3 fix (2026-05-17): substring match flagged false-positives when agent
    quoted the eval_id in surrounding text without actually running the probe.
    Require word-boundary regex match so the id must appear as a distinct
    token — typical legitimate use is in a Verify Report table cell like
    `| us1-action-tag-populated | ✅ PASS | ...`.
    """
    result = {}
    for eid in eval_ids:
        # Escape eid for regex. Negative lookbehind + lookahead both INCLUDE
        # hyphen so a SHORT eid (`us1-action-tag`) does NOT match inside a
        # LONGER eid (`us1-action-tag-populated`). Hyphen is part of slug
        # identity, so `-` is treated as a continuation char.
        pattern = r"(?<![A-Za-z0-9_-])" + re.escape(eid) + r"(?![A-Za-z0-9_-])"
        result[eid] = bool(re.search(pattern, report_text))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec_slug", help="Spec slug (filename in .agent-toolkit/specs/ without .md)")
    ap.add_argument("--report", help="Path to verify report markdown (default: stdin)")
    ap.add_argument("--workspace", help="Workspace root (default: auto-detect from cwd)")
    args = ap.parse_args()

    workspace = Path(args.workspace).resolve() if args.workspace else _find_workspace_root(Path.cwd())

    evals = _load_spec_evals(args.spec_slug, workspace)
    if not evals:
        print(f"info: spec '{args.spec_slug}' has no acceptance_evals — lint skipped.",
              file=sys.stderr)
        return 3

    eval_ids = [e["id"] for e in evals]
    if args.report:
        report_text = Path(args.report).read_text(encoding="utf-8")
    else:
        report_text = sys.stdin.read()

    coverage = _scan_report_for_ids(report_text, eval_ids)
    missing = [eid for eid, found in coverage.items() if not found]
    covered = [eid for eid, found in coverage.items() if found]

    if missing:
        print(f"FAIL: {len(missing)}/{len(eval_ids)} acceptance_evals MISSING from report:",
              file=sys.stderr)
        for eid in missing:
            print(f"  - {eid}", file=sys.stderr)
        print(f"\nCovered: {len(covered)}/{len(eval_ids)}", file=sys.stderr)
        return 1

    print(f"PASS: all {len(eval_ids)} acceptance_evals referenced in report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
