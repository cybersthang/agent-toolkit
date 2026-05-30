#!/usr/bin/env python
"""implement_noted_validator — validate <slug>.implement-noted.md content.

Catches Coverage 3 (hallucinated SD/T/F) in spec v0.7.2:
  - SD-N file path actually exists.
  - SD-N line range within file's line count.
  - SD-N Spec linkage eval id exists in the parent spec's
    acceptance_evals list (or is the literal "none").
  - T-N has non-empty Transcript evidence cite.
  - F-N priority is valid enum.
  - Frontmatter total_* counts match actual section item counts.

Public-project safe: no hardcoded path; reads workspace + spec via CLI.

CLI:
  python implement_noted_validator.py <spec_path> [--workspace .] [--json]

Exit:
  0 — valid
  1 — issues found (issues printed to stdout JSON or markdown)
  2 — file missing / parse error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


VALID_PRIORITY = {"high", "medium", "med", "low"}


def _spec_for_slug(workspace: Path, slug: str) -> Optional[Path]:
    sd = workspace / ".agent-toolkit" / "specs"
    if not sd.is_dir():
        # Fallback: also check upstream specs/ dir (toolkit dogfood)
        alt = workspace / "specs"
        if alt.is_dir():
            for p in alt.rglob(f"{slug}.md"):
                if p.stem == slug:
                    return p
        return None
    for p in sd.rglob(f"{slug}.md"):
        if p.stem == slug:
            return p
    # Toolkit dogfood fallback
    alt = workspace / "specs"
    if alt.is_dir():
        for p in alt.rglob(f"{slug}.md"):
            if p.stem == slug:
                return p
    return None


def _parse_implement_noted(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: Dict[str, Any] = {"frontmatter": {}, "sd_items": [], "t_items": [],
                           "f_items": [], "raw": text}
    if not text.startswith("---"):
        return out
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        return out
    fm_text = rest[:end]
    # Parse frontmatter as flat key:value (no nested structures expected)
    for line in fm_text.splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*:\s*(.+?)\s*$", line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
            if val.isdigit():
                out["frontmatter"][key] = int(val)
            elif val.lower() in ("true", "false"):
                out["frontmatter"][key] = val.lower() == "true"
            else:
                out["frontmatter"][key] = val
    body = text[3 + end + 4:]

    # Extract SD-N / T-N / F-N items via either:
    #  (a) inline list form: `- **SD-N**: title`
    #  (b) heading form: `### SD-N: title`
    for tag, key in [("SD", "sd_items"), ("T", "t_items"), ("F", "f_items")]:
        # Match heading form first (### SD-N: ...)
        head_pat = re.compile(
            r"^#{2,4}\s*" + tag + r"-(?P<n>\d+)\s*[:\-]\s*(?P<title>[^\n]+)"
            r"(?P<body>(?:\n(?!\s*#{2,4}\s*[A-Z]).*)*)",
            re.MULTILINE,
        )
        # Match list form (- **SD-N**: ...)
        list_pat = re.compile(
            r"^\s*-\s*\*\*" + tag + r"-(?P<n>\d+)\*\*\s*:\s*(?P<title>[^\n]+)"
            r"(?P<body>(?:\n(?:\s{2,}-|\s{4,}).+)*)",
            re.MULTILINE,
        )
        seen_idx: set = set()
        for pat in (head_pat, list_pat):
            for m in pat.finditer(body):
                idx = m.group("n")
                if idx in seen_idx:
                    continue
                seen_idx.add(idx)
                block = (m.group("title") or "") + "\n" + (m.group("body") or "")
                item: Dict[str, Any] = {"index": idx, "title": m.group("title")}
                for sf in ("Type", "File\\(s\\) affected", "Spec linkage",
                           "Confidence", "Transcript evidence",
                           "Priority", "Lý do", "Rationale"):
                    sub_m = re.search(
                        r"-\s*" + sf + r"\s*:\s*(?P<v>[^\n]+)", block)
                    if sub_m:
                        field_name = sf.replace("\\(s\\)", "(s)").lower()
                        item[field_name] = sub_m.group("v").strip()
                out[key].append(item)
    return out


def _resolve_file_ref(workspace: Path, ref: str) -> Optional[Path]:
    """Extract path part from 'path/to/file.py:line-line' style ref."""
    if not ref:
        return None
    ref = ref.split("`")[1] if ref.startswith("`") and "`" in ref[1:] else ref
    # Strip line range suffix
    path_part = ref.split(":")[0].strip("` ")
    if not path_part:
        return None
    p = workspace / path_part
    return p if p.exists() else None


def _parse_line_range(ref: str) -> Optional[tuple]:
    m = re.search(r":(\d+)(?:-(\d+))?", ref or "")
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    return (start, end)


SUPPORTED_SCHEMA_VERSIONS = {1}


def validate(implement_noted_path: Path, workspace: Path,
             enforce_schema_version: bool = True) -> Dict[str, Any]:
    if not implement_noted_path.exists():
        return {"error": "file not found", "path": str(implement_noted_path)}
    data = _parse_implement_noted(implement_noted_path)
    fm = data["frontmatter"]
    issues: List[Dict[str, Any]] = []

    # Phase G v0.9.0: schema_version enforcement
    schema_version = fm.get("schema_version")
    if enforce_schema_version:
        if schema_version is None:
            issues.append({
                "kind": "schema-version-missing",
                "item": "frontmatter",
                "detail": "schema_version field required. Add `schema_version: 1` to frontmatter.",
            })
        elif schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            issues.append({
                "kind": "schema-version-unsupported",
                "item": "frontmatter",
                "detail": f"schema_version={schema_version} not in supported {SUPPORTED_SCHEMA_VERSIONS}",
            })

    # Load parent spec for eval id cross-check
    slug = fm.get("spec") or implement_noted_path.stem.replace(".implement-noted", "")
    spec_path = _spec_for_slug(workspace, slug)
    eval_ids: set = set()
    if spec_path:
        try:
            spec_text = spec_path.read_text(encoding="utf-8", errors="replace")
            # Quick frontmatter eval id scan
            for m in re.finditer(r"^\s*-\s*id:\s*([\w.\-]+)\s*$",
                                 spec_text, re.MULTILINE):
                eval_ids.add(m.group(1))
        except OSError:
            pass

    # Validate SD items
    for sd in data["sd_items"]:
        idx = sd.get("index", "?")
        f_ref = sd.get("file(s) affected") or ""
        if f_ref and f_ref != "none":
            p = _resolve_file_ref(workspace, f_ref)
            if not p:
                issues.append({
                    "kind": "sd-file-missing",
                    "item": f"SD-{idx}",
                    "detail": f"File reference does not resolve: {f_ref!r}",
                })
            else:
                line_range = _parse_line_range(f_ref)
                if line_range:
                    try:
                        text = p.read_text(encoding="utf-8", errors="replace")
                        line_count = text.count("\n") + 1
                        if line_range[1] > line_count + 5:
                            # Allow ±5 line tolerance for post-edit drift
                            issues.append({
                                "kind": "sd-line-out-of-range",
                                "item": f"SD-{idx}",
                                "detail": f"Line range {line_range} exceeds file's {line_count} lines",
                            })
                    except OSError:
                        pass
        linkage = (sd.get("spec linkage") or "").strip().lower()
        if linkage and linkage != "none" and eval_ids:
            # Linkage value may contain extra text; try to match any eval id
            matched = any(eid.lower() in linkage for eid in eval_ids)
            if not matched:
                issues.append({
                    "kind": "sd-spec-linkage-unknown",
                    "item": f"SD-{idx}",
                    "detail": f"Spec linkage references unknown eval id: {linkage!r}",
                })
        conf = (sd.get("confidence") or "").strip().lower()
        if conf and conf not in ("high", "medium", "med", "low"):
            issues.append({
                "kind": "sd-confidence-invalid",
                "item": f"SD-{idx}",
                "detail": f"Confidence value not in {{high, medium, low}}: {conf!r}",
            })

    # Validate T items
    for t in data["t_items"]:
        idx = t.get("index", "?")
        evidence = (t.get("transcript evidence") or "").strip()
        if not evidence or evidence.lower() == "none":
            issues.append({
                "kind": "t-transcript-evidence-missing",
                "item": f"T-{idx}",
                "detail": "Trade-off has no transcript cite (strict cite-required)",
            })

    # Validate F items
    for f in data["f_items"]:
        idx = f.get("index", "?")
        prio = (f.get("priority") or "").strip().lower()
        if prio and prio not in VALID_PRIORITY:
            issues.append({
                "kind": "f-priority-invalid",
                "item": f"F-{idx}",
                "detail": f"Priority not in {{high, medium, low}}: {prio!r}",
            })

    # Frontmatter count cross-check
    actual_counts = {
        "total_scope_deviations": len(data["sd_items"]),
        "total_tradeoffs_with_evidence": len(data["t_items"]),
        "total_followups": len(data["f_items"]),
    }
    for key, actual in actual_counts.items():
        declared = fm.get(key)
        if declared is not None and declared != actual:
            issues.append({
                "kind": "frontmatter-count-mismatch",
                "item": key,
                "detail": f"declared={declared} actual={actual}",
            })

    return {
        "path": str(implement_noted_path),
        "slug": slug,
        "spec_found": str(spec_path) if spec_path else None,
        "eval_id_count": len(eval_ids),
        "item_counts": actual_counts,
        "issues": issues,
        "verdict": "clean" if not issues else "issues",
    }


def render_markdown(result: Dict[str, Any]) -> str:
    if "error" in result:
        return f"## implement_noted_validator — ERROR\n\n- {result['error']}\n"
    lines = [
        f"## implement_noted_validator — `{Path(result['path']).name}`",
        "",
        f"- Verdict: **{result['verdict']}**",
        f"- Spec found: `{result['spec_found'] or '(none)'}`",
        f"- Eval ids in spec: {result['eval_id_count']}",
        f"- Item counts: {result['item_counts']}",
        "",
    ]
    issues = result.get("issues") or []
    if issues:
        lines.append(f"### Issues ({len(issues)})")
        for iss in issues:
            lines.append(f"- **{iss['kind']}** `{iss['item']}`: {iss['detail']}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="Path to <slug>.implement-noted.md")
    ap.add_argument("--workspace", default=".",
                    help="Workspace root (default: cwd)")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of markdown")
    ap.add_argument("--no-schema-check", action="store_true",
                    help="Skip schema_version field check (legacy mode)")
    ns = ap.parse_args(argv[1:])

    workspace = Path(ns.workspace).resolve()
    path = Path(ns.path).resolve()
    result = validate(path, workspace,
                      enforce_schema_version=not ns.no_schema_check)

    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(result))

    if "error" in result:
        return 2
    return 0 if result.get("verdict") == "clean" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
