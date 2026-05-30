"""Malformed-envelope contract for the Stop-event hooks (CI suite).

Regression for `json.loads("null") -> None -> envelope.get(...)`. Under
run_main_safe's default (fail-CLOSED since v0.20.0) an uncaught exception
exits 1 and BLOCKS the response — so a non-dict envelope (`null`, a list, a
bare string/number) would have hard-blocked the agent's Stop. Each Stop hook
must instead fail OPEN: exit 0, no traceback, no block decision.

Runs against the shipped source hooks under templates/claude/hooks/.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
PY = os.environ.get("PYTHON_BIN", sys.executable)

# Stop hooks that parse the raw envelope and call `.get()` on it.
STOP_HOOKS = [
    "evidence_audit.py",
    "gap_completeness_gate.py",
    "scope_completeness_gate.py",
]

# Valid JSON that is NOT a dict — each would crash `.get()` pre-fix.
NON_DICT_ENVELOPES = ["null", "[1, 2, 3]", '"a bare string"', "42", "true"]
EMPTY_ENVELOPES = ["", "   ", "\n"]


def _run(hook: str, raw: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Don't let the kill-switch / recursion guard mask the parse path.
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    env.pop("stop_hook_active", None)
    return subprocess.run(
        [PY, str(HOOKS_DIR / hook)],
        input=raw,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, env=env,
    )


@pytest.mark.parametrize("hook", STOP_HOOKS)
@pytest.mark.parametrize("raw", NON_DICT_ENVELOPES)
def test_non_dict_envelope_fails_open(hook: str, raw: str):
    p = _run(hook, raw)
    # Must NOT crash (fail-CLOSED default would exit 1 = block the Stop).
    assert p.returncode == 0, (
        f"{hook} on {raw!r}: rc={p.returncode}\n{p.stderr}"
    )
    assert "Traceback" not in (p.stderr or ""), (
        f"{hook} raised on {raw!r}:\n{p.stderr}"
    )
    # Must not emit a block decision.
    assert '"block"' not in (p.stdout or "")


@pytest.mark.parametrize("hook", STOP_HOOKS)
@pytest.mark.parametrize("raw", EMPTY_ENVELOPES)
def test_empty_envelope_fails_open(hook: str, raw: str):
    p = _run(hook, raw)
    assert p.returncode == 0, f"{hook} on {raw!r}: rc={p.returncode}\n{p.stderr}"
    assert "Traceback" not in (p.stderr or "")
