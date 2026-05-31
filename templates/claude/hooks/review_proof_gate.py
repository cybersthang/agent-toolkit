#!/usr/bin/env python
"""Stop hook — verify that `/review` finding proofs are REAL (v0.34 F3.1 / T7).

`/review` emits, per finding, a line `**Proof**: \`path:line\` cite + tool used`.
The evidence-audit hook already rejects a finding with NO proof line, but it does
not check that the cited `path:line` is real — an agent can hallucinate a plausible
`src/auth/login.py:42` it never inspected. This gate closes that gap.

Detection: the response carries the `/review` finding contract — a final count-table
(`| Severity | Count |`) OR ≥1 `**Severity**:` line — AND ≥1 `**Proof**:` line.
Otherwise silent (fail-open).

A proof is FABRICATED iff its cited FILE path (cites that aren't file paths — e.g.
`mcp__*` tool-name / symbol / URL proofs, which review.md explicitly sanctions — are
skipped) was NEITHER touched by a tool THIS turn NOR exists on disk. "Touched" is
un-forgeable: the cited path must appear in (a) a harness-written tool_RESULT (e.g.
a Grep result lists real `path:line`s) or (b) the file_path/notebook_path of a
READ/EDIT tool_use (the harness ran the tool on that exact file). Agent-controlled
SEARCH inputs (Grep `pattern`, Bash `command`, `glob`) are EXCLUDED — they let an
agent name a fake path without reading real content. Matching is full-path substring
(NOT bare basename), so a same-named file elsewhere does not satisfy a proof. Only
"neither inspected nor real" is flagged (high-precision, low false-positive per R5.3).

Block-CAPABLE @ WARN: default warn (advisory stderr); blocks only under
`enforce_mode review_proof_gate=block` / `AGENT_TOOLKIT_STRICT=1`, via the shared
convergence-cap (HOLDS after cap — crisp + a reachable bypass — never deadlocks).
The streak key is per fabricated-path-set so one review's streak can't bleed into an
unrelated review. Single-shot bypass: `review-proof: skip <reason>` in the response.

Bounded: `stop_hook_active` short-circuits re-entrance; `run_main_safe` keeps it
fail-open on crash.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, find_workspace_root, run_main_safe,
    get_enforce_mode, converge_or_degrade)

wrap_utf8_stdio()


# `/review` signatures — the final count-table header OR a per-finding severity line.
_COUNT_TABLE_RE = re.compile(r"(?im)^\s*\|\s*Severity\s*\|\s*Count\s*\|")
_SEVERITY_RE = re.compile(r"(?im)^\s*\*\*Severity\*\*\s*:")
# Per-finding proof line: `**Proof**: \`path:line\` …` — capture the first backtick.
_PROOF_RE = re.compile(r"(?im)^\s*\*\*Proof\*\*\s*:\s*`([^`]+)`")
# Single-shot bypass marker in the response.
_BYPASS_RE = re.compile(r"review-proof\s*:\s*skip\b", re.IGNORECASE)
# A cite is a FILE-path claim iff it has a path separator or a known source ext.
_SRC_EXT_RE = re.compile(
    r"\.(py|js|ts|tsx|jsx|xml|json|ya?ml|md|txt|html?|css|scss|sql|sh|bash|go|rs|"
    r"java|rb|c|cpp|cc|h|hpp|php|vue|toml|ini|cfg|svg|tf)$", re.IGNORECASE)
# A tool's agent-supplied target file_path counts as "inspected" — but ONLY when the
# harness returned a NON-ERROR result (a failed Read of a nonexistent file must not
# forge a touch — review round-2 HIGH). Grep/Glob instead contribute their RESULT
# text (which lists the real matching paths); their agent-controlled pattern/glob is
# never trusted.
_PATH_INPUT_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}
_PATH_RESULT_TOOLS = {"Grep", "Glob"}


def _exit_allow() -> None:
    sys.exit(0)


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _last_assistant_text(messages: List[Dict[str, Any]]) -> str:
    for rec in reversed(messages):
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        if (msg.get("role") or rec.get("type")) != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _tool_results_by_id(records: List[Dict[str, Any]]) -> Dict[str, tuple]:
    """Map tool_use_id → (result_text, is_error). The harness sets `is_error` on a
    failed tool (e.g. Read of a nonexistent file); an errored result must not credit
    a touch."""
    out: Dict[str, tuple] = {}
    for rec in records:
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        # tool_result records are USER-role; one inside an assistant message is
        # malformed/forged → ignore (mirrors verify_lint hardening).
        if (msg.get("role") or rec.get("type")) != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "tool_result":
                c = blk.get("content")
                txt = c if isinstance(c, str) else (
                    " ".join(b.get("text", "") for b in c
                             if isinstance(b, dict) and b.get("type") == "text")
                    if isinstance(c, list) else "")
                tid = blk.get("tool_use_id")
                if tid:
                    out[tid] = (txt or "", bool(blk.get("is_error")))
    return out


def _turn_records(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Records since the last REAL user prompt (text content). A tool_result is a
    user-role message but NOT a turn boundary, so tool_use→result→report stays in
    one turn."""
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


def _turn_evidence(messages: List[Dict[str, Any]]) -> str:
    """The harness-confirmed record of what the agent inspected THIS turn. A
    Read/Edit/Write target file_path counts ONLY when its tool_result is present and
    NOT an error (so a failed Read of a nonexistent file can't forge a touch —
    review round-2 HIGH); Grep/Glob contribute their RESULT text (the real matching
    paths), never their agent-controlled pattern/glob. Everything else is ignored."""
    turn = _turn_records(messages)
    results = _tool_results_by_id(turn)
    parts: List[str] = []
    for rec in turn:
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for blk in content:
            if not (isinstance(blk, dict) and blk.get("type") == "tool_use"):
                continue
            name = blk.get("name") or ""
            res = results.get(blk.get("id") or "")
            if res is None or res[1]:          # missing or errored result → no credit
                continue
            if name in _PATH_INPUT_TOOLS:
                inp = blk.get("input") or {}
                if isinstance(inp, dict):
                    for key in ("file_path", "notebook_path"):
                        val = inp.get(key)
                        if isinstance(val, str):
                            parts.append(val)
            elif name in _PATH_RESULT_TOOLS:
                parts.append(res[0])
    return "\n".join(parts).replace("\\", "/")


def _proof_path(cite: str) -> str:
    """Strip a trailing line locator (`:N`, `:N:M` line:col, `:N-M` range, `:N,M`)
    from a `path:line` cite → the bare path."""
    cite = cite.strip().replace("\\", "/")
    m = re.match(r"^(.+?)(?::\d+(?:[:,-]\d+)?)?$", cite)
    return (m.group(1) if m else cite).strip()


def _looks_like_path(p: str) -> bool:
    """True iff the cite is a FILE-path claim (has a separator or a source ext) and
    is not an mcp tool-name or a URL — review.md sanctions `mcp__*`/symbol/URL proofs
    which are NOT files and must NOT be treated as fabricated file paths."""
    if not p or p.startswith("mcp__") or "://" in p:
        return False
    return ("/" in p) or bool(_SRC_EXT_RE.search(p))


def _path_in_evidence(path: str, evidence: str) -> bool:
    """Path-boundary substring match: `path` must be flanked by start/end or a
    delimiter, so a short cite (`a.py`) does NOT match a longer unrelated path
    (`src/data.py`) — review round-2 substring false-negative fix."""
    pat = r"(?:^|[\s\"'`(\[/=,:])" + re.escape(path) + r"(?:$|[\s\"'`:),\];=])"
    return re.search(pat, evidence, re.MULTILINE) is not None


def _is_fabricated(path: str, evidence: str, workspace: Path) -> bool:
    """Fabricated iff the path was NEITHER touched this turn (path-boundary match in
    the harness-confirmed evidence) NOR exists on disk. Fail-SAFE toward
    NOT-fabricated on any error — a false block on a real finding is the costly
    mistake to avoid (R5.3)."""
    if not path:
        return False
    if _path_in_evidence(path, evidence):
        return False
    try:
        if (workspace / path).exists():
            return False
    except OSError:
        return False
    return True


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_allow()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_allow()
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_allow()
    if envelope.get("stop_hook_active"):
        _exit_allow()

    transcript_path = envelope.get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        _exit_allow()
    messages = read_jsonl_transcript(Path(transcript_path))
    if not messages:
        _exit_allow()

    text = _last_assistant_text(messages)
    # Fire only on the /review finding contract (count-table OR a severity line).
    if not text or not (_COUNT_TABLE_RE.search(text) or _SEVERITY_RE.search(text)):
        _exit_allow()
    # Parse proof cites; keep only FILE-path claims (skip mcp/symbol/URL proofs).
    proofs = sorted({p for c in _PROOF_RE.findall(text)
                     if _looks_like_path(p := _proof_path(c))})
    if not proofs:
        _exit_allow()                      # nothing file-path-shaped to verify

    workspace_str = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = find_workspace_root(Path(workspace_str)) or Path(workspace_str).resolve()

    evidence = _turn_evidence(messages)
    fabricated = sorted(p for p in proofs if _is_fabricated(p, evidence, workspace))
    if not fabricated:
        _exit_allow()

    listing = ", ".join(f"`{p}`" for p in fabricated[:8])
    base_msg = (
        f"[review-proof-gate] {len(fabricated)} finding-proof không xác minh được "
        f"(path không được Read/Grep touch turn này VÀ không tồn tại trên disk): "
        f"{listing}. Mỗi `**Proof**: `path:line`` phải trỏ tới file có thật mà anh "
        f"đã Read/Grep trong CHÍNH turn này — đọc lại file rồi cite, hoặc bỏ finding. "
        f"(Proof dạng `mcp__*` / symbol / URL không bị check.) Bypass 1-lần nếu chặn "
        f"SAI: thêm `review-proof: skip <lý do>` vào response."
    )

    # warn-first (R5.3): default mode only warns; block under enforce_mode / strict.
    if get_enforce_mode(workspace, "review_proof_gate", default="warn") != "block":
        sys.stderr.write(base_msg + "\n")
        _exit_allow()

    if _BYPASS_RE.search(text):
        sys.stderr.write("[review-proof-gate] bypass `review-proof: skip` honored.\n")
        _exit_allow()

    # Per fabricated-path-set streak key — one review's streak can't bleed into an
    # unrelated review (different fabricated set → different key).
    key = "fab:" + hashlib.sha1("|".join(fabricated).encode("utf-8")).hexdigest()[:12]
    action = converge_or_degrade(
        workspace, "review_proof_gate", key, cap=3, crisp=True, has_bypass=True)
    if action == "degrade":
        sys.stderr.write(base_msg + "\n[review-proof-gate] (degrade→warn)\n")
        _exit_allow()
    if action == "hold":
        base_msg += ("\n\n⚠️ Đã block liên tiếp cho cùng set path. Nếu các path NÀY "
                     "thật sự đúng, dùng `review-proof: skip <lý do>` để override, hoặc "
                     "set enforce_mode `review_proof_gate: warn`.")
    _emit_block(base_msg)


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
