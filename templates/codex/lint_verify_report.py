#!/usr/bin/env python
"""Lint a /verify Report against spec.acceptance_evals (enforces ADR-007 Bước 1.5).

Purpose
-------
After agent runs /verify and emits a Verify Report (markdown), this script
verifies that every entry in the spec's `acceptance_evals:` frontmatter block
was referenced in the report. If any eval id is missing → exit non-zero, list
the missing ids. Stop hook + agent can then re-emit with full coverage.

Additionally (2026-05-19), when spec frontmatter sets
`feature_kind: classification`, the report MUST contain a "Real-Data Proof"
section header — enforcing `verify-feature/SKILL.md` Step 1.8's mandate
beyond the honor-system layer. Closes the M1 medium finding.

Usage
-----
    # Pipe report stdin → lint
    cat verify_report.md | python lint_verify_report.py <spec-slug>

    # Or pass a file
    python lint_verify_report.py <spec-slug> --report path/to/report.md

Exit codes
----------
0 = report covers all acceptance_evals AND any required sections
1 = missing eval(s) from report
2 = spec not found / not readable
3 = no acceptance_evals in spec (lint not applicable)
4 = classifier spec missing the required Real-Data Proof section
5 = spec declares `reuse_targets` but report does not cite them
    (v0.12.0 — closes "reuse hàm có sẵn" gap)
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


def _load_spec_meta(spec_slug: str, workspace: Path) -> dict:
    """Return spec metadata needed for lint: evals + feature_kind + path.

    Shape: ``{"evals": [{"id": ...}, ...], "feature_kind": str | None,
              "spec_path": Path}``.

    `evals` is [] when no acceptance_evals block is present.
    `feature_kind` is the literal frontmatter value (lower-cased) when set,
    else None — callers compare against ``"classification"``.
    """
    # Resolve spec via rglob — supports branch-scoped (`<branch>/<slug>.md`)
    # and legacy flat layouts. Pick the most-recently-modified match.
    specs_dir = workspace / ".agent-toolkit" / "specs"
    matches = sorted(
        specs_dir.rglob(f"{spec_slug}.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ) if specs_dir.is_dir() else []
    if not matches:
        print(f"error: spec not found: {specs_dir}/**/{spec_slug}.md", file=sys.stderr)
        sys.exit(2)
    spec_path = matches[0]
    text = spec_path.read_text(encoding="utf-8")
    # Extract YAML frontmatter (between first --- and second ---).
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        print(f"error: spec has no YAML frontmatter: {spec_path}", file=sys.stderr)
        sys.exit(2)
    fm_text = m.group(1)
    if yaml is None:
        # Fallback: crude regex parse of `- id: <slug>` lines under
        # acceptance_evals and a single-line `feature_kind: <value>`.
        evals_list: list[dict] = []
        if "acceptance_evals:" in fm_text:
            after = fm_text.split("acceptance_evals:", 1)[1]
            ids = re.findall(
                r"^\s*-\s*id:\s*([^\s]+)\s*$", after, re.MULTILINE
            )
            evals_list = [{"id": i} for i in ids]
        kind_m = re.search(
            r"^\s*feature_kind\s*:\s*[\"']?([A-Za-z0-9_-]+)[\"']?\s*$",
            fm_text, re.MULTILINE,
        )
        reuse_list: list[str] = []
        if "reuse_targets:" in fm_text:
            after = fm_text.split("reuse_targets:", 1)[1]
            # Stop at the next top-level YAML key (line starting with non-space
            # followed by `:` and end-of-line or value). Tolerant fallback —
            # full YAML lib path above handles arbitrary nesting.
            block_end = re.search(r"\n[A-Za-z_][\w-]*:", after)
            block = after[: block_end.start()] if block_end else after
            reuse_list = [
                m.group(1).strip()
                for m in re.finditer(r"^\s*-\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
                                     block, re.MULTILINE)
                if m.group(1).strip()
            ]
        return {
            "evals": evals_list,
            "feature_kind": kind_m.group(1).lower() if kind_m else None,
            "reuse_targets": reuse_list,
            "spec_path": spec_path,
        }
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        print(f"error: spec frontmatter not valid YAML: {exc}", file=sys.stderr)
        sys.exit(2)
    evals = fm.get("acceptance_evals") or []
    kind = fm.get("feature_kind")
    reuse = fm.get("reuse_targets") or []
    return {
        "evals": [e for e in evals if isinstance(e, dict) and e.get("id")],
        "feature_kind": (kind.lower() if isinstance(kind, str) else None),
        "reuse_targets": [r for r in reuse if isinstance(r, str) and r.strip()],
        "spec_path": spec_path,
    }


def _load_spec_evals(spec_slug: str, workspace: Path) -> list[dict]:
    """Backward-compatible wrapper — returns just the evals list."""
    return _load_spec_meta(spec_slug, workspace)["evals"]


# Real-Data Proof section header — matches the canonical form emitted by
# real-data-proof/SKILL.md Step 4: `## Real-Data Proof — <slug>` and the
# tolerant variants (`### Real Data Proof`, `**Real-Data Proof Report**`).
# Case-insensitive; allows hyphen OR space between Real and Data; optional
# "Report" suffix; allowed inside a heading or bold span.
_REAL_DATA_PROOF_RE = re.compile(
    r"(?im)^\s*(?:#+\s*|\*\*\s*)real[-\s]?data\s*proof\b",
)

# v0.12.0 — Reuse Metric section header. Accepts both bullet-list and table
# forms below the heading.
_REUSE_METRIC_RE = re.compile(
    r"(?im)^\s*(?:#+\s*|\*\*\s*)reuse\s*(?:metric|targets?)\b",
)


def _has_real_data_proof_section(report_text: str) -> bool:
    return bool(_REAL_DATA_PROOF_RE.search(report_text))


def _has_reuse_metric_section(report_text: str) -> bool:
    return bool(_REUSE_METRIC_RE.search(report_text))


def _reuse_targets_cited(report_text: str, targets: list) -> list:
    """Return the subset of `targets` NOT cited verbatim in report."""
    missing = []
    for t in targets:
        # Treat target as a literal substring (allows path:line and module.fn forms)
        if t not in report_text:
            missing.append(t)
    return missing


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

    meta = _load_spec_meta(args.spec_slug, workspace)
    evals = meta["evals"]
    feature_kind = meta["feature_kind"]
    reuse_targets = meta.get("reuse_targets") or []
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

    # Classifier specs MUST include a Real-Data Proof section — enforces
    # verify-feature/SKILL.md Step 1.8 (mandatory for feature_kind:
    # classification). Without this check Step 1.8 is honor-system.
    if feature_kind == "classification" and not _has_real_data_proof_section(report_text):
        print(
            "FAIL: spec has feature_kind: classification but Verify Report "
            "is missing the required `Real-Data Proof` section.",
            file=sys.stderr,
        )
        print(
            "  Fix: re-emit the report with a `## Real-Data Proof` section "
            "(per real-data-proof/SKILL.md Step 4) — including a Data source "
            "line, a Distribution table, a Falsification table with measured "
            "Δ per tag, and a Revert checklist.",
            file=sys.stderr,
        )
        return 4

    # v0.12.0 — Reuse Metric check. Spec declares reuse_targets → report
    # must either include a `## Reuse Metric` section OR cite every target
    # verbatim (path:fn or module.Class.method). Otherwise exit 5.
    if reuse_targets:
        if not _has_reuse_metric_section(report_text):
            uncited = _reuse_targets_cited(report_text, reuse_targets)
            if uncited:
                print(
                    f"FAIL: spec declares {len(reuse_targets)} reuse_targets "
                    f"but report has no `Reuse Metric` section and "
                    f"{len(uncited)} target(s) are not cited:",
                    file=sys.stderr,
                )
                for t in uncited:
                    print(f"  - {t}", file=sys.stderr)
                print(
                    "  Fix: add `## Reuse Metric` section listing which "
                    "reuse_targets you actually called (or explain why "
                    "you rewrote instead).",
                    file=sys.stderr,
                )
                return 5

    print(f"PASS: all {len(eval_ids)} acceptance_evals referenced in report.")
    if feature_kind == "classification":
        print("PASS: Real-Data Proof section present (classifier spec).")
    if reuse_targets:
        print(f"PASS: reuse_targets ({len(reuse_targets)}) covered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
