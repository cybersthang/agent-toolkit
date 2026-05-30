#!/usr/bin/env python
"""gap_status — concise probe-status table for one spec.

Engine for the `/gap-status` slash command + `gap-status` skill. Reads
spec frontmatter + probes registry + auto_run_probes state + last
verify_report cell, classifies each probe per skill spec, prints a
markdown table.

Project-agnostic: no stack-specific assumptions. Driven by acceptance-
probes.schema.json v2 fields.

Usage:
  python .codex/tools/gap_status.py [<spec-slug>]
  python .codex/tools/gap_status.py --json [<spec-slug>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / ".agent-toolkit" / "specs"
PROBES_PATH = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"
AUTO_PROBES_STATE = REPO_ROOT / ".agent-toolkit" / ".auto_probes_state.json"
AUTO_TEST_STATE = REPO_ROOT / ".agent-toolkit" / ".auto_test_state.json"

# Staleness threshold (7 days)
STALE_S = 7 * 24 * 3600


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _find_spec(slug: Optional[str]) -> Optional[Path]:
    if not SPECS_DIR.is_dir():
        return None
    candidates = list(SPECS_DIR.glob("**/*.md"))
    # Exclude tasks.md / verify_report.md / *_evidence.md etc — only spec.
    candidates = [
        p for p in candidates
        if p.stem not in ("tasks", "verify_report")
        and "evidence" not in p.stem.lower()
    ]
    if not candidates:
        return None
    if slug:
        for p in candidates:
            if p.stem == slug:
                return p
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _parse_spec_frontmatter(spec_path: Path) -> Dict[str, Any]:
    """Extract slug + acceptance_eval ids from spec markdown frontmatter."""
    text = spec_path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.startswith("---"):
        return {"slug": spec_path.stem, "eval_ids": [], "feature_kind": None}
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        return {"slug": spec_path.stem, "eval_ids": [], "feature_kind": None}
    block = rest[:end]
    slug = spec_path.stem
    feature_kind = None
    eval_ids: List[str] = []
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("slug:"):
            slug = s.split(":", 1)[1].strip()
        elif s.startswith("feature_kind:"):
            feature_kind = s.split(":", 1)[1].strip()
        elif re.match(r"^\s*-\s*id:\s*", line):
            eid = line.split(":", 1)[1].strip()
            eval_ids.append(eid)
    return {"slug": slug, "eval_ids": eval_ids,
            "feature_kind": feature_kind, "path": str(spec_path)}


def _find_verify_report(spec_path: Path) -> Optional[Path]:
    """Look for verify_report.md sibling of the spec."""
    candidate = spec_path.parent / "verify_report.md"
    return candidate if candidate.exists() else None


def _verify_report_cell(report_path: Path, probe_id: str) -> Optional[str]:
    """Crude lookup: find row in verify_report that mentions probe_id +
    extract last token like PASS/FAIL/PENDING."""
    if not report_path:
        return None
    text = report_path.read_text(encoding="utf-8-sig", errors="replace")
    for line in text.splitlines():
        if probe_id in line.lower() or probe_id.replace("-", " ") in line.lower():
            low = line.lower()
            for label, key in [("pass", "passed"), ("verified", "passed"),
                               ("fail", "failed"), ("gap", "gap"),
                               ("blocker", "blocker"), ("pending", "pending")]:
                if label in low:
                    return key
    return None


def _classify(probe: Dict[str, Any], auto_state: Dict[str, Any],
              verify_cell: Optional[str], now: float) -> Dict[str, Any]:
    """Resolve last verdict + classify status."""
    pid = probe.get("id") or ""
    severity = (probe.get("severity") or "warn").lower()
    auto = auto_state.get(pid) or {}

    verdict = (auto.get("status") or "").lower()
    source = "auto_run_probes" if verdict else None
    ts = auto.get("ts") or 0
    age_s = (now - ts) if ts else None

    if not verdict and verify_cell:
        verdict = verify_cell
        source = "verify_report"
        age_s = None

    if not verdict:
        status = "unknown"
    elif verdict in ("proven", "passed", "verified", "ok"):
        if age_s is not None and age_s > STALE_S and probe.get("auto_run"):
            status = "stale"
        else:
            status = "within-predicate"
    elif verdict in ("refuted", "failed", "fail", "gap", "blocker"):
        status = "failing"
    elif verdict == "pending":
        status = "pending"
    else:
        status = "unknown"

    return {
        "id": pid,
        "severity": severity,
        "predicate": (probe.get("description") or "")[:80],
        "verdict": verdict or "—",
        "source": source or "—",
        "age_s": age_s,
        "status": status,
        "auto_run": bool(probe.get("auto_run")),
    }


def _next_action(rows: List[Dict[str, Any]], slug: str) -> str:
    failing = [r for r in rows if r["status"] == "failing"]
    blocker_failing = [r for r in failing if r["severity"] == "blocker"]
    unknown = [r for r in rows if r["status"] == "unknown"]
    if blocker_failing:
        return (
            f"`/implement {slug}` — gap-fix-cycle will engage on "
            f"{len(blocker_failing)} blocker(s) failing"
        )
    if failing:
        ids = ", ".join(r["id"] for r in failing[:3])
        return f"`/run-probes` targeted on: {ids}"
    if unknown:
        return f"`/run-probes` (full diff) — {len(unknown)} probe(s) unknown"
    return f"`/verify {slug}` to finalize report"


def gap_status(slug: Optional[str], as_json: bool = False) -> Dict[str, Any]:
    spec_path = _find_spec(slug)
    if not spec_path:
        return {"error": "no spec found", "specs_dir": str(SPECS_DIR)}

    frontmatter = _parse_spec_frontmatter(spec_path)
    probes_data = _load_json(PROBES_PATH)
    probes = [p for p in (probes_data.get("probes") or []) if isinstance(p, dict)]
    auto_state = _load_json(AUTO_PROBES_STATE)
    verify_report = _find_verify_report(spec_path)

    now = time.time()
    rows: List[Dict[str, Any]] = []
    for probe in probes:
        pid = probe.get("id") or ""
        verify_cell = _verify_report_cell(verify_report, pid) if verify_report else None
        rows.append(_classify(probe, auto_state, verify_cell, now))

    summary = {
        "spec": frontmatter.get("slug"),
        "spec_path": str(spec_path),
        "feature_kind": frontmatter.get("feature_kind"),
        "verify_report": str(verify_report) if verify_report else None,
        "total_probes": len(rows),
        "within_predicate": sum(1 for r in rows if r["status"] == "within-predicate"),
        "failing": sum(1 for r in rows if r["status"] == "failing"),
        "unknown": sum(1 for r in rows if r["status"] == "unknown"),
        "stale": sum(1 for r in rows if r["status"] == "stale"),
        "blockers_outstanding": [
            r["id"] for r in rows
            if r["severity"] == "blocker" and r["status"] in ("failing", "unknown")
        ],
        "next_action": _next_action(rows, frontmatter.get("slug") or "<slug>"),
        "rows": rows,
    }
    return summary


def render_markdown(summary: Dict[str, Any]) -> str:
    if "error" in summary:
        return f"## Gap status — ERROR\n\n- {summary['error']}\n"
    lines = [
        f"## Gap status — `{summary['spec']}`",
        "",
        f"feature_kind: `{summary.get('feature_kind') or '(none)'}` · "
        f"verify_report: `{summary.get('verify_report') or '(none)'}`",
        "",
        "| Probe | Severity | Predicate | Last evidence | Status |",
        "|---|---|---|---|---|",
    ]
    for r in summary["rows"]:
        age = ""
        if r.get("age_s") is not None:
            age = f" ({int(r['age_s']/60)}m ago)" if r["age_s"] < 3600 else \
                  f" ({int(r['age_s']/3600)}h ago)"
        evid = f"{r['verdict']} via {r['source']}{age}" if r["verdict"] != "—" else "(none)"
        lines.append(
            f"| `{r['id']}` | {r['severity']} | {r['predicate']} | {evid} | {r['status']} |"
        )
    lines.extend([
        "",
        f"**Total**: {summary['total_probes']} · "
        f"within-predicate {summary['within_predicate']} · "
        f"failing {summary['failing']} · "
        f"unknown {summary['unknown']} · "
        f"stale {summary['stale']}",
    ])
    if summary["blockers_outstanding"]:
        lines.append(
            f"**Blockers outstanding**: {', '.join(summary['blockers_outstanding'])}"
        )
    lines.append(f"**Next action**: {summary['next_action']}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slug", nargs="?", default=None)
    ap.add_argument("--json", action="store_true",
                    help="Emit raw summary JSON instead of markdown table")
    ns = ap.parse_args(argv[1:])
    summary = gap_status(ns.slug, as_json=ns.json)
    if "error" in summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    if ns.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
