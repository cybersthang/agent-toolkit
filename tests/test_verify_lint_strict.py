"""v0.33 ① — verify_lint.py strict-mode hardening (F1.1 + F1.2-B).

Run the hook as a subprocess (no import → avoids wrap_utf8_stdio side-effects;
mirrors test_independent_review_gate.py). UTF-8 bytes in/out for Windows.

Acceptance evals:
  ev1-noevals-blocks : feature-scope spec with NO acceptance_evals + strict → block
  ev2-pass-needs-mcp : Verify Report PASS but NO real-data tool_use this turn → block
  happy              : PASS + a Bash tool_use this turn → allow
  default-unchanged  : no-evals in DEFAULT (non-strict) mode → allow (regression)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "verify_lint.py"
LINT = TOOLKIT_ROOT / "templates" / "codex" / "lint_verify_report.py"
PYTHON = sys.executable


def _mk_ws(tmp: Path, slug: str = "feat", evals=("us1-flag",)) -> Path:
    ws = tmp / "proj"
    spec_dir = ws / ".agent-toolkit" / "specs" / "main" / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    (ws / ".codex").mkdir(parents=True, exist_ok=True)
    shutil.copy(LINT, ws / ".codex" / "lint_verify_report.py")
    lines = ["---", f"slug: {slug}"]
    if evals:
        lines.append("acceptance_evals:")
        for e in evals:
            lines += [f"  - id: {e}", "    story: x", "    grader: data"]
    lines += ["---", "# spec body"]
    (spec_dir / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ws


def _transcript(tmp: Path, report_text: str, tool: str | None = None,
                cmd: str = "", result: str = "") -> Path:
    recs = [{"type": "user", "message": {"role": "user",
             "content": [{"type": "text", "text": "/verify feat"}]}}]
    if tool:
        recs.append({"type": "assistant", "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": tool, "id": "x",
                                  "input": {"command": cmd} if cmd else {}}]}})
        # harness-written tool_result (the agent cannot forge this record)
        if result:
            recs.append({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "x", "content": result}]}})
    recs.append({"type": "assistant", "message": {"role": "assistant",
                 "content": [{"type": "text", "text": report_text}]}})
    tp = tmp / "t.jsonl"
    tp.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    return tp


def _run_hook(ws: Path, tp: Path, strict: bool = True):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    if strict:
        env["AGENT_TOOLKIT_STRICT"] = "1"
    else:
        env.pop("AGENT_TOOLKIT_STRICT", None)
    envelope = {"transcript_path": str(tp), "cwd": str(ws), "stop_hook_active": False}
    p = subprocess.run([PYTHON, str(HOOK)], input=json.dumps(envelope).encode("utf-8"),
                       capture_output=True, timeout=15, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def test_ev1_noevals_blocks_strict(tmp_path):
    ws = _mk_ws(tmp_path, evals=())          # spec with NO acceptance_evals
    tp = _transcript(tmp_path, "## Verify Report — feat\n\nLooks good ✅ PASS.")
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision": "block"' in out, out
    assert "acceptance_evals" in out


def test_ev2_pass_without_realdata_tooluse_blocks_strict(tmp_path):
    ws = _mk_ws(tmp_path, evals=("us1-flag",))
    # eval covered WITH a verdict, PASS claimed — but NO Bash/mcp tool_use this turn.
    report = "## Verify Report — feat\n\n| eval | result |\n| us1-flag | ✅ PASS |\n"
    tp = _transcript(tmp_path, report, tool=None)
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision": "block"' in out, out
    assert "real-data probe" in out


_PASS_REPORT = "## Verify Report — feat\n\n| eval | result |\n| us1-flag | ✅ PASS |\n"


@pytest.mark.parametrize("cmd", [
    "echo hello",
    "echo pytest",                  # round-2: the word inside an echo must NOT count
    'echo "pytest passed"',
    "# pytest",                     # a comment mentioning pytest
    "cat pytest.ini",
    "grep -r pytest .",
    'sleep 0; echo "make test ok"',
    "make clean",                   # a non-test make target must NOT count
    "poetry run black .",           # F1.5: launcher + NON-test → unwrap → not a runner
])
def test_non_probe_bash_does_not_count_strict(tmp_path, cmd):
    # round-2 HIGH fix: probe detection is anchored to the executed program,
    # so merely MENTIONING a test word does not satisfy the real-data requirement.
    ws = _mk_ws(tmp_path, evals=("us1-flag",))
    tp = _transcript(tmp_path, _PASS_REPORT, tool="Bash", cmd=cmd)
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision": "block"' in out, (cmd, out)
    assert "real-data probe" in out


@pytest.mark.parametrize("cmd", [
    "pytest tests/",
    "python -m pytest tests/test_feat.py",
    "make test",
    "cd /repo && pytest -x",        # program after && is a real runner
    "odoo-bin -i mod --test-enable --stop-after-init",
    "poetry run pytest tests/",       # F1.5: launcher-wrapped real run counts
    "uv run pytest",
    "xvfb-run pytest tests/",
    "timeout 60 pytest tests/",
    "env PYTHONPATH=. pytest tests/",
])
def test_real_probe_bash_counts_strict(tmp_path, cmd):
    ws = _mk_ws(tmp_path, evals=("us1-flag",))
    # the run must show real test execution in its (harness-written) result
    tp = _transcript(tmp_path, _PASS_REPORT, tool="Bash", cmd=cmd,
                     result="===== 5 passed in 0.31s =====")
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision"' not in out, (cmd, out)      # allowed


def test_runner_with_no_test_output_blocks_strict(tmp_path):
    # round-3 HIGH: `pytest --version` invokes the runner but runs ZERO tests →
    # its result has no "N passed" → still blocks (the RESULT is inspected, not
    # just the command string). Un-forgeable: the agent can't fake the result.
    ws = _mk_ws(tmp_path, evals=("us1-flag",))
    tp = _transcript(tmp_path, _PASS_REPORT, tool="Bash", cmd="pytest --version",
                     result="pytest 8.3.0")
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision": "block"' in out, out


@pytest.mark.parametrize("result", [
    "===== 0 passed, 4 skipped in 0.03s =====",   # real runner, ZERO tests ran
    "collected 0 items\nno tests ran in 0.01s",
    "Linting check passed\nno tests ran",         # 'passed' log line, no count
    "Ran 0 tests in 0.000s\n\nOK",                # 0 tests
    "conftest: 1 passed-through fixture\nno tests ran in 0.01s",  # round-5 FU1: stray "1 passed" off-summary-line
    "collected 0 items\nrun: 7 passed-files scanned",            # round-5 FU2: "7 passed" not a summary
])
def test_runner_that_ran_zero_tests_blocks_strict(tmp_path, result):
    # round-4 MED fix: a real runner whose result shows NO executed test (0
    # passed / all-skipped / 'passed' log token) must NOT satisfy the gate.
    ws = _mk_ws(tmp_path, evals=("us1-flag",))
    tp = _transcript(tmp_path, _PASS_REPORT, tool="Bash", cmd="pytest tests/ -k nomatch",
                     result=result)
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision": "block"' in out, (result, out)


def test_mcp_realdata_probe_with_result_allows_strict(tmp_path):
    ws = _mk_ws(tmp_path, evals=("us1-flag",))
    tp = _transcript(tmp_path, _PASS_REPORT,
                     tool="mcp__realdata_test__run_module_test",
                     result="2 passed, 0 failed")
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision"' not in out, out


def test_mcp_noop_without_realdata_result_blocks_strict(tmp_path):
    # round-3 MED: a read-only / no-op mcp call (non-probe name, empty result)
    # no longer satisfies the proof requirement.
    ws = _mk_ws(tmp_path, evals=("us1-flag",))
    tp = _transcript(tmp_path, _PASS_REPORT, tool="mcp__misc__list_dbs", result="")
    rc, out = _run_hook(ws, tp, strict=True)
    assert '"decision": "block"' in out, out


def test_default_mode_noevals_allows(tmp_path):
    # Regression: in DEFAULT (non-strict) mode the no-evals case stays allow.
    ws = _mk_ws(tmp_path, evals=())
    tp = _transcript(tmp_path, "## Verify Report — feat\n\nLooks good ✅ PASS.")
    rc, out = _run_hook(ws, tp, strict=False)
    assert '"decision"' not in out, out
