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
from _audit.progress_checks import (  # noqa: E402
    CITATION_MISSING_NEAR_RE, check_phantom_citation,
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


# EVID-FP regression: phantom_citation false-positived on legitimate
# absence-reporting because the "reporting-missing" exemption window only
# matched a narrow keyword set (missing/absent/...). A path framed as ABSENT
# via common neutral phrasings ("not found", "deleted", "404", "ENOENT",
# Vietnamese "đã xoá") is a FINDING, not a phantom claim — must be exempt.
class TestCitationMissingNearRecall:
    """CITATION_MISSING_NEAR_RE must recognise neutral absence phrasings so
    check_phantom_citation exempts them from the phantom-cite block."""

    ABSENCE_POSITIVES = [
        "no such file", "not found", "file not found", "removed", "deleted",
        "gone", "404", "not there", "n't found", "not found", "ENOENT",
        "đã xoá", "đã xóa", "đã gỡ", "bị xoá",
        # case-insensitivity check
        "NOT FOUND", "Enoent", "DELETED",
    ]

    def test_all_absence_phrasings_match(self):
        misses = [p for p in self.ABSENCE_POSITIVES
                  if not CITATION_MISSING_NEAR_RE.search(p)]
        assert not misses, f"CITATION_MISSING_NEAR_RE missed absence phrasings: {misses}"

    def test_existing_alternatives_still_match(self):
        # The original keyword set must keep matching (no regression).
        for p in ("missing", "absent", "does not exist", "dead link",
                  "broken link", "(planned)", "placeholder", "TBD",
                  "chưa tồn tại", "không có", "thiếu"):
            assert CITATION_MISSING_NEAR_RE.search(p), \
                f"CITATION_MISSING_NEAR_RE regressed on {p!r}"

    def test_neutral_word_does_not_match(self):
        # A plain claim with no absence framing must NOT be exempted.
        assert not CITATION_MISSING_NEAR_RE.search("see this helper for details")


class TestPhantomCitationExemptsAbsenceReporting:
    """End-to-end: check_phantom_citation must NOT flag a cited path when the
    surrounding text frames it as absent via a neutral phrasing."""

    def test_not_found_path_is_not_phantom(self, tmp_path):
        text = "Read foo/bar_baz.py — not found; file not found on disk."
        assert check_phantom_citation(text, [], tmp_path) is None

    def test_deleted_path_is_not_phantom(self, tmp_path):
        text = "config/settings_old.py was deleted in the last refactor."
        assert check_phantom_citation(text, [], tmp_path) is None

    def test_404_path_is_not_phantom(self, tmp_path):
        text = "Got a 404 on docs/api_reference.py — no such file there."
        assert check_phantom_citation(text, [], tmp_path) is None

    def test_vietnamese_absence_path_is_not_phantom(self, tmp_path):
        text = "File src/old_module.py đã xoá rồi, không còn nữa."
        assert check_phantom_citation(text, [], tmp_path) is None

    def test_unframed_phantom_path_still_blocks(self, tmp_path):
        # Control: a cited non-existent path with NO absence framing is phantom.
        text = "See imaginary/ghost_helper.py:42 for the shared logic."
        assert check_phantom_citation(text, [], tmp_path) is not None


# EVID-FP regression (2026-05-30): phantom_citation false-positived on
# (a) paths the same turn WROTE via Write/MultiEdit/NotebookEdit, and
# (b) paths that literally appeared in a prior tool_result's content.
class TestPhantomCitationCreditsTurnEvidence:
    """check_phantom_citation must credit files the turn demonstrably wrote
    and paths proven by prior tool_result output."""

    def test_written_file_is_not_phantom(self, tmp_path):
        # (a) The path was created via Write THIS turn → it exists.
        text = "Implemented the helper in src/new_helper.py:12 as planned."
        tool_calls = [{"name": "Write", "input": {"file_path": "src/new_helper.py"}}]
        assert check_phantom_citation(text, tool_calls, tmp_path) is None

    def test_multiedit_file_is_not_phantom(self, tmp_path):
        text = "Refactored config/app_settings.py with the new defaults."
        tool_calls = [{"name": "MultiEdit", "input": {"file_path": "config/app_settings.py"}}]
        assert check_phantom_citation(text, tool_calls, tmp_path) is None

    def test_notebookedit_path_is_not_phantom(self, tmp_path):
        text = "Added a cell to notebooks/analysis_main.py for the plot."
        tool_calls = [{"name": "NotebookEdit", "input": {"notebook_path": "notebooks/analysis_main.py"}}]
        assert check_phantom_citation(text, tool_calls, tmp_path) is None

    def test_path_in_prior_tool_result_is_not_phantom(self, tmp_path):
        # (b) The path showed up in a grep/cat tool_result → it exists.
        text = "The match lives in lib/parser_core.py:88 per the grep."
        results_by_id = {
            "toolu_1": {"content": "lib/parser_core.py:88: def parse(): ..."}
        }
        assert check_phantom_citation(text, [], tmp_path, results_by_id) is None

    def test_path_in_structured_tool_result_is_not_phantom(self, tmp_path):
        text = "See utils/string_format.py from the ls output."
        results_by_id = {
            "toolu_2": {"content": [{"type": "text", "text": "utils/string_format.py\nutils/other.py"}]}
        }
        assert check_phantom_citation(text, [], tmp_path, results_by_id) is None

    def test_genuinely_unseen_path_still_blocks(self, tmp_path):
        # Control: never written, never output, never read, doesn't exist → phantom.
        text = "See imaginary/ghost_helper.py:42 for the shared logic."
        results_by_id = {"toolu_3": {"content": "some unrelated grep output here"}}
        tool_calls = [{"name": "Write", "input": {"file_path": "src/something_else.py"}}]
        assert check_phantom_citation(text, tool_calls, tmp_path, results_by_id) is not None
