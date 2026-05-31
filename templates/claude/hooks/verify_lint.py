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
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, find_workspace_root, run_main_safe,
    get_enforce_mode)
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

# v0.33 F1.2-B (strict): a /verify PASS claim must be backed by a real-data
# probe THIS turn — an mcp__* tool or a Bash run (pytest/make per ADR-002).
_PASS_CLAIM_RE = re.compile(
    r"(?i)(?:\bpass(?:ed|es)?\b|\bcorrect\b|\bverified\b|\bno gaps?\b"
    r"|\ball (?:user )?stories\b|✅)")

# v0.33 (round-2 HIGH fix): a Bash tool_use counts as a real-data probe ONLY if
# the PROGRAM being executed is a test runner — anchored to argv[0] of each
# sub-command (split on ; && || |), NOT a substring match. So `echo pytest`,
# `cat pytest.ini`, `# pytest`, `grep pytest` do NOT count; `pytest`, `make test`,
# `python -m pytest`, `odoo-bin --test-enable`, `cd x && pytest` DO.
_TEST_PROGRAMS = {"pytest", "py.test", "tox", "nose2", "nose",
                  "odoo-bin", "odoo", "psql", "manage.py"}


def _runs_tests(cmd: str) -> bool:
    if not cmd:
        return False
    for sub in re.split(r"(?:&&|\|\||[;&|\n])+", cmd):
        sub = sub.strip()
        if not sub:
            continue
        try:
            tokens = shlex.split(sub)
        except ValueError:
            tokens = sub.split()
        idx = 0                                  # skip leading VAR=val env assignments
        while idx < len(tokens) and re.match(r"^[A-Za-z_]\w*=", tokens[idx]):
            idx += 1
        if idx >= len(tokens):
            continue
        prog = os.path.basename(tokens[idx])
        rest = tokens[idx + 1:]
        if prog in _TEST_PROGRAMS:
            return True
        if prog == "make":            # only a test-ish target counts (not `make clean`)
            return any(t in {"test", "tests", "rebuild", "coverage", "check",
                             "ci", "verify"} for t in rest)
        if prog in ("python", "python3"):
            if "-m" in rest:
                mi = rest.index("-m")
                if mi + 1 < len(rest) and rest[mi + 1] in ("pytest", "unittest"):
                    return True
            if "test" in rest or any(
                    re.search(r"(?:^|/)(?:test_.*|.*_test)\.py$", t) for t in rest):
                return True
    return False


def _claims_pass(text: str) -> bool:
    return bool(_PASS_CLAIM_RE.search(text))


# v0.33 (round-3 HIGH fix): inspecting the COMMAND is whack-a-mole (`pytest
# --version` runs the runner but zero tests). The un-forgeable signal is the
# tool RESULT — written by Claude Code, not the agent. A Bash test command only
# counts if its result shows ACTUAL test execution (`N passed`/`Ran N tests`/
# OK/FAILED), not a version string / `--collect-only` / "no tests ran".
# Require a NON-ZERO test count on a genuine SUMMARY line — round-5 fix: a bare
# `[1-9]\d* passed` matched anywhere let a zero-test runner whose captured output
# merely contained a "1 passed-through…" substring slip through. Anchor to a
# pytest summary banner (`==== N passed ====`), a `N passed … in <t>s` summary,
# a unittest `Ran N tests` line, or `make rebuild`'s `REBUILD GREEN`.
_TEST_RAN_RE = re.compile(
    r"(?im)^(?:"
    r".*={3,}.*\b[1-9]\d*\s+(?:passed|failed|error(?:s|ed)?)\b"          # ==== N passed ====
    r"|.*\b[1-9]\d*\s+(?:passed|failed|error(?:s|ed)?)\b.*\bin\s+[\d.]+\s*s"  # N passed … in 0.3s
    r"|\s*Ran\s+[1-9]\d*\s+tests?\b"                                     # unittest: Ran N tests
    r"|\s*REBUILD GREEN"
    r")")
# mcp tools that constitute a real-data probe (not any read-only mcp call).
_REALDATA_MCP_RE = re.compile(
    r"(?i)(?:realdata|postgres|psql|sql|eval|consistency|orm|query|run_module"
    r"|run_python_tests|probe)")


def _tool_results_by_id(messages: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for rec in messages:
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        # LOW hardening: Claude Code writes tool_result records as USER-role; a
        # tool_result inside an assistant message is malformed/forged → ignore it.
        if (msg.get("role") or rec.get("type")) != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "tool_result":
                tid = blk.get("tool_use_id")
                c = blk.get("content")
                txt = c if isinstance(c, str) else (
                    " ".join(b.get("text", "") for b in c
                             if isinstance(b, dict) and b.get("type") == "text")
                    if isinstance(c, list) else "")
                if tid:
                    out[tid] = txt or ""
    return out


def _turn_records(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Records since the last REAL user prompt (text content). A tool_result is a
    user-role message but NOT a turn boundary, so a `Bash`→tool_result→report
    sequence stays in one turn (plain split-on-user-message would drop the tool_use)."""
    start = 0
    for i, rec in enumerate(messages):
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        if (msg.get("role") or rec.get("type")) != "user":
            continue
        content = msg.get("content")
        has_text = isinstance(content, str) or (
            isinstance(content, list)
            and any(isinstance(b, dict) and b.get("type") == "text" for b in content))
        if has_text:
            start = i
    return messages[start:]


def _has_realdata_tooluse(messages: List[Dict[str, Any]]) -> bool:
    """True iff the CURRENT turn ran ≥1 real-data probe whose RESULT proves it
    executed: a `mcp__*` real-data probe that returned data, or a Bash test
    runner whose output shows tests actually ran (`N passed`/`Ran N`/OK/FAILED).
    A no-op like `pytest --version` or an empty/`list`-type mcp call does NOT —
    the tool_result is harness-written, so the agent can't forge the evidence."""
    results = _tool_results_by_id(messages)
    for rec in _turn_records(messages):
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for blk in content:
            if not (isinstance(blk, dict) and blk.get("type") == "tool_use"):
                continue
            name = blk.get("name") or ""
            res = results.get(blk.get("id") or "", "")
            if name.startswith("mcp__"):
                if _REALDATA_MCP_RE.search(name) and res.strip():
                    return True
            elif name == "Bash" and _runs_tests((blk.get("input") or {}).get("command") or ""):
                if _TEST_RAN_RE.search(res):
                    return True
    return False


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

    lint_script = workspace / ".codex" / "lint_verify_report.py"
    if not lint_script.exists():
        # No lint script installed — toolkit incomplete; fail-open.
        _exit_allow()

    python_bin = sys.executable
    # v0.33 (Q2a): NEW strictness only under enforce_mode block / AGENT_TOOLKIT_STRICT.
    # The existing rc==1 (coverage) / rc==4 (classifier) blocks stay ALWAYS-on.
    strict = get_enforce_mode(workspace, "verify_lint", default="warn") == "block"
    cmd = [python_bin, str(lint_script), slug, "--workspace", str(workspace)]
    if strict:
        cmd.append("--strict")
    try:
        result = subprocess.run(
            cmd, input=text, capture_output=True, text=True,
            encoding="utf-8", timeout=10,
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
    # v0.33 F1.1 (strict): no acceptance_evals → /verify proves nothing → block.
    if result.returncode == 3 and strict:
        _emit_block(
            f"[verify-lint] Spec `{slug}` không có `acceptance_evals` → `/verify` "
            f"không chứng minh được gì (strict). Định nghĩa ≥1 eval "
            f"(`/eval-define {slug}`) rồi re-verify, hoặc tắt strict nếu feature "
            f"thật sự không cần real-data proof."
        )
    # exit_code 0 = lint passed → P11 v0.8.0 auto-cleanup snapshot
    if result.returncode == 0:
        # v0.33 F1.2-B (strict): a PASS claim must have a real-data probe this turn.
        if strict and _claims_pass(text) and not _has_realdata_tooluse(messages):
            _emit_block(
                f"[verify-lint] Verify Report cho `{slug}` claim PASS nhưng turn "
                f"này KHÔNG có real-data probe (mcp__* / Bash pytest|make — ADR-002). "
                f"Chạy probe thật rồi report kết quả raw (số/fingerprint) trước khi chốt PASS."
            )
        _trigger_snapshot_cleanup(workspace, slug)
    # exit_code 0, 2, 3 (non-strict), or other → allow
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
