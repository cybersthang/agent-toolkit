"""[meta-review] / [meta] exempt marker tests."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import (
    LONG_PAD, cleanup_workspace, make_workspace, run_evidence_audit, write_transcript,
)


PROBES = {
    "version": 1,
    "_defaults": {"pass_exempt_markers": ["[meta-review]", "[meta]"]},
    "probes": []
}


def _assistant(text=None, tools=None):
    blocks = list(tools or [])
    if text:
        blocks.append({"type": "text", "text": text})
    return {"role": "assistant", "message": {"content": blocks}}


def _user(text):
    return {"role": "user", "content": text}


class TestMetaReviewMarker(unittest.TestCase):

    def setUp(self):
        self.ws = make_workspace(PROBES)

    def tearDown(self):
        cleanup_workspace(self.ws)

    def _decide(self, messages):
        t = write_transcript(self.ws, messages)
        return run_evidence_audit(t, self.ws).get("decision", "allow")

    def test_M1_pass_claim_with_meta_review_marker_allows(self):
        self.assertEqual(self._decide([
            _user("đánh giá toolkit"),
            _assistant(
                tools=[{"type": "tool_use", "id": "r1", "name": "Read",
                        "input": {"file_path": "src/x.py"}}],
                text="[meta-review] Đánh giá: hook đã verified qua Read; tests pass cleanly khi kiểm engine. " + LONG_PAD,
            ),
        ]), "allow")

    def test_M2_pass_claim_with_meta_short_form_allows(self):
        self.assertEqual(self._decide([
            _user("review"),
            _assistant(text="[meta] Implementation done from a design perspective, verified by reading source. " + LONG_PAD),
        ]), "allow")

    def test_M3_pass_claim_without_marker_still_blocks(self):
        self.assertEqual(self._decide([
            _user("implement xong"),
            _assistant(text="Tests pass và implementation done trên feature mới. " + LONG_PAD),
        ]), "block")

    def test_M4_generic_claim_with_meta_review_allows(self):
        self.assertEqual(self._decide([
            _user("review hook"),
            _assistant(text="[meta-review] Hook này CHẬM khi parse transcript dài; root cause là regex non-anchored. Module logging THIẾU rate limiter. " + LONG_PAD),
        ]), "allow")

    def test_M5_action_ghost_with_meta_review_still_blocks(self):
        # Progress checks NOT exempted by meta-review marker.
        self.assertEqual(self._decide([
            _user("fix hook"),
            _assistant(text="[meta-review] Mình đã thêm code mới vào hook để fix bug rate-limiter. " + LONG_PAD),
        ]), "block")

    def test_M6_action_ghost_with_both_bypasses_allows(self):
        self.assertEqual(self._decide([
            _user("fix hook"),
            _assistant(text="[meta-review] Mình đã thêm code mới vào hook. progress-skip: action_ghost meta context. " + LONG_PAD),
        ]), "allow")


if __name__ == "__main__":
    unittest.main()
