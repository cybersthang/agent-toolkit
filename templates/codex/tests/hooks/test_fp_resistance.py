"""FP-resistance suite — 20 realistic transcripts that should NOT trigger
any hook (allow). These represent normal agent prose that contains claim
words inside code blocks, quotes, markdown links, tables, or questions —
all situations where regex-based detection has historically false-positived.
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import (
    LONG_PAD, cleanup_workspace, make_workspace, run_evidence_audit, write_transcript,
)


PROBES = {
    "version": 1,
    "_defaults": {
        "pass_claim_regex": r"\b(passed|verified|hoàn\s*thành|done)\b",
        "required_tool_prefixes": ["mcp__realdata_test__"],
    },
    "probes": []
}


def _assistant(text=None, tools=None):
    blocks = list(tools or [])
    if text:
        blocks.append({"type": "text", "text": text})
    return {"role": "assistant", "message": {"content": blocks}}


def _user(text):
    return {"role": "user", "content": text}


class TestFPResistance(unittest.TestCase):
    """All cases here MUST return decision=allow. If any becomes block,
    that's a regression on FP rate."""

    def setUp(self):
        self.ws = make_workspace(PROBES)
        (self.ws / "src").mkdir(parents=True, exist_ok=True)
        (self.ws / "src" / "module.py").write_text("def f(): pass", encoding="utf-8")

    def tearDown(self):
        cleanup_workspace(self.ws)

    def _expect_allow(self, msgs):
        t = write_transcript(self.ws, msgs)
        d = run_evidence_audit(t, self.ws).get("decision", "allow")
        self.assertEqual(d, "allow")

    # --- Past-tense words inside code blocks / inline code ---

    def test_01_past_tense_in_fenced_code(self):
        self._expect_allow([
            _user("commit format?"),
            _assistant(text="Format thường:\n```\nfix: đã sửa bug X\nfeat: đã thêm Y\n```\nQuy ước team. " + LONG_PAD),
        ])

    def test_02_past_tense_in_inline_code(self):
        self._expect_allow([
            _user("log mẫu?"),
            _assistant(text="Log mẫu: `[INFO] đã verified config` — đây là output script khác. " + LONG_PAD),
        ])

    def test_03_count_in_code_block(self):
        self._expect_allow([
            _user("ví dụ"),
            _assistant(text="```python\n# đã sửa 5 method trong refactor\nprint('hello')\n```\nĐây là pseudo-code thôi. " + LONG_PAD),
        ])

    # --- Quoted user prompts in blockquotes ---

    def test_04_quote_user_past_tense(self):
        self._expect_allow([
            _user("recap"),
            _assistant(text="Bạn nói:\n\n> Mình đã thêm tính năng đó hôm qua rồi\n\nCâu hỏi tiếp theo của mình. " + LONG_PAD),
        ])

    def test_05_quote_with_verified_word(self):
        self._expect_allow([
            _user("kiểm lại"),
            _assistant(text="Em quote lại lời sếp:\n\n> Tính năng này đã verified và passed QA\n\nVậy mình giả định ổn rồi. " + LONG_PAD),
        ])

    # --- Markdown tables (historical/example data) ---

    def test_06_table_with_done_status(self):
        self._expect_allow([
            _user("status?"),
            _assistant(text="Bảng sprint:\n\n| Task | Status |\n|------|--------|\n| A | done |\n| B | pending |\n\nGhi chú: chỉ tham khảo. " + LONG_PAD),
        ])

    def test_07_table_with_counts(self):
        self._expect_allow([
            _user("xem"),
            _assistant(text="Log:\n\n| Sprint | Action |\n|--------|--------|\n| 12 | đã sửa 5 file |\n| 13 | đã viết 3 test |\n\nĐây là sprint cũ. " + LONG_PAD),
        ])

    # --- Markdown links to real files ---

    def test_08_markdown_link_real_file(self):
        self._expect_allow([
            _user("đọc"),
            _assistant(
                tools=[{"type": "tool_use", "id": "r1", "name": "Read",
                        "input": {"file_path": "src/module.py"}}],
                text="Xem [module.py:1](src/module.py#L1) định nghĩa hàm f. " + LONG_PAD,
            ),
        ])

    def test_09_markdown_link_existing_disk_no_read(self):
        self._expect_allow([
            _user("ref"),
            _assistant(text="File [module.py](src/module.py) có hàm tiện ích. " + LONG_PAD),
        ])

    # --- Questions about bugs/slowness (no claims) ---

    def test_10_question_about_bug_word(self):
        self._expect_allow([
            _user("?"),
            _assistant(text="Vậy bug bạn nói tới là bug nào? Mình cần thêm thông tin để giúp [assumption]. " + LONG_PAD),
        ])

    def test_11_disclaimer_tag_present(self):
        self._expect_allow([
            _user("ý kiến?"),
            _assistant(text="Theo phỏng đoán, module này có thể chậm khi nhiều record [assumption]. " + LONG_PAD),
        ])

    # --- Meta-review marker ---

    def test_12_meta_review_with_pass_word(self):
        self._expect_allow([
            _user("review toolkit"),
            _assistant(text="[meta-review] Hook system đã verified design-wise, tests pass cleanly. " + LONG_PAD),
        ])

    def test_13_meta_short_form(self):
        self._expect_allow([
            _user("review"),
            _assistant(text="[meta] Toàn bộ implementation done từ góc nhìn design. " + LONG_PAD),
        ])

    # --- Explicit bypasses ---

    def test_14_evidence_audit_skip(self):
        self._expect_allow([
            _user("safe"),
            _assistant(text="Style fix nhỏ, không cần verify. evidence-audit: skip\n" + LONG_PAD),
        ])

    def test_15_probe_skip_all(self):
        self._expect_allow([
            _user("verify"),
            _assistant(text="Tests pass nhưng DB staging down. probe-skip: all DB unavailable. " + LONG_PAD),
        ])

    # --- Past-tense WITH matching Edit (legitimate) ---

    def test_16_action_with_edit(self):
        self._expect_allow([
            _user("sửa"),
            _assistant(
                tools=[{"type": "tool_use", "id": "e1", "name": "Edit",
                        "input": {"file_path": "src/module.py",
                                 "old_string": "pass", "new_string": "return 1"}}],
                text="Đã sửa hàm f để return 1. " + LONG_PAD,
            ),
        ])

    # --- Generic claim words inside code refs (verified by Read) ---

    def test_17_slow_word_in_code_quote(self):
        self._expect_allow([
            _user("explain"),
            _assistant(
                tools=[{"type": "tool_use", "id": "r2", "name": "Read",
                        "input": {"file_path": "src/module.py"}}],
                text="Comment trong code: `# TODO: this is slow on large input`. " + LONG_PAD,
            ),
        ])

    def test_18_missing_word_in_blockquote(self):
        self._expect_allow([
            _user("phân tích"),
            _assistant(
                tools=[{"type": "tool_use", "id": "g1", "name": "Grep",
                        "input": {"pattern": "missing", "path": "src/"}}],
                text="Output grep:\n\n> src/module.py:5: # missing index\n\nMình cần check thêm. " + LONG_PAD),
        ])

    # --- Short response below threshold ---

    def test_19_short_response_below_threshold(self):
        self._expect_allow([
            _user("ok"),
            _assistant(text="Tests pass."),
        ])

    # --- TodoWrite all completed + completion claim ---

    def test_20_all_done_with_clean_todos_and_mcp(self):
        # Completion claim + TodoWrite clean + MCP real-data call → allow
        # all 3 enforcement layers (PASS contract, todo_inconsistency, generic).
        self._expect_allow([
            _user("status?"),
            _assistant(tools=[
                {"type": "tool_use", "id": "td", "name": "TodoWrite",
                 "input": {"todos": [
                     {"content": "s1", "activeForm": "s1", "status": "completed"},
                 ]}},
                {"type": "tool_use", "id": "m1", "name": "mcp__realdata_test__run_module_test",
                 "input": {"module": "foo"}},
                {"type": "tool_use", "id": "e2", "name": "Edit",
                 "input": {"file_path": "src/module.py",
                          "old_string": "pass", "new_string": "return 1"}},
            ], text="Đã hoàn thành tất cả. " + LONG_PAD),
        ])


if __name__ == "__main__":
    unittest.main()
