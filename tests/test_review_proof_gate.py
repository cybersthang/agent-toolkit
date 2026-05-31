"""v0.34 T7 (F3.1) — review_proof_gate: /review finding-proofs must be real.

Subprocess invocation (no import side-effects; UTF-8 in/out for Windows). The gate
fires only on a /review count-table; a proof whose `path:line` was neither touched
by a tool this turn NOR exists on disk is fabricated → warn (default) / block (strict).

Acceptance eval: ev3-fake-proof-blocks.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "review_proof_gate.py"
PYTHON = sys.executable


def _mk_ws(tmp: Path) -> Path:
    ws = tmp / "proj"
    (ws / ".agent-toolkit" / "specs").mkdir(parents=True, exist_ok=True)
    return ws


def _review(proof_path: str, bypass: bool = False) -> str:
    extra = "\n\nreview-proof: skip not-actually-fake" if bypass else ""
    return (
        "## Review — auth module\n\n"
        "### F1 — a finding\n"
        "**Severity**: MEDIUM\n"
        f"**Proof**: `{proof_path}` cite + tool used (`Read`)\n"
        "**Fix sketch**: do the thing\n\n"
        "| Severity | Count | Delta from REV-1 lock |\n"
        "|----------|-------|-----------------------|\n"
        "| BLOCKER  | 0     | =                     |\n"
        "| MEDIUM   | 1     | +1                    |\n"
        "| LOW      | 0     | =                     |\n"
        + extra
    )


def _transcript(tmp: Path, report: str, touched=(), raw_tools=()) -> Path:
    recs = [{"type": "user", "message": {"role": "user",
             "content": [{"type": "text", "text": "/review auth"}]}}]
    for i, p in enumerate(touched):
        recs.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Read", "id": f"t{i}", "input": {"file_path": p}}]}})
        recs.append({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": f"<contents of {p}>"}]}})
    for j, item in enumerate(raw_tools):
        name, inp, result = item[0], item[1], item[2]
        is_err = item[3] if len(item) > 3 else False
        rid = f"r{j}"
        recs.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": name, "id": rid, "input": inp}]}})
        tr = {"type": "tool_result", "tool_use_id": rid, "content": result}
        if is_err:
            tr["is_error"] = True
        recs.append({"type": "user", "message": {"role": "user", "content": [tr]}})
    recs.append({"type": "assistant", "message": {"role": "assistant",
                 "content": [{"type": "text", "text": report}]}})
    tp = tmp / "t.jsonl"
    tp.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    return tp


def _run(ws: Path, tp: Path, strict: bool = True):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    if strict:
        env["AGENT_TOOLKIT_STRICT"] = "1"
    else:
        env.pop("AGENT_TOOLKIT_STRICT", None)
    envelope = {"transcript_path": str(tp), "cwd": str(ws), "stop_hook_active": False}
    p = subprocess.run([PYTHON, str(HOOK)], input=json.dumps(envelope).encode("utf-8"),
                       capture_output=True, timeout=15, env=env)
    return (p.returncode, p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def test_fake_proof_blocks_strict(tmp_path):
    # ev3: path neither touched this turn nor on disk → fabricated → block.
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/ghost.py:42"))
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision": "block"' in out, (out, err)
    assert "ghost.py" in out


def test_real_proof_touched_allows_strict(tmp_path):
    # path appears in a Read tool_use input this turn → real → allow.
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/touched.py:5"), touched=["src/touched.py"])
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision"' not in out, (out, err)


def test_real_proof_exists_on_disk_allows_strict(tmp_path):
    # path exists on disk (known from a prior turn, not touched now) → not fabricated.
    ws = _mk_ws(tmp_path)
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "real.py").write_text("x = 1\n", encoding="utf-8")
    tp = _transcript(tmp_path, _review("src/real.py:1"))
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision"' not in out, (out, err)


def test_fake_proof_warns_default(tmp_path):
    # warn-first (R5.3): default mode never blocks, surfaces a stderr warning.
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/ghost.py:42"))
    rc, out, err = _run(ws, tp, strict=False)
    assert '"decision"' not in out, out
    assert "review-proof-gate" in err


def test_no_count_table_is_silent(tmp_path):
    # A response with a Proof line but NO /review count-table is not a review → silent.
    ws = _mk_ws(tmp_path)
    report = ("Some prose.\n**Proof**: `src/ghost.py:42` cite + tool used (`Read`)\n"
              "No table here.\n")
    tp = _transcript(tmp_path, report)
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision"' not in out, out


def test_bypass_marker_allows_strict(tmp_path):
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/ghost.py:42", bypass=True))
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision"' not in out, (out, err)


def test_no_proofs_is_silent(tmp_path):
    # count-table present but no `**Proof**:` lines → nothing to verify → silent.
    ws = _mk_ws(tmp_path)
    report = ("## Review\n\n| Severity | Count | Delta |\n|---|---|---|\n"
              "| BLOCKER | 0 | = |\n| MEDIUM | 0 | = |\n| LOW | 0 | = |\n")
    tp = _transcript(tmp_path, report)
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision"' not in out, out


def test_range_cite_real_file_allows_strict(tmp_path):
    # review round-1 HIGH: a line-RANGE cite `path:10-20` on a real file must NOT be
    # flagged (the range suffix is stripped before the existence check).
    ws = _mk_ws(tmp_path)
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    tp = _transcript(tmp_path, _review("src/foo.py:10-20"))
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision"' not in out, (out, err)


def test_mcp_proof_not_treated_as_path_allows_strict(tmp_path):
    # review round-1 HIGH: review.md sanctions `mcp__*` proofs — not a file path,
    # must NOT be flagged as fabricated.
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("mcp__postgres__query_readonly"))
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision"' not in out, (out, err)


def test_grep_pattern_input_does_not_forge_touch_strict(tmp_path):
    # review round-1 HIGH: naming a fake path in a Grep PATTERN (agent-controlled
    # input) must NOT count as touching it → still blocks.
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/ghost.py:42"),
                     raw_tools=[("Grep", {"pattern": "src/ghost.py"}, "no matches found")])
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision": "block"' in out, (out, err)


def test_basename_collision_still_blocks_strict(tmp_path):
    # review round-1 HIGH: reading an UNRELATED same-basename file must NOT satisfy a
    # proof for a different path (full-path match, not basename).
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/auth/login.py:999"),
                     touched=["tests/login.py"])
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision": "block"' in out, (out, err)


def test_forge_via_failed_read_still_blocks_strict(tmp_path):
    # review round-2 HIGH: a Read of a NONEXISTENT file (errored result) must NOT
    # forge a touch — the fake proof still blocks.
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/ghost.py:42"),
                     raw_tools=[("Read", {"file_path": "src/ghost.py"},
                                 "File does not exist.", True)])  # is_error=True
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision": "block"' in out, (out, err)


def test_substring_cite_does_not_satisfy_strict(tmp_path):
    # review round-2 NEW: a short cite `a.py` that is only a SUBSTRING of a real
    # touched path `src/data.py` must NOT be credited (path-boundary match).
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("a.py:3"), touched=["src/data.py"])
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision": "block"' in out, (out, err)


def test_severity_trigger_without_count_table_blocks_strict(tmp_path):
    # review round-1 MED: the gate fires on the per-finding `**Severity**:` contract
    # even when the count-table is reformatted/absent (trigger not table-only).
    ws = _mk_ws(tmp_path)
    report = ("### F1 — issue\n**Severity**: BLOCKER\n"
              "**Proof**: `src/ghost.py:42` cite + tool used (`Read`)\n"
              "**Fix sketch**: x\n")  # no count-table at all
    tp = _transcript(tmp_path, report)
    rc, out, err = _run(ws, tp, strict=True)
    assert '"decision": "block"' in out, (out, err)


def test_convergence_hold_appends_escape_hint_strict(tmp_path):
    # crisp + has_bypass → after cap=3 the block HOLDS (still blocks) with the
    # override hint → provably no deadlock.
    ws = _mk_ws(tmp_path)
    tp = _transcript(tmp_path, _review("src/ghost.py:42"))
    outs = [_run(ws, tp, strict=True)[1] for _ in range(3)]
    assert '"decision": "block"' in outs[0]
    assert "Đã block liên tiếp" not in outs[0]   # streak 1: base block, no hold hint
    assert '"decision": "block"' in outs[2]        # streak 3: still blocks (HOLD)
    assert "Đã block liên tiếp" in outs[2]         # ...with the hold/escape hint
