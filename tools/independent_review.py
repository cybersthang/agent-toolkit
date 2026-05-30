#!/usr/bin/env python3
"""v0.31.0 independent-review — context-packet assembler (CLI).

`emit-context <spec-slug>` builds the CODE-assembled context packet a
fresh-context reviewer sub-agent consumes (ID-1..ID-2, ID-14), and prints a
deterministic `packet_sha`. The packet is the ONLY input the reviewer is told
to use — assembling it in code (not letting the agent curate it) is what gives
the review its independence-by-construction (ID-2/ID-14).

Packet content (reviewer-facing, real text):
  1. DIFF        — `git diff HEAD` of feature-scope files (ID-9/ID-23).
  2. SPEC        — the spec markdown.
  3. EVALS       — the spec `acceptance_evals` block.
  4. INVARIANTS  — `.agent-toolkit/invariants.json` (must-keep patterns).
  5. RELATED     — files imported by changed .py files, pruned (ID-19).

`packet_sha` (ID-18/ID-23): sha256 over the NORMALIZED concat of
diff+spec+evals+invariants — comment-only / whitespace-only lines stripped so a
comment-only edit does not invalidate a still-valid review, while a spec/eval
change DOES. Reuses the sha-fingerprint trust-model of `_audit/pass_contract.py`.

NOT a hook — opt-in CLI invoked by the `independent-review` skill / the
`/review-independent` command. Bám pattern `tools/parallel_wave.py`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Default feature-scope patterns (ID-9). Mirrors auto_test_runner.py:55 for
# Odoo, plus the toolkit's own python surface so the tool dogfoods itself.
DEFAULT_SCOPE_RE = re.compile(
    r"(?:(?:models|controllers|wizard|wizards|jobs)/[^/]+\.py$)"
    r"|(?:^(?:tools|lib)/[^/]+\.py$)"
    r"|(?:templates/claude/hooks/[^/]+\.py$)"
)
MAX_RELATED_FILES = 12  # ID-19 prune cap
_STDLIB = getattr(sys, "stdlib_module_names", frozenset())  # 3.10+; empty pre-3.10
PACKET_REL = ".agent-toolkit"
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)
COMMENT_OR_BLANK = re.compile(r"^\s*(#.*)?$")


def _run_git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_root(start: Path) -> Path:
    top = _run_git(start, "rev-parse", "--show-toplevel").strip()
    return Path(top) if top else start.resolve()


def changed_files(root: Path) -> List[str]:
    """Tracked-file changes vs HEAD + untracked (best-effort)."""
    files = set(_run_git(root, "diff", "HEAD", "--name-only").splitlines())
    files.update(_run_git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(f for f in files if f.strip())


def feature_scope(files: List[str], scope_re: re.Pattern) -> List[str]:
    return [f for f in files if scope_re.search(f)]


def diff_for(root: Path, files: List[str]) -> str:
    if not files:
        return ""
    return _run_git(root, "diff", "HEAD", "--", *files)


_GIT_META = re.compile(r"^(diff --git |index |@@ |--- |\+\+\+ )")


def normalize_for_hash(text: str) -> str:
    """Hash-stable normalization (ID-18/ID-23): drop volatile git-diff metadata
    (index/hunk/path headers) and comment-only / whitespace-only lines —
    INCLUDING diff-prefixed (`+`/`-`) ones — so a comment-only edit does NOT
    change the sha while a real code change does. Retained code lines keep their
    `+`/`-` prefix (so add vs remove stay distinct). Strip trailing ws."""
    out: List[str] = []
    for ln in text.splitlines():
        if _GIT_META.match(ln):
            continue
        body = ln[1:] if ln[:1] in "+-" else ln  # peek past diff prefix
        if COMMENT_OR_BLANK.match(body):
            continue
        out.append(ln.rstrip())
    return "\n".join(out)


def find_spec(root: Path, slug: str) -> Optional[Path]:
    # Both layouts: repo/dogfood `specs/`; consumer `.agent-toolkit/specs/`.
    hits = sorted(root.glob(f"specs/**/*{slug}*.md")) + \
        sorted(root.glob(f".agent-toolkit/specs/**/*{slug}*.md"))
    hits = [h for h in hits if not h.name.endswith(
        (".tasks.md", ".verify_report.md", ".implement-noted.md"))]
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)


def extract_acceptance_evals(spec_text: str) -> str:
    lines = spec_text.splitlines()
    out: List[str] = []
    grabbing = False
    for ln in lines:
        if ln.startswith("acceptance_evals:"):
            grabbing = True
        if grabbing:
            if ln.startswith("eval_status:") or ln.strip() == "---":
                break
            out.append(ln)
    return "\n".join(out)


def relevant_invariants(root: Path) -> str:
    p = root / ".agent-toolkit" / "invariants.json"
    try:
        return p.read_text(encoding="utf-8-sig") if p.exists() else "{}"
    except OSError:
        return "{}"


def prune_related(root: Path, files: List[str]) -> List[Tuple[str, str]]:
    """ID-19: include files imported by changed .py files (light static scan)."""
    related: Dict[str, str] = {}
    py_files = [root / f for f in files if f.endswith(".py")]
    for pf in py_files:
        try:
            src = pf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for mod in IMPORT_RE.findall(src):
            top = mod.split(".")[0]
            # Skip stdlib / trivially-short names — else `import os/json/re`
            # triggers a full `**` tree walk per import that never hits the cap
            # (no match) — a real latency risk inside the gate's 15s timeout.
            if top in _STDLIB or len(top) <= 2:
                continue
            for cand in (root.glob(f"**/{top}.py")):
                rel = str(cand.relative_to(root))
                if rel in files or rel in related:
                    continue
                try:
                    related[rel] = cand.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if len(related) >= MAX_RELATED_FILES:
                    return list(related.items())
    return list(related.items())


def build_packet(root: Path, slug: str,
                 scope_re: re.Pattern = DEFAULT_SCOPE_RE) -> Dict[str, object]:
    spec_path = find_spec(root, slug)
    if spec_path is None:
        raise FileNotFoundError(f"spec not found for slug: {slug}")
    spec_text = spec_path.read_text(encoding="utf-8")
    files = feature_scope(changed_files(root), scope_re)
    diff = diff_for(root, files)
    evals = extract_acceptance_evals(spec_text)
    inv = relevant_invariants(root)
    related = prune_related(root, files)

    # ID-18/ID-23: hash over NORMALIZED contract (diff+spec+evals+invariants).
    hash_src = "\n".join(normalize_for_hash(s) for s in (diff, spec_text, evals, inv))
    packet_sha = hashlib.sha256(hash_src.encode("utf-8")).hexdigest()

    related_md = "\n\n".join(
        f"### related: {name}\n```\n{body}\n```" for name, body in related
    ) or "(none)"
    packet = (
        f"# REVIEW CONTEXT PACKET — {slug}\n"
        f"packet_sha: {packet_sha}\n\n"
        f"> Reviewer: review ONLY from this packet. Default-skeptic — try to\n"
        f"> REFUTE each diff hunk; do NOT assume the implementer was right (ID-15).\n\n"
        f"## 1. DIFF (feature-scope: {len(files)} file)\n```diff\n{diff or '(empty)'}\n```\n\n"
        f"## 2. SPEC\n{spec_text}\n\n"
        f"## 3. ACCEPTANCE_EVALS\n```yaml\n{evals or '(none)'}\n```\n\n"
        f"## 4. INVARIANTS (must-keep)\n```json\n{inv}\n```\n\n"
        f"## 5. RELATED (pruned ≤{MAX_RELATED_FILES})\n{related_md}\n"
    )
    return {"packet_sha": packet_sha, "packet": packet,
            "scope_files": files, "related_count": len(related),
            "spec_path": str(spec_path)}


def emit_context(project_dir: Path, slug: str) -> Dict[str, object]:
    root = repo_root(project_dir)
    res = build_packet(root, slug)
    out_dir = root / PACKET_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    sha8 = str(res["packet_sha"])[:8]
    packet_path = out_dir / f".review_packet.{sha8}.md"
    packet_path.write_text(str(res["packet"]), encoding="utf-8")
    return {"packet_sha": res["packet_sha"], "packet_path": str(packet_path),
            "scope_files": res["scope_files"], "related_count": res["related_count"]}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="independent-review context packet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ec = sub.add_parser("emit-context", help="build packet + print packet_sha")
    ec.add_argument("slug")
    ec.add_argument("--project-dir", default=".")
    args = ap.parse_args(argv)

    if args.cmd == "emit-context":
        try:
            res = emit_context(Path(args.project_dir), args.slug)
        except FileNotFoundError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
