"""invariant_guard PreToolUse hook — 6 cases including bypass + glob match."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import cleanup_workspace, make_workspace, run_invariant_guard


def _make_workspace_with_invariant():
    ws = make_workspace(probes_registry=None)
    inv = {
        "version": 1,
        "invariants": [{
            "id": "test-keep-order",
            "description": "test rule",
            "applies_to": ["app-server/**/models/**.py"],
            "rules": {"must_keep_regex": ["order='type'"], "must_keep_call": []},
            "severity": "blocker",
            "rationale": "smoke test"
        }]
    }
    (ws / ".agent-toolkit" / "invariants.json").write_text(
        json.dumps(inv, ensure_ascii=False), encoding="utf-8"
    )
    return ws


class TestInvariantGuard(unittest.TestCase):

    def setUp(self):
        self.ws = _make_workspace_with_invariant()

    def tearDown(self):
        cleanup_workspace(self.ws)

    def _decision(self, envelope):
        envelope["cwd"] = str(self.ws)
        out = run_invariant_guard(envelope)
        return out.get("permissionDecision", "allow")

    def test_01_edit_removes_pattern_denies(self):
        self.assertEqual(self._decision({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.ws / "app-server" / "foo" / "models" / "bar.py"),
                "old_string": "order='type'",
                "new_string": "order='id'",
            },
        }), "deny")

    def test_02_edit_keeps_pattern_allows(self):
        self.assertEqual(self._decision({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.ws / "app-server" / "foo" / "models" / "bar.py"),
                "old_string": "x=1\norder='type'",
                "new_string": "x=2\norder='type'",
            },
        }), "allow")

    def test_03_bypass_via_user_prompt_allows(self):
        self.assertEqual(self._decision({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.ws / "app-server" / "foo" / "models" / "bar.py"),
                "old_string": "order='type'",
                "new_string": "order='id'",
            },
            "user_prompt": "bypass-invariant: test-keep-order vi test",
        }), "allow")

    def test_04_path_outside_glob_allows(self):
        self.assertEqual(self._decision({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.ws / "app-server" / "foo" / "services" / "bar.py"),
                "old_string": "order='type'",
                "new_string": "order='id'",
            },
        }), "allow")

    def test_05_write_new_file_missing_pattern_denies(self):
        # Documented limitation: Write of new file under glob without pattern is denied.
        self.assertEqual(self._decision({
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.ws / "app-server" / "new_mod" / "models" / "new.py"),
                "content": "class Foo:\n    pass\n",
            },
        }), "deny")

    def test_06_path_outside_repo_allows(self):
        # static/src/ doesn't match models/** glob.
        self.assertEqual(self._decision({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.ws / "app-server" / "static" / "src" / "bar.py"),
                "old_string": "order='type'",
                "new_string": "order='id'",
            },
        }), "allow")


if __name__ == "__main__":
    unittest.main()
