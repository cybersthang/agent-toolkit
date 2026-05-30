#!/usr/bin/env python
"""missing_sd_detector — find Edits not declared as SD nor in spec scope.

Coverage 4 in spec v0.7.2: AGENT may omit SD-N entries for files it
modified. Detects by comparing snapshot's modified-file-list against
the union of:
  - acceptance_evals[].probe.args.target (eval-target files)
  - implement-noted SD-N file references
  - bypass markers (scope-creep-allowed)

Files modified but not in any of the 3 buckets → missing SD candidate.

Public-project safe: paths workspace-relative; no hardcoded names.

CLI:
  python missing_sd_detector.py <slug> [--workspace .] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


SNAPSHOT_REL = ".agent-toolkit/.implement_snapshots"


def _spec_for_slug(workspace: Path, slug: str) -> Optional[Path]:
    for base in (".agent-toolkit/specs", "specs"):
        sd = workspace / base
        if not sd.is_dir():
            continue
        for p in sd.rglob(f"{slug}.md"):
            if p.stem == slug:
                return p
    return None


def _extract_spec_eval_targets(spec_path: Path) -> Set[str]:
    """Return set of file paths referenced as probe.args.target in
    acceptance_evals."""
    targets: Set[str] = set()
    try:
        text = spec_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return targets
    if not text.startswith("---"):
        return targets
    end = text[3:].find("\n---")
    if end < 0:
        return targets
    fm = text[3:3 + end]
    # YAML-ish flat scan for `target:` values
    for m in re.finditer(r"^\s*target\s*:\s*(.+?)\s*$", fm, re.MULTILINE):
        v = m.group(1).strip().strip("'\"")
        # Strip pytest nodeid suffix
        v = v.split("::")[0]
        if v:
            targets.add(v.replace("\\", "/"))
    return targets


def _extract_spec_affected_modules(spec_path: Path) -> List[str]:
    """Read affected_modules list from frontmatter (returns globs/prefixes)."""
    out: List[str] = []
    try:
        text = spec_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    if not text.startswith("---"):
        return out
    end = text[3:].find("\n---")
    if end < 0:
        return out
    fm = text[3:3 + end]
    m = re.search(
        r"^\s*affected_modules\s*:\s*\n((?:\s+- .+\n?)+)",
        fm, re.MULTILINE,
    )
    if not m:
        return out
    for line in m.group(1).splitlines():
        sm = re.match(r"\s*-\s*(.+?)\s*$", line)
        if sm:
            out.append(sm.group(1).strip().strip("'\""))
    return out


def _extract_sd_file_refs(implement_noted_path: Path) -> Set[str]:
    """Pull file paths from each SD-N's `File(s) affected:` line."""
    refs: Set[str] = set()
    if not implement_noted_path.exists():
        return refs
    try:
        text = implement_noted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return refs
    pat = re.compile(
        r"-\s*File\(s\)\s*affected\s*:\s*`?([^\n`]+?)`?\s*$",
        re.MULTILINE,
    )
    for m in pat.finditer(text):
        raw = m.group(1).strip()
        # May contain ":line-line"; strip
        path_part = raw.split(":")[0].strip()
        if path_part and path_part.lower() != "none":
            refs.add(path_part.replace("\\", "/"))
    return refs


def _extract_bypass_files(implement_noted_path: Path) -> Set[str]:
    """Pull file paths from `scope-creep-allowed: <file> <reason>` markers."""
    out: Set[str] = set()
    if not implement_noted_path.exists():
        return out
    try:
        text = implement_noted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for m in re.finditer(
        r"scope-creep-allowed:\s*(\S+)\s+", text, re.IGNORECASE,
    ):
        out.add(m.group(1).replace("\\", "/"))
    return out


def _load_snapshot_modified(workspace: Path, slug: str) -> List[str]:
    """Call implement_snapshot.snapshot_diff_filelist."""
    snap_tool = workspace / ".codex/tools/implement_snapshot.py"
    if not snap_tool.exists():
        # Fallback: try toolkit-internal path
        snap_tool = workspace / "templates/codex/tools/implement_snapshot.py"
    if not snap_tool.exists():
        return []
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_snap", str(snap_tool))
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.snapshot_diff_filelist(slug, workspace) or []
    except Exception:
        return []


def _is_covered(file_path: str, eval_targets: Set[str],
                sd_refs: Set[str], bypass: Set[str],
                affected_modules: List[str]) -> bool:
    """File covered if it matches any of:
      - eval_targets (exact or prefix match)
      - sd_refs (exact)
      - bypass markers
      - affected_modules prefix match (broad scope)
    """
    fp = file_path.replace("\\", "/")
    if fp in sd_refs or fp in bypass:
        return True
    for t in eval_targets:
        if fp == t or fp.endswith("/" + t) or t in fp:
            return True
    for prefix in affected_modules:
        if "*" in prefix:
            # fnmatch-style: simplest substring match for common cases
            stem = prefix.replace("**", "").replace("*", "").rstrip("/").lstrip("/")
            if stem and stem in fp:
                return True
        else:
            if fp.startswith(prefix.rstrip("/")):
                return True
    return False


def detect(slug: str, workspace: Path) -> Dict[str, Any]:
    spec_path = _spec_for_slug(workspace, slug)
    if not spec_path:
        return {"error": "spec not found", "slug": slug}

    impl_noted = spec_path.parent / f"{spec_path.stem}.implement-noted.md"

    eval_targets = _extract_spec_eval_targets(spec_path)
    affected_modules = _extract_spec_affected_modules(spec_path)
    sd_refs = _extract_sd_file_refs(impl_noted)
    bypass = _extract_bypass_files(impl_noted)
    modified = _load_snapshot_modified(workspace, slug)

    missing: List[str] = []
    covered: List[str] = []
    for f in modified:
        if _is_covered(f, eval_targets, sd_refs, bypass, affected_modules):
            covered.append(f)
        else:
            missing.append(f)

    # P4 v0.8.0: cross-check SD-N file refs against actual snapshot
    # modified files. SD claiming a file that wasn't modified = fabricated.
    modified_set = {f.replace("\\", "/") for f in modified}
    fabricated_sd: List[str] = []
    for sd_ref in sd_refs:
        # Need to match against modified set with same normalization as
        # _is_covered (substring tolerance for relative paths).
        matched = False
        for mod in modified_set:
            if sd_ref == mod or sd_ref in mod or mod.endswith("/" + sd_ref):
                matched = True
                break
        if not matched:
            fabricated_sd.append(sd_ref)

    verdict = "clean"
    if missing:
        verdict = "missing-sd"
    if fabricated_sd:
        # fabricated takes priority since it indicates hallucination,
        # higher severity than omission
        verdict = "fabricated-sd" if not missing else "missing-and-fabricated"

    return {
        "slug": slug,
        "spec_path": str(spec_path),
        "implement_noted_path": str(impl_noted),
        "implement_noted_exists": impl_noted.exists(),
        "modified_count": len(modified),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "missing_files": missing,
        "covered_files": covered,
        "fabricated_sd_files": fabricated_sd,
        "fabricated_sd_count": len(fabricated_sd),
        "verdict": verdict,
    }


def render_markdown(result: Dict[str, Any]) -> str:
    if "error" in result:
        return f"## missing_sd_detector — ERROR\n\n- {result['error']}\n"
    lines = [
        f"## missing_sd_detector — `{result['slug']}`",
        "",
        f"- Verdict: **{result['verdict']}**",
        f"- Modified files (vs snapshot): {result['modified_count']}",
        f"- Covered (eval-target / SD / bypass / affected_modules): {result['covered_count']}",
        f"- Missing-SD candidates: {result['missing_count']}",
    ]
    if result.get("missing_files"):
        lines.append("")
        lines.append("### Missing SD files")
        for f in result["missing_files"]:
            lines.append(f"- `{f}`")
        lines.append("")
        lines.append("Action: declare each as SD-N in implement-noted with valid")
        lines.append("Spec linkage, OR add `scope-creep-allowed: <file> <reason>`")
        lines.append("token, OR move to spec's `affected_modules` list.")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="Spec slug")
    ap.add_argument("--workspace", default=".", help="Workspace root")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv[1:])

    workspace = Path(ns.workspace).resolve()
    result = detect(ns.slug, workspace)

    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(result))

    if "error" in result:
        return 2
    return 0 if result.get("verdict") == "clean" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
