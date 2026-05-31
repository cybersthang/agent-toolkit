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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, find_workspace_root, run_main_safe,
    get_enforce_mode, converge_or_degrade, converge_reset, spec_is_feature_scope,
    spec_has_acceptance_evals)
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


_VERIFY_BYPASS_REL = ".agent-toolkit/.skip_verify_lint_next.json"
_VERIFY_BYPASS_TTL = 600  # seconds — mirrors git_guardrails one-shot token


def _consume_verify_bypass(workspace: Path) -> tuple:
    """T3b — single-shot override token at `.agent-toolkit/.skip_verify_lint_next.json`
    (any JSON content) that lets ONE verify-report stop through, whatever trigger
    fired. Consumed (deleted) on read; honored only within TTL.

    TRUST MODEL (review round-1 HIGH — claim corrected): this is the SAME
    DEV-convention escape as git_guardrails' `.skip_git_guard_next.json`, enforced
    by the CLAUDE.md "agent must not author its own bypass" rule, NOT mechanically —
    an agent with the Write tool *could* author this file today (no deny-glob guards
    `.skip_*` yet; that is Phase-4 T8b's `deny_write_glob` rule-type, which should
    cover this path). The genuinely un-forgeable anchor is the RESULT-INSPECTION
    (`_TEST_RAN_RE` over the harness-written tool_result) — that this token exists
    does NOT weaken it; the token only changes the *block/allow* decision, never the
    proof itself. `has_bypass=True` for this gate means the escape is reachable, so
    R5.1 "escalate-and-HOLD" can't deadlock. Returns (ok, reason). Never raises."""
    tok = workspace / _VERIFY_BYPASS_REL
    try:
        if not tok.is_file():
            return (False, "")
        age = time.time() - tok.stat().st_mtime
        try:
            raw = tok.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
        except (OSError, ValueError):
            data = {}
        reason = str(data.get("reason") or "").strip() if isinstance(data, dict) else ""
        try:
            tok.unlink()  # single-shot: consume even if invalid (cleanup)
        except OSError:
            pass
        # review round-1 MED: a future mtime (clock skew / `touch -d +1d`) makes age
        # negative — reject it so the TTL can't be sidestepped by a future stamp.
        if age < 0 or age > _VERIFY_BYPASS_TTL:
            return (False, "")
        return (True, reason)
    except OSError:
        return (False, "")


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
# F1.5 (v0.34): launchers to unwrap so a REAL run still counts as a probe.
_RUN_LAUNCHERS = {"poetry", "uv", "pdm", "hatch", "pipenv"}       # `<x> run <cmd>`
_PREFIX_LAUNCHERS = {"env", "nice", "ionice", "stdbuf", "xvfb-run", "timeout", "chrt"}
_VALUE_FLAGS = {"-s", "--signal", "-k", "--kill-after"}           # take a following value


def _effective_program(tokens: List[str]) -> tuple:
    """F1.5: strip leading env-assignments + known launchers (poetry/uv run, env,
    nice, timeout <n>, xvfb-run, …) so the REAL executed program surfaces — a real
    test run via a launcher must still count. Returns (prog_basename, rest)."""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if re.match(r"^[A-Za-z_]\w*=", tok):            # VAR=val env-assignment
            i += 1
            continue
        base = os.path.basename(tok)
        if base in _RUN_LAUNCHERS:
            if i + 1 < len(tokens) and tokens[i + 1] == "run":
                i += 2
                continue
            break                                        # bare `poetry`/`uv` → not a runner
        if base in _PREFIX_LAUNCHERS:
            i += 1
            while i < len(tokens):                       # skip launcher opts + timeout duration
                t = tokens[i]
                if t in _VALUE_FLAGS:
                    i += 2
                    continue
                if (t.startswith("-")
                        or re.match(r"^\d+(?:\.\d+)?[smhd]?$", t)
                        or re.match(r"^[A-Za-z_]\w*=", t)):
                    i += 1
                    continue
                break
            continue
        break
    if i >= len(tokens):
        return "", []
    return os.path.basename(tokens[i]), tokens[i + 1:]


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
        prog, rest = _effective_program(tokens)   # F1.5: unwrap launchers
        if not prog:
            continue
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
    spec_path = matches[0]
    # v0.33 (Q2a) + v0.34 T3 (F1.1): the no-evals / PASS-without-probe blocks fire
    # only under enforce_mode block (strict) AND only for FEATURE-SCOPE specs
    # (R5.5 blast-radius limit). The pre-existing rc==1 (coverage) / rc==4
    # (classifier) blocks stay always-on. All four route through ONE decision point
    # so each honors the single-shot DEV bypass token (T3b) + the convergence-cap
    # (T2 / R5.1, per-trigger key) — no verify_lint block can deadlock.
    strict = get_enforce_mode(workspace, "verify_lint", default="warn") == "block"
    feature_scope = spec_is_feature_scope(spec_path)
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
    rc = result.returncode
    detail = result.stderr or "<no detail>"

    # Decide whether this stop blocks, and on which trigger (per-trigger streak key).
    block_key: Optional[str] = None
    message = ""
    if rc == 1:
        block_key = "coverage"
        message = (
            f"[verify-lint] Verify Report cho `{slug}` thiếu coverage:\n\n{detail}\n\n"
            "Fix: re-emit Verify Report cite các eval id thiếu (mỗi id trong 1 row "
            "của bảng `| <eid> | <result> | ...`). Hoặc nếu eval không còn applicable, "
            "sửa spec frontmatter để remove entry đó trước."
        )
    elif rc == 4:
        block_key = "classification"
        message = (
            f"[verify-lint] Spec `{slug}` có `feature_kind: classification` nhưng "
            f"Verify Report thiếu section bắt buộc `Real-Data Proof`.\n\n{detail}\n\n"
            "Fix: re-emit Verify Report kèm `## Real-Data Proof` section đầy đủ 4 mục "
            "(Data source / Distribution / Falsification / Revert checklist) — xem "
            "`real-data-proof/SKILL.md` Step 4 + worked example "
            "`references/block-async-worked-example.md`. Mỗi tag distinct phải có ≥1 "
            "perturb-test row trong bảng Falsification."
        )
    # v0.33 F1.1 + v0.34 T3 (strict + feature-scope): no acceptance_evals → /verify
    # proves nothing → block. Non-feature spec → warn-only (allow). Review round-1
    # HIGH: lint rc==3 means no *frontmatter* evals — re-check LOCATION-AGNOSTICALLY
    # so a spec with body-placed evals (this repo's v0.33/v0.34 specs) isn't FP-blocked.
    elif (rc == 3 and strict and feature_scope
          and not spec_has_acceptance_evals(spec_path)):
        block_key = "noevals"
        message = (
            f"[verify-lint] Spec `{slug}` không có `acceptance_evals` → `/verify` "
            f"không chứng minh được gì (strict). Định nghĩa ≥1 eval "
            f"(`/eval-define {slug}`) rồi re-verify, hoặc tắt strict nếu feature "
            f"thật sự không cần real-data proof."
        )
    # v0.33 F1.2-B + v0.34 T3 (strict + feature-scope): a PASS claim must have a
    # real-data probe this turn (the un-forgeable result-inspection anchor).
    elif (rc == 0 and strict and feature_scope
          and _claims_pass(text) and not _has_realdata_tooluse(messages)):
        block_key = "passprobe"
        message = (
            f"[verify-lint] Verify Report cho `{slug}` claim PASS nhưng turn này "
            f"KHÔNG có real-data probe (mcp__* / Bash pytest|make — ADR-002). Chạy "
            f"probe thật rồi report kết quả raw (số/fingerprint) trước khi chốt PASS."
        )

    if block_key is None:
        # Satisfied — or non-strict / non-feature-scope (warn-only). Clear streaks + allow.
        for k in ("coverage", "classification", "noevals", "passprobe"):
            converge_reset(workspace, "verify_lint", f"{k}:{slug}")
        if rc == 3 and strict and not feature_scope:
            print(
                f"[verify-lint] (warn) spec `{slug}` không có acceptance_evals nhưng "
                f"đánh dấu non-feature (`feature_scope: false` / `feature_kind: meta…`) "
                f"→ chỉ cảnh báo, không chặn.",
                file=sys.stderr,
            )
        if rc == 0:
            _trigger_snapshot_cleanup(workspace, slug)
        _exit_allow()

    # would-block → DEV single-shot override wins (T3b); else convergence decides.
    ok, reason = _consume_verify_bypass(workspace)
    if ok:
        suffix = f" (lý do: {reason})" if reason else ""
        print(
            f"[verify-lint] DEV bypass token tiêu thụ — cho `{slug}` qua 1 lần{suffix}.",
            file=sys.stderr,
        )
        _exit_allow()

    action = converge_or_degrade(
        workspace, "verify_lint", f"{block_key}:{slug}",
        cap=3, crisp=True, has_bypass=True,
    )
    if action == "degrade":
        # Defensive fallback: with crisp=True + has_bypass=True converge_or_degrade
        # only ever returns "block"/"hold" (review round-1 confirmed "degrade" is
        # unreachable here) — kept so a future arg change can't deadlock: degrade =
        # warn-allow, self-terminating.
        print(
            f"[verify-lint] (warn) convergence degrade cho `{slug}` ({block_key}).",
            file=sys.stderr,
        )
        _exit_allow()
    if action == "hold":
        message += (
            "\n\n⚠️ Gate đã block liên tiếp cho trigger này. Nếu đây là chặn SAI, "
            "DEV override 1-lần: tạo `.agent-toolkit/.skip_verify_lint_next.json` "
            "(bất kỳ nội dung JSON; hết hạn 600s) rồi /verify lại — hoặc set "
            "enforce_mode `verify_lint: warn`."
        )
    _emit_block(message)


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
