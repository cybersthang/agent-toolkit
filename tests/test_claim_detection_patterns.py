"""Regression battery for the natural-language completion-claim detectors
(v0.23.1).

Background: the claim detectors in `_patterns.py` are the trigger for the
gap / scope completeness gates. If the trigger regex misses a phrasing, the
gate never fires for that phrasing and partial-done slips through silently.

A self-audit on 2026-05-27 found `DONE_FULL_CLAIM_RE` missed ~12/22 common
completion phrasings because an outer `\b(?:…)\b` wrapper killed the emoji
and trailing-punctuation branches. This file locks the recall/precision of
each detector so the regression cannot recur.

Run: pytest tests/test_claim_detection_patterns.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from _patterns import (  # noqa: E402
    DONE_FULL_CLAIM_RE, COMPLETION_RE, DONE_CLAIM_GAP_RE,
)


# Phrasings that DO assert "the whole thing is done" — the scope gate MUST
# fire on all of these (else partial-done slips through).
FULL_CLAIM_POSITIVES = [
    "Đã hoàn thành toàn bộ", "All done", "Implement done", "Everything complete",
    "Đã xong hết", "Sprint complete", "✅ Done", "làm full xong rồi",
    "Tất cả đã xong", "Done.", "Verified — 636 tests pass", "Hoàn tất rồi nhé",
    "Đã fix xong tất cả findings", "Mọi thứ đã ổn", "Tôi đã làm xong yêu cầu",
    "Finished implementing the feature", "Tất cả tasks đều pass", "Xong rồi",
    "Đã hoàn thành", "completed successfully", "fix hết rồi", "ready to merge",
]

# Mid-work / partial / negated phrasings — the scope gate must NOT fire.
FULL_CLAIM_NEGATIVES = [
    "Đang làm dở", "T1 passed, sang T2", "Còn 3 việc nữa", "Tôi sẽ làm tiếp",
    "Bước 1 xong, tiếp tục bước 2", "Chưa xong", "Let me continue with the next step",
    "Found a bug in the parser", "Phân tích cho thấy có 2 vấn đề", "Chưa hoàn thành",
]


class TestDoneFullClaimRecall:
    """us2 trigger — DONE_FULL_CLAIM_RE must catch every full-done phrasing."""

    def test_all_positives_match(self):
        misses = [p for p in FULL_CLAIM_POSITIVES if not DONE_FULL_CLAIM_RE.search(p)]
        assert not misses, f"DONE_FULL_CLAIM_RE missed completion phrasings: {misses}"

    def test_no_false_positives(self):
        fp = [p for p in FULL_CLAIM_NEGATIVES if DONE_FULL_CLAIM_RE.search(p)]
        assert not fp, f"DONE_FULL_CLAIM_RE false-matched non-claims: {fp}"

    def test_emoji_branch_lives(self):
        """The `\\b` wrapper bug (v0.23.0) killed this; lock it open."""
        assert DONE_FULL_CLAIM_RE.search("✅ Done")
        assert DONE_FULL_CLAIM_RE.search("✅ Hoàn thành")

    def test_punct_terminated_branch_lives(self):
        """`Done.` / `Verified —` were dead under the old wrapper."""
        assert DONE_FULL_CLAIM_RE.search("Done.")
        assert DONE_FULL_CLAIM_RE.search("Verified — all green")

    def test_negation_excluded(self):
        assert not DONE_FULL_CLAIM_RE.search("Chưa xong")
        assert not DONE_FULL_CLAIM_RE.search("Chưa hoàn thành")


class TestCompletionReNegationGuard:
    """COMPLETION_RE (post_edit_verify_gate / probe_coverage_gate trigger)
    must not read a negated claim as completion."""

    def test_negation_not_matched(self):
        assert not COMPLETION_RE.search("Chưa xong")
        assert not COMPLETION_RE.search("Chưa hoàn thành")

    def test_legit_claims_still_match(self):
        for p in ("done", "Đã xong", "hoàn thành", "ready to merge",
                  "completed", "verified"):
            assert COMPLETION_RE.search(p), f"COMPLETION_RE regressed on {p!r}"


class TestGapClaimIsIntentionallyNarrow:
    """DONE_CLAIM_GAP_RE is deliberately HIGH-precision / low-recall — it
    should fire only on strong ALL/toàn-bộ done signals, NOT on every
    standalone 'done'. This documents the design (not a bug)."""

    def test_strong_signals_match(self):
        assert DONE_CLAIM_GAP_RE.search("All done")
        assert DONE_CLAIM_GAP_RE.search("Implement done")
        assert DONE_CLAIM_GAP_RE.search("Đã xong toàn bộ")

    def test_bare_done_not_matched(self):
        # Intentionally narrow: a bare standalone 'Done.' is NOT enough for
        # the gap gate (avoids blocking on partial mentions mid-work).
        assert not DONE_CLAIM_GAP_RE.search("Step 1 done, next.")
