"""Hallucinated-progress contract — 5 categories A-E + 2 bypass cases."""
import json
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import (
    LONG_PAD, cleanup_workspace, make_workspace, run_evidence_audit, write_transcript,
)


PROBES = {
    "version": 1,
    "_defaults": {
        # Disable PASS contract for these tests so progress checks isolate.
        "pass_claim_regex": "____NEVER_MATCH____",
        "disabled_progress_checks": []
    },
    "probes": []
}


def _assistant(text=None, tools=None):
    blocks = list(tools or [])
    if text:
        blocks.append({"type": "text", "text": text})
    return {"role": "assistant", "message": {"content": blocks}}


def _user(text_or_blocks):
    if isinstance(text_or_blocks, list):
        return {"role": "user", "content": text_or_blocks}
    return {"role": "user", "content": text_or_blocks}


def _tool_result(tool_use_id, content, is_error=False):
    return _user([
        {"type": "tool_result", "tool_use_id": tool_use_id,
         "content": content, "is_error": is_error}
    ])


class TestProgressChecks(unittest.TestCase):

    def setUp(self):
        self.ws = make_workspace(PROBES)
        # Create a real file we can cite legitimately.
        (self.ws / "src").mkdir(parents=True, exist_ok=True)
        (self.ws / "src" / "real.py").write_text("def hello():\n    pass\n", encoding="utf-8")

    def tearDown(self):
        cleanup_workspace(self.ws)

    def _decide(self, messages):
        t = write_transcript(self.ws, messages)
        return run_evidence_audit(t, self.ws).get("decision", "allow")

    # ===== A. action_ghost =====

    def test_A1_action_ghost_without_edit_blocks(self):
        self.assertEqual(self._decide([
            _user("thêm hàm bar"),
            _assistant(text="Mình đã thêm hàm bar vào module. " + LONG_PAD),
        ]), "block")

    def test_A2_action_with_edit_allows(self):
        self.assertEqual(self._decide([
            _user("thêm hàm bar"),
            _assistant(
                tools=[{"type": "tool_use", "id": "u1", "name": "Edit",
                        "input": {"file_path": "src/real.py", "old_string": "pass", "new_string": "return 1"}}],
                text="Mình đã thêm logic vào hàm. " + LONG_PAD,
            ),
        ]), "allow")

    def test_A3_english_fixed_without_edit_blocks(self):
        self.assertEqual(self._decide([
            _user("fix"),
            _assistant(text="I fixed the bug in the controller logic. " + LONG_PAD),
        ]), "block")

    # ===== B. tool_result_fabrication =====

    def test_B1_pass_claim_with_failed_bash_blocks(self):
        self.assertEqual(self._decide([
            _user("chạy test"),
            _assistant(tools=[{"type": "tool_use", "id": "b1", "name": "Bash",
                               "input": {"command": "pytest"}}]),
            _tool_result("b1", "Some output\nExit code: 1\n", is_error=True),
            _assistant(
                tools=[{"type": "tool_use", "id": "e1", "name": "Edit",
                        "input": {"file_path": "src/real.py", "old_string": "pass", "new_string": "return 0"}}],
                text="Tốt — Đã sửa file. Build succeeded, no errors. " + LONG_PAD,
            ),
        ]), "block")

    def test_B2_pass_claim_with_clean_bash_allows(self):
        self.assertEqual(self._decide([
            _user("chạy test"),
            _assistant(tools=[{"type": "tool_use", "id": "b2", "name": "Bash",
                               "input": {"command": "pytest"}}]),
            _tool_result("b2", "All tests passed\nExit code: 0\n"),
            _assistant(
                tools=[{"type": "tool_use", "id": "e2", "name": "Edit",
                        "input": {"file_path": "src/real.py", "old_string": "pass", "new_string": "return 1"}}],
                text="Đã sửa và tests passed cleanly. " + LONG_PAD,
            ),
        ]), "allow")

    # ===== C. phantom_citation =====

    def test_C1_ghost_file_blocks(self):
        self.assertEqual(self._decide([
            _user("đọc gì đó"),
            _assistant(text="Xem imaginary/ghost_file.py:42 để hiểu thêm logic này. " + LONG_PAD),
        ]), "block")

    def test_C2_cited_file_was_read_allows(self):
        self.assertEqual(self._decide([
            _user("đọc real.py"),
            _assistant(
                tools=[{"type": "tool_use", "id": "r1", "name": "Read",
                        "input": {"file_path": "src/real.py"}}],
                text="Xem src/real.py:1 thấy có hàm hello. " + LONG_PAD,
            ),
        ]), "allow")

    def test_C3_existing_file_on_disk_allows(self):
        self.assertEqual(self._decide([
            _user("đề cập real.py"),
            _assistant(text="File src/real.py có hàm hello định nghĩa sẵn trong workspace. " + LONG_PAD),
        ]), "allow")

    def test_C4_markdown_link_url_resolves(self):
        # Display `short.py:N` would naively be phantom, but URL points to real path.
        self.assertEqual(self._decide([
            _user("link"),
            _assistant(
                tools=[{"type": "tool_use", "id": "r2", "name": "Read",
                        "input": {"file_path": "src/real.py"}}],
                text="Xem [real.py:1](src/real.py#L1) thấy hàm hello. " + LONG_PAD,
            ),
        ]), "allow")

    # ===== D. todo_inconsistency =====

    def test_D1_all_done_with_open_todos_blocks(self):
        self.assertEqual(self._decide([
            _user("làm nhiều việc"),
            _assistant(tools=[{
                "type": "tool_use", "id": "td1", "name": "TodoWrite",
                "input": {"todos": [
                    {"content": "step 1", "activeForm": "step 1", "status": "completed"},
                    {"content": "step 2", "activeForm": "step 2", "status": "pending"},
                    {"content": "step 3", "activeForm": "step 3", "status": "in_progress"},
                ]}
            }]),
            _tool_result("td1", "ok"),
            _assistant(text="Đã xong tất cả các bước! " + LONG_PAD),
        ]), "block")

    def test_D2_all_done_with_clean_todos_allows(self):
        self.assertEqual(self._decide([
            _user("làm"),
            _assistant(tools=[
                {"type": "tool_use", "id": "td2", "name": "TodoWrite",
                 "input": {"todos": [
                     {"content": "step 1", "activeForm": "step 1", "status": "completed"},
                     {"content": "step 2", "activeForm": "step 2", "status": "completed"},
                 ]}},
                {"type": "tool_use", "id": "e3", "name": "Edit",
                 "input": {"file_path": "src/real.py", "old_string": "pass", "new_string": "return 2"}},
            ], text="Đã hoàn thành tất cả. " + LONG_PAD),
        ]), "allow")

    # ===== E. overcount =====

    def test_E1_claim_5_files_with_1_edit_blocks(self):
        self.assertEqual(self._decide([
            _user("sửa nhiều file"),
            _assistant(
                tools=[{"type": "tool_use", "id": "e4", "name": "Edit",
                        "input": {"file_path": "src/real.py", "old_string": "pass", "new_string": "return 1"}}],
                text="Mình đã sửa 5 file để thay đổi logic chính. " + LONG_PAD,
            ),
        ]), "block")

    def test_E2_claim_2_files_with_2_edits_allows(self):
        self.assertEqual(self._decide([
            _user("sửa"),
            _assistant(
                tools=[
                    {"type": "tool_use", "id": "e5", "name": "Edit",
                     "input": {"file_path": "src/real.py", "old_string": "pass", "new_string": "return 1"}},
                    {"type": "tool_use", "id": "e6", "name": "Write",
                     "input": {"file_path": "src/new.py", "content": "x=1"}},
                ],
                text="Mình đã sửa 2 file theo yêu cầu. " + LONG_PAD,
            ),
        ]), "allow")

    def test_E3_claim_3_bugs_with_1_edit_blocks(self):
        # Broadened regex catches non-file counter-nouns.
        self.assertEqual(self._decide([
            _user("fix bugs"),
            _assistant(
                tools=[{"type": "tool_use", "id": "e7", "name": "Edit",
                        "input": {"file_path": "src/real.py", "old_string": "pass", "new_string": "return 1"}}],
                text="Mình đã fix 3 bugs trong logic chính. " + LONG_PAD,
            ),
        ]), "block")

    # ===== Bypasses =====

    def test_F1_progress_skip_all_allows(self):
        self.assertEqual(self._decide([
            _user("skip"),
            _assistant(text="Đã thêm logic mới. progress-skip: all manual review override. " + LONG_PAD),
        ]), "allow")

    def test_F2_progress_skip_action_ghost_allows(self):
        self.assertEqual(self._decide([
            _user("skip A"),
            _assistant(text="Mình đã thêm hàm. progress-skip: action_ghost giải thích thuần lý thuyết. " + LONG_PAD),
        ]), "allow")

    # ===== FP-resistance =====

    def test_G1_past_tense_in_code_block_does_not_trigger(self):
        # 'đã thêm' inside fenced code is illustrative, not a claim.
        text = (
            "Đây là ví dụ commit message:\n\n"
            "```\n"
            "feat: đã thêm hàm bar vào module\n"
            "```\n\n"
            "Format này hay dùng. " + LONG_PAD
        )
        self.assertEqual(self._decide([
            _user("ví dụ commit"),
            _assistant(text=text),
        ]), "allow")

    def test_G2_past_tense_in_inline_code_does_not_trigger(self):
        # `đã sửa` shown as code reference, not action claim.
        text = (
            "Khi bạn thấy log `INFO: đã sửa cấu hình thành công`, "
            "đó là output của script khác — không phải mình. " + LONG_PAD
        )
        self.assertEqual(self._decide([
            _user("giải thích log"),
            _assistant(text=text),
        ]), "allow")

    def test_G3_past_tense_in_blockquote_does_not_trigger(self):
        # Quoting the user's prior message back — blockquote line should be
        # stripped before action_ghost regex applies.
        text = (
            "Bạn nói:\n\n"
            "> Mình đã thêm tính năng tuần trước rồi đó\n\n"
            "Mình cần biết thêm về tính năng đó là gì. Câu hỏi tiếp theo. " + LONG_PAD
        )
        self.assertEqual(self._decide([
            _user("xem lại"),
            _assistant(text=text),
        ]), "allow")

    def test_G4_count_claim_in_table_row_does_not_trigger(self):
        # Table column saying "đã sửa 5 file" as historical reference.
        text = (
            "Theo log lịch sử commit:\n\n"
            "| Sprint | Action | Result |\n"
            "|--------|--------|--------|\n"
            "| S12    | đã sửa 5 file | passed |\n"
            "| S13    | refactor | done |\n\n"
            "Số liệu này chỉ để tham khảo. " + LONG_PAD
        )
        self.assertEqual(self._decide([
            _user("xem bảng"),
            _assistant(text=text),
        ]), "allow")


if __name__ == "__main__":
    unittest.main()
