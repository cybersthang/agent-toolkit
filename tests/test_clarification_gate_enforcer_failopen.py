"""R8 regression: clarification_gate_enforcer must FAIL OPEN when the
response text is unreadable/empty (e.g. a tool-call turn that has not yet
flushed assistant text) instead of false-blocking every tool-call turn.

Mirrors tests/test_gap_completeness_gate.py's subprocess `_run` pattern:
feed a real Stop envelope (transcript_path + cwd) over stdin.

Run: pytest tests/test_clarification_gate_enforcer_failopen.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "clarification_gate_enforcer.py"
PY = os.environ.get("PYTHON_BIN", sys.executable)

LAST_INTENT_REL = ".agent-toolkit/.last_intent_suggested.json"


def _run_transcript(workspace: Path, transcript: Path,
                    extra_env: dict = None) -> subprocess.CompletedProcess:
    """Run the enforcer with a real Stop envelope shape — transcript_path +
    cwd over stdin (no inline `response` field)."""
    env = os.environ.copy()
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    env.pop("stop_hook_active", None)
    if extra_env:
        env.update(extra_env)
    envelope = {"transcript_path": str(transcript), "cwd": str(workspace)}
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, env=env, cwd=str(workspace),
    )


def _seed_intent(workspace: Path) -> Path:
    """Write `.last_intent_suggested.json` so `_last_intent_relevant` is True:
    fresh ts + a `skills` list containing `clarification-gate`."""
    path = workspace / LAST_INTENT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "ts": int(time.time()),
        "skills": ["clarification-gate"],
    }), encoding="utf-8")
    return path


def _write_tool_only_transcript(workspace: Path) -> Path:
    """Current turn has NO flushed assistant text: a user prompt + an
    assistant message whose content is ONLY a tool_use block (no text)."""
    path = workspace / "transcript.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user",
                                     "content": "do the thing"}},
        {"type": "assistant", "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu1", "name": "Bash",
                 "input": {"command": "echo hi"}},
            ],
        }},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n",
                    encoding="utf-8")
    return path


def _write_text_missing_markers_transcript(workspace: Path) -> Path:
    """Last assistant message HAS text but is MISSING the 4 markers."""
    path = workspace / "transcript.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user",
                                     "content": "do the thing"}},
        {"type": "assistant", "message": {
            "role": "assistant",
            "content": [{"type": "text",
                         "text": "Sure, here is a plain answer with no markers."}],
        }},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n",
                    encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


class TestR8FailOpen:
    """The enforce preconditions are met (intent relevant, no autonomy, no
    skip token) yet the response is unreadable → must fail OPEN (exit 0, no
    block decision)."""

    def test_tool_only_turn_fails_open(self, workspace):
        _seed_intent(workspace)
        tr = _write_tool_only_transcript(workspace)
        r = _run_transcript(workspace, tr)
        assert r.returncode == 0, (
            f"unreadable/empty response must fail OPEN (R8), got rc="
            f"{r.returncode}, stderr={r.stderr}"
        )
        assert "block" not in r.stderr.lower(), (
            f"must NOT emit a block decision on a tool-only turn; stderr={r.stderr}"
        )

    def test_text_missing_markers_blocks(self, workspace):
        """Control — when the response IS readable but missing the 4 markers
        the enforcer still BLOCKS (deny/block). Confirms the fail-open fix
        did not neuter the enforcer."""
        _seed_intent(workspace)
        tr = _write_text_missing_markers_transcript(workspace)
        r = _run_transcript(workspace, tr)
        assert r.returncode == 2, (
            f"readable response missing markers must BLOCK, got rc="
            f"{r.returncode}, stderr={r.stderr}"
        )
        assert "block" in r.stderr.lower()
        assert "missing markers" in r.stderr.lower()
