#!/usr/bin/env python
"""Stop hook — auto-invoke `.codex/lint_verify_report.py` on Verify Reports.

Closes the enforcement gap identified in code review 2026-05-17: previously
`verify-feature/SKILL.md` Bước 8 said "BẮT BUỘC chạy lint" but no hook
enforced it. Now: when the agent emits a response containing a Verify Report
header, this hook extracts the spec slug + report text and runs the lint
script. If lint exits non-zero (missing acceptance_evals coverage), the Stop
is BLOCKED with the missing eval ids so the agent must re-emit.

Detection
---------
Looks in the final assistant message text for:
  - Verify Report header (regex `(?:#+\s*|^\s*)verify\s*report\b`, case-insensitive)
  - Spec slug — pattern `Verify Report\s*[-—]\s*<slug>` OR `Spec: .agent-toolkit/specs/<slug>.md`

If slug cannot be inferred, hook silent (fail-open).

Lint invocation
---------------
Runs `<PYTHON_BIN> <WORKSPACE>/.codex/lint_verify_report.py <slug>` with the
response text piped to stdin. Exit code:
  0 → allow Stop
  1 → BLOCK with "missing N evals: <ids>" reason
  3 → allow (spec has no acceptance_evals — lint not applicable)
  4 → BLOCK with "classifier spec missing Real-Data Proof section" reason
  any other → allow (script error; don't punish agent for infra)

Loops are bounded: if `stop_hook_active` is set in envelope, exit allow.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, find_workspace_root, run_main_safe)
from _patterns import (  # noqa: E402
    VERIFY_REPORT_HEADER_RE as _VERIFY_REPORT_HEADER_RE,
    SLUG_PATTERNS as _SLUG_PATTERNS,
)

wrap_utf8_stdio()


def _exit_allow() -> None:
    sys.exit(0)


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


_read_transcript = read_jsonl_transcript


def _last_assistant_text(messages: List[Dict[str, Any]]) -> str:
    """Return the text from the final assistant message in transcript."""
    for msg in reversed(messages):
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                block.get("text", "") for block in content
                if block.get("type") == "text"
            )
    return ""


def _extract_spec_slug(text: str, workspace: Optional[Path] = None) -> Optional[str]:
    """Extract spec slug from report text.

    FIX-4 (2026-05-17): collect ALL candidate slugs across patterns, then
    return the first one that has an actual spec file at
    `<workspace>/.agent-toolkit/specs/<slug>.md`. Avoids false-positive
    captures like 'failed' or 'NEEDS' that appear in Verify Report fail
    summaries. Falls back to first non-empty candidate if workspace unknown
    (caller handles spec-not-found gracefully).
    """
    candidates: List[str] = []
    for pat in _SLUG_PATTERNS:
        for m in pat.finditer(text):
            slug = m.group(1).strip()
            if slug and len(slug) <= 100 and not slug.isdigit():
                if slug not in candidates:
                    candidates.append(slug)
    if not candidates:
        return None
    if workspace is not None:
        specs_dir = workspace / ".agent-toolkit" / "specs"
        for slug in candidates:
            # Branch-scoped layout: specs/<branch>/<slug>.md
            # Legacy flat layout:   specs/<slug>.md
            # rglob picks both.
            if any(specs_dir.rglob(f"{slug}.md")):
                return slug
    return candidates[0]


_find_workspace_root = find_workspace_root


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_allow()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_allow()
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_allow()

    # Avoid re-entrance loop.
    if envelope.get("stop_hook_active"):
        _exit_allow()

    transcript_path = envelope.get("transcript_path")
    if not transcript_path:
        _exit_allow()
    tpath = Path(transcript_path)
    if not tpath.exists():
        _exit_allow()
    messages = _read_transcript(tpath)
    if not messages:
        _exit_allow()

    text = _last_assistant_text(messages)
    if not text or not _VERIFY_REPORT_HEADER_RE.search(text):
        _exit_allow()

    workspace_str = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = _find_workspace_root(Path(workspace_str)) or Path(workspace_str).resolve()

    slug = _extract_spec_slug(text, workspace=workspace)
    if not slug:
        # Can't determine which spec — fail-open with diagnostic.
        _exit_allow()

    # Resolve spec via rglob (branch-scoped + legacy flat both supported).
    specs_dir = workspace / ".agent-toolkit" / "specs"
    matches = sorted(
        specs_dir.rglob(f"{slug}.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ) if specs_dir.is_dir() else []
    if not matches:
        # Slug parsed but spec file missing — agent typo'd; fail-open.
        _exit_allow()
    spec_path = matches[0]

    lint_script = workspace / ".codex" / "lint_verify_report.py"
    if not lint_script.exists():
        # No lint script installed — toolkit incomplete; fail-open.
        _exit_allow()

    python_bin = sys.executable
    try:
        result = subprocess.run(
            [python_bin, str(lint_script), slug, "--workspace", str(workspace)],
            input=text,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        _exit_allow()

    if result.returncode == 1:
        _emit_block(
            f"[verify-lint] Verify Report cho `{slug}` thiếu coverage:\n\n"
            + (result.stderr or "<no detail>")
            + "\n\nFix: re-emit Verify Report cite các eval id thiếu (mỗi id trong "
            "1 row của bảng `| <eid> | <result> | ...`). Hoặc nếu eval không "
            "còn applicable, sửa spec frontmatter để remove entry đó trước."
        )
    if result.returncode == 4:
        _emit_block(
            f"[verify-lint] Spec `{slug}` có `feature_kind: classification` "
            f"nhưng Verify Report thiếu section bắt buộc `Real-Data Proof`.\n\n"
            + (result.stderr or "<no detail>")
            + "\n\nFix: re-emit Verify Report kèm `## Real-Data Proof` "
            "section đầy đủ 4 mục (Data source / Distribution / Falsification / "
            "Revert checklist) — xem `real-data-proof/SKILL.md` Step 4 + "
            "worked example `references/block-async-worked-example.md`. "
            "Mỗi tag distinct phải có ≥1 perturb-test row trong bảng "
            "Falsification."
        )
    # exit_code 0 = lint passed → P11 v0.8.0 auto-cleanup snapshot
    if result.returncode == 0:
        _trigger_snapshot_cleanup(workspace, slug)
    # exit_code 0, 2, 3, or other → allow
    _exit_allow()


def _trigger_snapshot_cleanup(workspace: Path, slug: str) -> None:
    """P11 v0.8.0: when verify_lint passes for a slug, snapshot is no
    longer needed (Layer 5 scope check already ran). Call
    snapshot_cleanup with force=True. Best-effort, silent on failure."""
    tool = workspace / ".codex" / "tools" / "implement_snapshot.py"
    if not tool.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(tool), "cleanup",
             "--slug", slug, "--workspace", str(workspace), "--force"],
            capture_output=True, timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        pass


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
