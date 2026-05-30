"""Real-data fingerprint enforcement tests (probe.evidence.required_result_fingerprint)."""
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import (
    LONG_PAD, cleanup_workspace, make_workspace, run_evidence_audit, write_transcript,
)


def _make_probe(expected_fp: str) -> dict:
    return {
        "version": 1,
        "_defaults": {
            "pass_claim_regex": r"\b(verified|passed|works\s*correctly)\b",
            "required_tool_prefixes": ["mcp__realdata_test__"],
        },
        "probes": [{
            "id": "count-must-match",
            "description": "partner count must equal 42",
            "applies_when": {"claim_regex": r"partner.*count.*works|count.*verified"},
            "evidence": {
                "required_tools": ["mcp__realdata_test__eval_orm_expression"],
                "min_calls": 1,
                "required_result_fingerprint": expected_fp,
            },
            "severity": "blocker",
            "rationale": "test fingerprint enforcement",
        }]
    }


def _assistant(text=None, tools=None):
    blocks = list(tools or [])
    if text:
        blocks.append({"type": "text", "text": text})
    return {"role": "assistant", "message": {"content": blocks}}


def _tool_result(tool_use_id, content):
    return {"role": "user", "content": [{"type": "tool_result",
            "tool_use_id": tool_use_id, "content": content}]}


class TestFingerprint(unittest.TestCase):

    def _decide(self, ws, messages):
        t = write_transcript(ws, messages)
        return run_evidence_audit(t, ws).get("decision", "allow")

    def test_01_matching_fingerprint_allows(self):
        expected_text = "42"
        expected_fp = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()
        ws = make_workspace(_make_probe(expected_fp))
        try:
            d = self._decide(ws, [
                {"role": "user", "content": "verify count"},
                _assistant(
                    tools=[{"type": "tool_use", "id": "m1",
                            "name": "mcp__realdata_test__eval_orm_expression",
                            "input": {"expression": "len(env['res.partner'].search([]))"}}],
                ),
                _tool_result("m1", expected_text),
                _assistant(text="partner count works correctly. " + LONG_PAD),
            ])
            self.assertEqual(d, "allow")
        finally:
            cleanup_workspace(ws)

    def test_02_wrong_fingerprint_blocks(self):
        # Agent calls MCP with dummy 1+1 → result fingerprint won't match.
        expected_text = "42"
        expected_fp = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()
        ws = make_workspace(_make_probe(expected_fp))
        try:
            d = self._decide(ws, [
                {"role": "user", "content": "verify count"},
                _assistant(
                    tools=[{"type": "tool_use", "id": "m1",
                            "name": "mcp__realdata_test__eval_orm_expression",
                            "input": {"expression": "1+1"}}],
                ),
                _tool_result("m1", "2"),  # dummy result, not 42
                _assistant(text="partner count works correctly. " + LONG_PAD),
            ])
            self.assertEqual(d, "block")
        finally:
            cleanup_workspace(ws)

    def test_03_no_fingerprint_required_passes_with_tool_call(self):
        # When required_result_fingerprint is absent, fingerprint check skipped.
        probe = _make_probe("dummy")
        del probe["probes"][0]["evidence"]["required_result_fingerprint"]
        ws = make_workspace(probe)
        try:
            d = self._decide(ws, [
                {"role": "user", "content": "verify count"},
                _assistant(
                    tools=[{"type": "tool_use", "id": "m1",
                            "name": "mcp__realdata_test__eval_orm_expression",
                            "input": {"expression": "1+1"}}],
                ),
                _tool_result("m1", "2"),
                _assistant(text="partner count works correctly. " + LONG_PAD),
            ])
            self.assertEqual(d, "allow")
        finally:
            cleanup_workspace(ws)


if __name__ == "__main__":
    unittest.main()
