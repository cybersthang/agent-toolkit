#!/usr/bin/env python
"""diff_annotation_validator — assert every hunk in .diff-annotations.md is tagged.

Coverage 2 enforcement: AGENT/DEV must tag each hunk with eval id,
SD-N reference, or `untagged-hunk-allowed:` bypass. Any untagged
hunk = block /verify.

Public-project safe.

CLI:
  python diff_annotation_validator.py <annotations.md> [--workspace .] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


TAG_PLACEHOLDER_RE = re.compile(
    r"<FILL\s+eval-id\s*\|\s*SD-N\s*\|\s*untagged-hunk-allowed:?\s*reason>",
    re.IGNORECASE,
)


def _spec_for_slug(workspace: Path, slug: str) -> Optional[Path]:
    for base in (".agent-toolkit/specs", "specs"):
        sd = workspace / base
        if not sd.is_dir():
            continue
        for p in sd.rglob(f"{slug}.md"):
            if p.stem == slug:
                return p
    return None


def _eval_ids(spec_path: Path) -> Set[str]:
    out: Set[str] = set()
    try:
        text = spec_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for m in re.finditer(r"^\s*-\s*id:\s*([\w.\-]+)\s*$", text, re.MULTILINE):
        out.add(m.group(1))
    return out


def _impl_noted_sd_ids(workspace: Path, slug: str) -> Set[str]:
    spec_path = _spec_for_slug(workspace, slug)
    if not spec_path:
        return set()
    impl_noted = spec_path.parent / f"{slug}.implement-noted.md"
    if not impl_noted.exists():
        return set()
    text = impl_noted.read_text(encoding="utf-8", errors="replace")
    return {m.group(0) for m in re.finditer(r"\bSD-\d+\b", text)}


def validate(annotations_path: Path, workspace: Path) -> Dict[str, Any]:
    if not annotations_path.exists():
        return {"error": "annotations file not found", "path": str(annotations_path)}
    text = annotations_path.read_text(encoding="utf-8", errors="replace")
    # Parse frontmatter slug
    slug = ""
    if text.startswith("---"):
        end = text[3:].find("\n---")
        if end > 0:
            fm = text[3:3 + end]
            sm = re.search(r"^\s*slug\s*:\s*(.+?)\s*$", fm, re.MULTILINE)
            if sm:
                slug = sm.group(1).strip()
    if not slug:
        slug = annotations_path.stem.replace(".diff-annotations", "")

    eval_ids = _eval_ids(_spec_for_slug(workspace, slug)) if slug else set()
    sd_ids = _impl_noted_sd_ids(workspace, slug)
    valid_tags = eval_ids | sd_ids

    # Parse each hunk block + its tag line
    hunk_pat = re.compile(
        r"^##\s*hunk\s+`(?P<file>[^`]+):(?P<hid>[^`]+)`\s*$"
        r"(?P<block>.*?)(?=^##\s*hunk|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    issues: List[Dict[str, Any]] = []
    total = 0
    tagged = 0
    for m in hunk_pat.finditer(text):
        total += 1
        block = m.group("block") or ""
        tag_m = re.search(r"^\s*-\s*tag\s*:\s*(.+?)\s*$", block, re.MULTILINE)
        tag_val = (tag_m.group(1).strip() if tag_m else "")

        if not tag_val or TAG_PLACEHOLDER_RE.search(tag_val):
            issues.append({
                "kind": "untagged-hunk",
                "hunk": f"{m.group('file')}:{m.group('hid')}",
                "detail": "tag field is empty or contains placeholder",
            })
            continue
        # Tagged → validate value
        is_bypass = "untagged-hunk-allowed" in tag_val.lower()
        if is_bypass:
            tagged += 1
            continue
        # Try matching eval id OR SD-N pattern
        matched = False
        for valid in valid_tags:
            if valid in tag_val:
                matched = True
                break
        if not matched:
            issues.append({
                "kind": "tag-unknown-reference",
                "hunk": f"{m.group('file')}:{m.group('hid')}",
                "detail": f"tag {tag_val!r} not in spec eval ids or implement-noted SD ids",
            })
            continue
        tagged += 1

    return {
        "path": str(annotations_path),
        "slug": slug,
        "total_hunks": total,
        "tagged": tagged,
        "untagged_or_invalid": total - tagged,
        "valid_tag_count": len(valid_tags),
        "issues": issues,
        "verdict": "clean" if not issues else "issues",
    }


def render_markdown(result: Dict[str, Any]) -> str:
    if "error" in result:
        return f"## diff_annotation_validator — ERROR\n\n- {result['error']}\n"
    lines = [
        f"## diff_annotation_validator — `{result['slug']}`",
        "",
        f"- Verdict: **{result['verdict']}**",
        f"- Total hunks: {result['total_hunks']}",
        f"- Tagged: {result['tagged']}",
        f"- Untagged or invalid: {result['untagged_or_invalid']}",
        f"- Valid tag references known: {result['valid_tag_count']}",
    ]
    for iss in (result.get("issues") or [])[:10]:
        lines.append(f"  - **{iss['kind']}** `{iss['hunk']}`: {iss['detail']}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="Path to <slug>.diff-annotations.md")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv[1:])
    workspace = Path(ns.workspace).resolve()
    path = Path(ns.path).resolve()
    result = validate(path, workspace)
    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(result))
    if "error" in result:
        return 2
    return 0 if result.get("verdict") == "clean" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
