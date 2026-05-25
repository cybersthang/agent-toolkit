"""Integration tests for Stop hook envelope reading pattern.

Verifies that clarification_gate_enforcer._extract_response_text() correctly
reads assistant text from transcript_path (JSONL), NOT from inline
envelope keys (response / response_text / etc.) which Claude Code does NOT
populate in Stop hook envelopes.

Run: python templates/codex/tests/test_hook_envelope.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Make hook importable.
HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def _write_jsonl_transcript(messages: list, tmp_dir: Path) -> Path:
    """Write a JSONL transcript file in Claude Code format."""
    tpath = tmp_dir / "transcript.jsonl"
    with tpath.open("w", encoding="utf-8") as fh:
        for msg in messages:
            fh.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return tpath


def test_extract_response_text_from_transcript():
    """_extract_response_text reads from transcript_path JSONL, not envelope keys."""
    from clarification_gate_enforcer import _extract_response_text

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        assistant_text = "UNDERSTANDING: test\nASSUMPTIONS: none\nQUESTIONS: none\nSearched: Grep"
        messages = [
            {"role": "user", "content": "implement something"},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": assistant_text}],
            },
        ]
        tpath = _write_jsonl_transcript(messages, tmp_dir)

        envelope = {"transcript_path": str(tpath), "cwd": str(tmp_dir)}
        result = _extract_response_text(envelope)
        assert assistant_text in result, (
            f"Expected assistant text in result. Got: {result!r}"
        )
    print("PASS test_extract_response_text_from_transcript")


def test_extract_response_text_no_transcript_path():
    """_extract_response_text returns '' when transcript_path is absent."""
    from clarification_gate_enforcer import _extract_response_text

    envelope = {}
    result = _extract_response_text(envelope)
    assert result == "", f"Expected empty string. Got: {result!r}"
    print("PASS test_extract_response_text_no_transcript_path")


def test_extract_response_text_missing_file():
    """_extract_response_text returns '' when transcript file does not exist."""
    from clarification_gate_enforcer import _extract_response_text

    envelope = {"transcript_path": "/nonexistent/path/transcript.jsonl"}
    result = _extract_response_text(envelope)
    assert result == "", f"Expected empty string. Got: {result!r}"
    print("PASS test_extract_response_text_missing_file")


def test_inline_envelope_keys_ignored():
    """Inline envelope keys (response / response_text) are NOT used — transcript only."""
    from clarification_gate_enforcer import _extract_response_text

    # Provide inline keys but no transcript_path — should return ""
    envelope = {
        "response": "UNDERSTANDING: injected",
        "response_text": "ASSUMPTIONS: injected",
    }
    result = _extract_response_text(envelope)
    assert result == "", (
        "Inline envelope keys must be ignored. "
        f"Got: {result!r}"
    )
    print("PASS test_inline_envelope_keys_ignored")


if __name__ == "__main__":
    test_extract_response_text_from_transcript()
    test_extract_response_text_no_transcript_path()
    test_extract_response_text_missing_file()
    test_inline_envelope_keys_ignored()
    print("\n4 tests passed")
