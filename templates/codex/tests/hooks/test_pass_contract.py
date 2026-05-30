"""PASS-claim contract — 10 cases proving the fail-CLOSED gate on
`tests pass / verified / done` requires an MCP evidence call."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import (
    LONG_PAD, cleanup_workspace, make_workspace, run_evidence_audit, write_transcript,
)


PROBES = {
    "version": 1,
    "_defaults": {
        "pass_claim_regex": r"\b(passed|tests?\s*pass|verified|đã\s*test|hoàn\s*thành|done)\b",
        "required_tool_prefixes": ["mcp__realdata_test__", "mcp__postgres__"]
    },
    "probes": [
        {
            "id": "load-views-blocking",
            "description": "load_views must block UI",
            "applies_when": {"claim_regex": r"load[_\s]views.*work|load_views.*pass|load_views.*đúng"},
            "evidence": {"required_tools": ["mcp__realdata_test__run_smoke_test"], "min_calls": 1},
            "falsification": {"type": "timing_perturb", "description": "inject time.sleep(2)"},
            "severity": "blocker",
            "rationale": "BLOCK cannot be inferred from code"
        }
    ]
}


def _assistant(text=None, tools=None):
    blocks = list(tools or [])
    if text:
        blocks.append({"type": "text", "text": text})
    return {"role": "assistant", "message": {"content": blocks}}


def _user(text):
    return {"role": "user", "content": text}


class TestPassClaimContract(unittest.TestCase):

    def setUp(self):
        self.ws = make_workspace(PROBES)

    def tearDown(self):
        cleanup_workspace(self.ws)

    def _decide(self, messages):
        t = write_transcript(self.ws, messages)
        return run_evidence_audit(t, self.ws).get("decision", "allow")

    def test_01_pass_no_mcp_blocks(self):
        self.assertEqual(self._decide([
            _user("implement xong chưa?"),
            _assistant(text="Tests pass, implementation done. " + LONG_PAD),
        ]), "block")

    def test_02_pass_with_realdata_mcp_allows(self):
        self.assertEqual(self._decide([
            _user("implement xong chưa?"),
            _assistant(
                tools=[{"type": "tool_use", "name": "mcp__realdata_test__run_module_test",
                        "input": {"module": "foo"}}],
                text="Tests pass, all green on real data. " + LONG_PAD,
            ),
        ]), "allow")

    def test_03_pass_with_only_read_blocks(self):
        self.assertEqual(self._decide([
            _user("verify đi"),
            _assistant(
                tools=[{"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/x"}}],
                text="Verified — implementation done. " + LONG_PAD,
            ),
        ]), "block")

    def test_04_probe_match_wrong_mcp_blocks(self):
        self.assertEqual(self._decide([
            _user("load_views có chạy đúng không?"),
            _assistant(
                tools=[{"type": "tool_use", "name": "mcp__realdata_test__eval_orm_expression",
                        "input": {"expr": "1+1"}}],
                text="load_views works correctly, the request blocks UI as expected. " + LONG_PAD,
            ),
        ]), "block")

    def test_05_probe_match_correct_mcp_allows(self):
        self.assertEqual(self._decide([
            _user("load_views có chạy đúng không?"),
            _assistant(
                tools=[{"type": "tool_use", "name": "mcp__realdata_test__run_smoke_test",
                        "input": {"module": "web"}}],
                text="load_views works correctly with sleep(2) injected, page load +2.0s confirmed. " + LONG_PAD,
            ),
        ]), "allow")

    def test_06_probe_skip_bypass_allows(self):
        self.assertEqual(self._decide([
            _user("implement xong chưa?"),
            _assistant(text="Tests pass. probe-skip: all DB staging is down, will verify later. " + LONG_PAD),
        ]), "allow")

    def test_07_pass_with_assumption_still_blocks(self):
        # PASS is incompatible with [assumption] — claim is factual.
        self.assertEqual(self._decide([
            _user("xong chưa"),
            _assistant(text="Tests pass [assumption]. Đã verify [assumption]. " + LONG_PAD),
        ]), "block")

    def test_08_short_pass_response_allows(self):
        self.assertEqual(self._decide([
            _user("?"),
            _assistant(text="Tests pass."),
        ]), "allow")

    def test_09_no_pass_no_probe_allows(self):
        self.assertEqual(self._decide([
            _user("đọc file"),
            _assistant(
                tools=[{"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/x"}}],
                text="Đây là nội dung file: function foo() returns x. Mô tả đơn giản, không claim gì cả. " + LONG_PAD,
            ),
        ]), "allow")

    def test_10_pass_with_postgres_mcp_allows(self):
        self.assertEqual(self._decide([
            _user("verify count"),
            _assistant(
                tools=[{"type": "tool_use", "name": "mcp__postgres__query_readonly",
                        "input": {"sql": "select count(*) from x"}}],
                text="Verified count matches expected, tests pass. " + LONG_PAD,
            ),
        ]), "allow")


if __name__ == "__main__":
    unittest.main()
