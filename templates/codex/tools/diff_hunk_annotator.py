#!/usr/bin/env python
"""diff_hunk_annotator — parse diff vs snapshot, emit annotation template.

Coverage 2 (semantic creep) in spec v0.7.2: catches code changes
INSIDE affected_modules but unrelated to acceptance_evals.

Workflow:
  1. Compute diff between snapshot and current state for each modified file.
  2. Extract unified-diff "hunks" (contiguous @@-delimited regions).
  3. Emit `<slug>.diff-annotations.md` template with 1 row per hunk
     and a `tag:` field DEV/AGENT fills.
  4. diff_annotation_validator.py asserts every hunk row has a non-empty
     tag (eval id, SD-N reference, or `untagged-hunk-allowed: <reason>`).

Public-project safe: no hardcoded paths; reads workspace.

CLI:
  python diff_hunk_annotator.py <slug> [--workspace .] [--write|--json]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SNAPSHOT_REL = ".agent-toolkit/.implement_snapshots"


def _load_snapshot_manifest(workspace: Path, slug: str) -> Dict[str, Any]:
    p = workspace / SNAPSHOT_REL / slug / "_manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _hunks_for_file(workspace: Path, slug: str, file_rel: str,
                    entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compute unified diff between snapshot and current; return list
    of hunk dicts."""
    current_path = workspace / file_rel
    snap_path = workspace / SNAPSHOT_REL / slug / file_rel

    if entry.get("type") == "net-new":
        # All lines are "added"
        if not current_path.exists():
            return []
        try:
            text = current_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        lines = text.splitlines()
        if not lines:
            return []
        return [{
            "file": file_rel,
            "hunk_id": "net-new-1",
            "type": "net-new",
            "start_line": 1,
            "end_line": len(lines),
            "preview": "\n".join(lines[:5]) + ("\n…" if len(lines) > 5 else ""),
        }]

    if not snap_path.exists() or not current_path.exists():
        return []
    try:
        old = snap_path.read_text(encoding="utf-8", errors="replace").splitlines()
        new = current_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    diff = list(difflib.unified_diff(old, new, n=0, lineterm=""))
    hunks: List[Dict[str, Any]] = []
    hunk_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
    current_hunk: Optional[Dict[str, Any]] = None
    hunk_index = 0
    for line in diff:
        m = hunk_re.match(line)
        if m:
            if current_hunk:
                hunks.append(current_hunk)
            hunk_index += 1
            new_start = int(m.group(3))
            new_count = int(m.group(4) or "0")
            current_hunk = {
                "file": file_rel,
                "hunk_id": f"h{hunk_index}",
                "type": "modify",
                "start_line": new_start,
                "end_line": new_start + new_count - 1 if new_count else new_start,
                "preview_lines": [],
            }
        elif current_hunk is not None and line.startswith(("+", "-")):
            if len(current_hunk["preview_lines"]) < 5:
                current_hunk["preview_lines"].append(line)
    if current_hunk:
        hunks.append(current_hunk)

    for h in hunks:
        h["preview"] = "\n".join(h.pop("preview_lines", []))
    return hunks


def _spec_for_slug(workspace: Path, slug: str) -> Optional[Path]:
    for base in (".agent-toolkit/specs", "specs"):
        sd = workspace / base
        if not sd.is_dir():
            continue
        for p in sd.rglob(f"{slug}.md"):
            if p.stem == slug:
                return p
    return None


def _extract_eval_targets(spec_path: Path) -> Dict[str, List[str]]:
    """Return {eval_id: [file paths]} for each acceptance_eval with
    probe.args.target. Used by auto-tag inference."""
    out: Dict[str, List[str]] = {}
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
    # Block scan: each `- id: <id>` then look ahead for `target: <path>`.
    current_id: Optional[str] = None
    for line in fm.splitlines():
        m_id = re.match(r"^\s*-\s*id:\s*([\w.\-]+)\s*$", line)
        if m_id:
            current_id = m_id.group(1)
            out.setdefault(current_id, [])
            continue
        m_target = re.match(r"^\s*target\s*:\s*(.+?)\s*$", line)
        if m_target and current_id:
            v = m_target.group(1).strip().strip("'\"")
            v = v.split("::")[0]  # strip pytest nodeid
            if v:
                out[current_id].append(v.replace("\\", "/"))
    return out


def _extract_sd_file_refs(impl_noted_path: Path) -> Dict[str, List[str]]:
    """Return {SD-N: [file paths]} from implement-noted."""
    out: Dict[str, List[str]] = {}
    if not impl_noted_path.exists():
        return out
    try:
        text = impl_noted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    # Find SD-N blocks via either heading or list form, then look for
    # `File(s) affected:` within reasonable proximity.
    head_pat = re.compile(
        r"^#{2,4}\s*SD-(?P<n>\d+)\s*[:\-]\s*[^\n]*"
        r"(?P<body>(?:\n(?!\s*#{2,4}\s*[A-Za-z]).*)*)",
        re.MULTILINE,
    )
    list_pat = re.compile(
        r"^\s*-\s*\*\*SD-(?P<n>\d+)\*\*\s*:\s*[^\n]*"
        r"(?P<body>(?:\n(?:\s{2,}-|\s{4,}).+)*)",
        re.MULTILINE,
    )
    seen: set = set()
    for pat in (head_pat, list_pat):
        for m in pat.finditer(text):
            n = m.group("n")
            if n in seen:
                continue
            seen.add(n)
            body = m.group("body") or ""
            for fm in re.finditer(
                r"-\s*File\(s\)\s*affected\s*:\s*`?([^\n`]+?)`?\s*$",
                body, re.MULTILINE,
            ):
                raw = fm.group(1).strip()
                path_part = raw.split(":")[0].strip()
                if path_part and path_part.lower() != "none":
                    out.setdefault(f"SD-{n}", []).append(
                        path_part.replace("\\", "/"))
    return out


def _auto_tag_hunk(file_rel: str,
                   eval_targets: Dict[str, List[str]],
                   sd_refs: Dict[str, List[str]]) -> Optional[str]:
    """Infer tag value for a hunk based on file_rel matching eval target
    OR SD file ref. Returns None if no unambiguous match."""
    file_norm = file_rel.replace("\\", "/")
    matched: List[str] = []
    # Try eval targets first (more authoritative)
    for eval_id, paths in eval_targets.items():
        for p in paths:
            if file_norm == p or file_norm.endswith("/" + p) or p in file_norm:
                matched.append(eval_id)
                break
    # Then SD refs
    for sd_id, paths in sd_refs.items():
        for p in paths:
            if file_norm == p or file_norm.endswith("/" + p) or p in file_norm:
                matched.append(sd_id)
                break
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        # Ambiguous → prefer eval id (first match)
        for m in matched:
            if not m.startswith("SD-"):
                return m
        return matched[0]
    return None


def build_annotation_template(slug: str, workspace: Path) -> Dict[str, Any]:
    manifest = _load_snapshot_manifest(workspace, slug)
    files_map = manifest.get("files") or {}
    if not files_map:
        return {"slug": slug, "hunks": [], "note": "no snapshot manifest",
                "auto_tagged": 0}

    # Load inference sources
    spec_path = _spec_for_slug(workspace, slug)
    eval_targets: Dict[str, List[str]] = {}
    sd_refs: Dict[str, List[str]] = {}
    if spec_path:
        eval_targets = _extract_eval_targets(spec_path)
        impl_noted = spec_path.parent / f"{slug}.implement-noted.md"
        sd_refs = _extract_sd_file_refs(impl_noted)

    all_hunks: List[Dict[str, Any]] = []
    auto_tagged_count = 0
    for file_rel, entry in files_map.items():
        if not isinstance(entry, dict):
            continue
        hunks = _hunks_for_file(workspace, slug, file_rel, entry)
        for h in hunks:
            auto_tag = _auto_tag_hunk(h["file"], eval_targets, sd_refs)
            if auto_tag:
                h["auto_tag"] = auto_tag
                auto_tagged_count += 1
        all_hunks.extend(hunks)

    return {
        "slug": slug,
        "hunks": all_hunks,
        "auto_tagged": auto_tagged_count,
        "total_eval_targets": sum(len(v) for v in eval_targets.values()),
        "total_sd_refs": sum(len(v) for v in sd_refs.values()),
    }


def render_markdown_template(template: Dict[str, Any]) -> str:
    """Markdown file template — each hunk → 1 numbered row. Auto-tagged
    hunks have their tag pre-filled; residual hunks get FILL placeholder."""
    hunks = template.get("hunks") or []
    auto_tagged = template.get("auto_tagged") or 0
    total = len(hunks)
    untagged = total - auto_tagged
    lines = [
        "---",
        f"slug: {template.get('slug')}",
        f"total_hunks: {total}",
        f"total_auto_tagged: {auto_tagged}",
        f"total_untagged: {untagged}",
        "---",
        "",
        "# Diff hunk annotations",
        "",
        "Auto-generated by `diff_hunk_annotator.py`. Hunks where file",
        "matches a spec eval target OR implement-noted SD-N file ref",
        "are auto-tagged. Residual hunks need manual `tag:` fill before",
        "`diff_annotation_validator.py` will pass.",
        "",
        "Valid tag values:",
        "- An acceptance_eval id from the spec.",
        "- An SD-N reference from implement-noted.",
        "- Bypass: `untagged-hunk-allowed: <reason>`.",
        "",
    ]
    for h in hunks:
        tag_value = h.get("auto_tag") or "<FILL eval-id | SD-N | untagged-hunk-allowed: reason>"
        lines.extend([
            f"## hunk `{h.get('file')}:{h.get('hunk_id')}`",
            "",
            f"- type: {h.get('type')}",
            f"- lines: {h.get('start_line')}-{h.get('end_line')}",
            f"- tag: {tag_value}",
            "",
            "```diff",
            h.get("preview") or "(empty)",
            "```",
            "",
        ])
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="Spec slug")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--write", action="store_true",
                    help="Write file to .agent-toolkit/specs/<branch>/<slug>.diff-annotations.md")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv[1:])

    workspace = Path(ns.workspace).resolve()
    template = build_annotation_template(ns.slug, workspace)

    if ns.json:
        print(json.dumps(template, ensure_ascii=False, indent=2))
        return 0

    md = render_markdown_template(template)
    if ns.write:
        # Find spec path to determine sibling location
        for base in (".agent-toolkit/specs", "specs"):
            sd = workspace / base
            if not sd.is_dir():
                continue
            for p in sd.rglob(f"{ns.slug}.md"):
                target = p.parent / f"{ns.slug}.diff-annotations.md"
                target.write_text(md, encoding="utf-8")
                print(f"Wrote {target}")
                return 0
        # Fallback: cwd
        target = workspace / f"{ns.slug}.diff-annotations.md"
        target.write_text(md, encoding="utf-8")
        print(f"Wrote {target}")
        return 0

    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
