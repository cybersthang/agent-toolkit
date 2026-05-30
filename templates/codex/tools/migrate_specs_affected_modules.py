#!/usr/bin/env python
"""migrate_specs_affected_modules — backfill `affected_modules` for legacy specs.

For each spec in `.agent-toolkit/specs/**/*.md` (or `specs/**/*.md` for
toolkit dogfood) that lacks the `affected_modules:` frontmatter field,
this tool:
  1. Uses `git log --follow --name-only` to find files modified in
     commits that touched the spec.
  2. Computes the top-N directory prefixes from that file list.
  3. Inserts `affected_modules: [...]` into the spec frontmatter
     (preserves other fields).

Idempotent: re-running on a spec that already has the field is a no-op.
Public-project safe: no hardcoded names.

CLI:
  python migrate_specs_affected_modules.py [--workspace .] [--apply]
                                            [--top-n 8] [--spec <slug>]

Without `--apply`: dry-run (prints proposed changes).
With `--apply`: writes changes to spec files.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _git_log_files_for_spec(workspace: Path, spec_rel: str) -> List[str]:
    """Find all files committed alongside the spec across its history."""
    try:
        # First: list commit SHAs that touched this spec.
        proc = subprocess.run(
            ["git", "log", "--format=%H", "--", spec_rel],
            cwd=str(workspace), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        if proc.returncode != 0:
            return []
        shas = [s for s in proc.stdout.splitlines() if s.strip()]
        if not shas:
            return []
    except (subprocess.SubprocessError, OSError):
        return []

    files: Set[str] = set()
    for sha in shas[:20]:  # cap to recent 20 commits
        try:
            proc = subprocess.run(
                ["git", "show", "--name-only", "--format=", sha],
                cwd=str(workspace), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
            )
            if proc.returncode != 0:
                continue
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Skip the spec itself + verify reports + implement-noted
                if line.endswith(".md") and (
                    "spec" in line.lower()
                    or "verify_report" in line
                    or "implement-noted" in line
                ):
                    continue
                files.add(line.replace("\\", "/"))
        except (subprocess.SubprocessError, OSError):
            continue
    return sorted(files)


def _derive_module_prefixes(files: List[str], top_n: int = 8) -> List[str]:
    """Pick top-N most-frequent directory prefixes (filenames stripped)."""
    counter: Counter = Counter()
    for f in files:
        parts = f.split("/")
        # Strip filename: if last part has an extension or starts with '.',
        # treat as file; drop it.
        if parts and ("." in parts[-1] or parts[-1].startswith(".")):
            parts = parts[:-1]
        if not parts:
            continue
        # 2-segment dir prefix if available; else 1-segment.
        if len(parts) >= 2:
            counter[f"{parts[0]}/{parts[1]}/"] += 1
        else:
            counter[parts[0] + "/"] += 1
    sorted_prefixes = sorted(
        counter.items(), key=lambda kv: (-kv[1], kv[0]),
    )
    return [p for p, _ in sorted_prefixes[:top_n]]


def _spec_has_affected_modules(text: str) -> bool:
    if not text.startswith("---"):
        return False
    end = text[3:].find("\n---")
    if end < 0:
        return False
    fm = text[3:3 + end]
    return bool(re.search(r"^\s*affected_modules\s*:", fm, re.MULTILINE))


def _insert_affected_modules(text: str, prefixes: List[str]) -> str:
    """Insert `affected_modules:` into frontmatter after `module:` (or
    after `slug:` if no module field). Idempotent."""
    if _spec_has_affected_modules(text):
        return text  # idempotent
    if not text.startswith("---"):
        return text
    end = text[3:].find("\n---")
    if end < 0:
        return text
    fm = text[3:3 + end]
    body = text[3 + end + 4:]
    lines = fm.split("\n")

    insert_at = -1
    for idx, ln in enumerate(lines):
        if re.match(r"^\s*module\s*:", ln):
            insert_at = idx + 1
            break
    if insert_at < 0:
        for idx, ln in enumerate(lines):
            if re.match(r"^\s*slug\s*:", ln):
                insert_at = idx + 1
                break
    if insert_at < 0:
        insert_at = len(lines)

    insertion = ["affected_modules:"]
    for p in prefixes:
        insertion.append(f"  - {p}")
    new_lines = lines[:insert_at] + insertion + lines[insert_at:]
    return "---\n" + "\n".join(new_lines) + "\n---" + body


def migrate(workspace: Path, apply: bool, top_n: int,
            target_slug: Optional[str] = None) -> Dict[str, Any]:
    candidates: List[Path] = []
    for base in (".agent-toolkit/specs", "specs"):
        sd = workspace / base
        if not sd.is_dir():
            continue
        for p in sd.rglob("*.md"):
            stem = p.stem
            # Skip aux files
            if any(suf in stem for suf in
                   ("verify_report", "implement-noted", "gap-fix-cycle-trace",
                    "runtime_fire_evidence", "diff-annotations")):
                continue
            if target_slug and stem != target_slug:
                continue
            candidates.append(p)

    results: List[Dict[str, Any]] = []
    for spec_path in candidates:
        try:
            text = spec_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _spec_has_affected_modules(text):
            results.append({
                "spec": str(spec_path.relative_to(workspace)),
                "status": "already-has-affected-modules",
            })
            continue
        spec_rel = str(spec_path.relative_to(workspace)).replace("\\", "/")
        files = _git_log_files_for_spec(workspace, spec_rel)
        prefixes = _derive_module_prefixes(files, top_n=top_n) or [
            "templates/", "tests/", "specs/",
        ]
        new_text = _insert_affected_modules(text, prefixes)
        if new_text == text:
            results.append({
                "spec": spec_rel,
                "status": "no-change-needed",
            })
            continue
        if apply:
            try:
                spec_path.write_text(new_text, encoding="utf-8")
                results.append({
                    "spec": spec_rel,
                    "status": "migrated",
                    "prefixes_added": prefixes,
                    "files_analyzed": len(files),
                })
            except OSError as e:
                results.append({
                    "spec": spec_rel,
                    "status": "write-failed",
                    "error": str(e),
                })
        else:
            results.append({
                "spec": spec_rel,
                "status": "would-migrate (dry-run)",
                "prefixes_proposed": prefixes,
                "files_analyzed": len(files),
            })
    return {"apply": apply, "results": results, "count": len(results)}


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--top-n", type=int, default=8)
    ap.add_argument("--spec", default=None,
                    help="Single spec slug to migrate (default: all)")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv[1:])
    workspace = Path(ns.workspace).resolve()
    result = migrate(workspace, apply=ns.apply, top_n=ns.top_n,
                     target_slug=ns.spec)
    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{'APPLY' if ns.apply else 'DRY-RUN'}: {result['count']} specs evaluated")
        for r in result["results"]:
            print(f"  - {r['spec']}: {r['status']}")
            if r.get("prefixes_added") or r.get("prefixes_proposed"):
                pfxs = r.get("prefixes_added") or r.get("prefixes_proposed")
                for p in pfxs:
                    print(f"      + {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
