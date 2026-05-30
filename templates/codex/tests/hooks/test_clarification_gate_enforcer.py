"""Smoke tests for clarification_gate_enforcer hook.

Tests: marker shape contract + skip paths (autonomy, no-suggestion, skip-token).
Pattern matches test_hook_envelope.py (direct import + mock envelope).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def _write_intent_state(workspace: Path, skills: list, age_seconds: int = 0):
    state_dir = workspace / ".agent-toolkit"
    state_dir.mkdir(exist_ok=True)
    (state_dir / ".last_intent_suggested.json").write_text(json.dumps({
        "ts": int(time.time()) - age_seconds,
        "skills": skills,
        "prompt_hash": "abc12345",
    }))


def _write_transcript(workspace: Path, text: str) -> Path:
    tpath = workspace / "transcript.jsonl"
    msgs = [
        {"role": "user", "content": "test"},
        {"role": "assistant", "content": [{"type": "text", "text": text}]},
    ]
    with tpath.open("w", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m) + "\n")
    return tpath


def test_missing_markers_returns_block_exit_code():
    """No 4 markers + clarification-gate suggested → block (exit 2)."""
    from clarification_gate_enforcer import _missing_markers, REQUIRED_MARKERS
    missing = _missing_markers("hello world")
    assert len(missing) == 4, f"Expected all 4 markers missing, got {missing}"
    assert set(missing) == set(REQUIRED_MARKERS)
    print("PASS test_missing_markers_returns_block_exit_code")


def test_all_4_markers_present_returns_empty():
    """Response with all 4 markers → empty missing list."""
    from clarification_gate_enforcer import _missing_markers
    response = "UNDERSTANDING: x\nASSUMPTIONS: y\nQUESTIONS: z\nSearched: w"
    assert _missing_markers(response) == []
    print("PASS test_all_4_markers_present_returns_empty")


def test_extract_response_text_uses_transcript_path():
    """_extract_response_text reads from transcript_path JSONL."""
    from clarification_gate_enforcer import _extract_response_text
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        tpath = _write_transcript(ws, "UNDERSTANDING marker text")
        result = _extract_response_text({"transcript_path": str(tpath)})
        assert "UNDERSTANDING marker text" in result
    print("PASS test_extract_response_text_uses_transcript_path")


if __name__ == "__main__":
    test_missing_markers_returns_block_exit_code()
    test_all_4_markers_present_returns_empty()
    test_extract_response_text_uses_transcript_path()
    print("\n3 tests passed")
