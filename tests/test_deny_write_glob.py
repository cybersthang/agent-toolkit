"""v0.34 T8b/T8 (F4.1) — invariant_guard `deny_write_glob` rule-type + the
`no-subagents-forge` seed invariant.

A path-DENY rule blocks any Edit/Write whose target matches a glob, independent of
must_keep content patterns. `no-subagents-forge` uses it to stop the agent forging a
sub-agent review transcript (`.claude/projects/**/subagents/*.jsonl`).

Acceptance eval: ev4-subagents-write-denied.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "invariant_guard.py"
SEED = TOOLKIT_ROOT / "templates" / "agent_toolkit" / "invariants.json"

_DENY_INV = {
    "id": "no-subagents-forge",
    "description": "no forging sub-agent transcripts",
    "applies_to": ["**/.claude/projects/**/subagents/**"],
    "rules": {"deny_write_glob": ["**/.claude/projects/**/subagents/**",
                                  "**/subagents/**"]},
    "severity": "blocker",
    "rationale": "harness-authored only",
}


def _run(envelope: dict):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(envelope),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=15, env=env)


def _decision(result):
    out = (result.stdout or "").strip()
    if not out:
        return None
    try:
        return json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision")
    except json.JSONDecodeError:
        return None


def _ws(tmp, invariants):
    ws = Path(tmp).resolve()
    (ws / ".agent-toolkit").mkdir(parents=True, exist_ok=True)
    (ws / ".agent-toolkit" / "invariants.json").write_text(
        json.dumps({"invariants": invariants}), encoding="utf-8")
    return ws


def _env(ws, tool, file_path, **extra):
    ti = {"file_path": file_path}
    ti.update(extra)
    return {"tool_name": tool, "tool_input": ti, "cwd": str(ws)}


class TestDenyWriteGlob(unittest.TestCase):

    def test_write_to_denied_glob_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = _ws(tmp, [_DENY_INV])
            e = _env(ws, "Write",
                     "/home/u/.claude/projects/proj/SID/subagents/agent-x.jsonl",
                     content="{}")
            self.assertEqual(_decision(_run(e)), "deny")

    def test_edit_to_denied_glob_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = _ws(tmp, [_DENY_INV])
            e = _env(ws, "Edit",
                     "/x/.claude/projects/p/s/subagents/agent-y.jsonl",
                     old_string="a", new_string="b")
            self.assertEqual(_decision(_run(e)), "deny")

    def test_non_matching_path_not_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = _ws(tmp, [_DENY_INV])
            e = _env(ws, "Write", "src/normal.py", content="x = 1")
            self.assertNotEqual(_decision(_run(e)), "deny")

    def test_relative_subagents_path_denied(self):
        # review round-1 MED-2: a RELATIVE `.claude/...subagents/...` path (which the
        # strict leading-slash glob can miss) is denied by the broad `**/subagents/**`.
        with tempfile.TemporaryDirectory() as tmp:
            ws = _ws(tmp, [_DENY_INV])
            e = _env(ws, "Write", ".claude/projects/p/SID/subagents/agent-z.jsonl",
                     content="{}")
            self.assertEqual(_decision(_run(e)), "deny")

    def test_review_verdict_path_not_denied(self):
        # F4.2's verdict path must NOT collide with the subagents deny-glob.
        with tempfile.TemporaryDirectory() as tmp:
            ws = _ws(tmp, [_DENY_INV])
            e = _env(ws, "Write",
                     str(ws / ".agent-toolkit" / ".review_verdict" / "v.json"),
                     content="{}")
            self.assertNotEqual(_decision(_run(e)), "deny")

    def test_warn_severity_deny_glob_does_not_hard_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            inv = dict(_DENY_INV, severity="warn")
            ws = _ws(tmp, [inv])
            e = _env(ws, "Write",
                     "/x/.claude/projects/p/s/subagents/a.jsonl", content="{}")
            self.assertNotEqual(_decision(_run(e)), "deny")

    def test_invariant_without_deny_glob_unaffected(self):
        # Regression: a normal must_keep invariant still behaves as before.
        with tempfile.TemporaryDirectory() as tmp:
            inv = {"id": "keep-x", "applies_to": ["*.py"],
                   "rules": {"must_keep_regex": [r"x\s*=\s*1"]},
                   "severity": "blocker", "rationale": "t"}
            ws = _ws(tmp, [inv])
            e = _env(ws, "Edit", str(ws / "f.py"),
                     old_string="x = 1", new_string="x = 2")
            self.assertEqual(_decision(_run(e)), "deny")   # strips must_keep → deny


class TestSeedInvariant(unittest.TestCase):

    def test_seed_is_valid_json(self):
        json.loads(SEED.read_text(encoding="utf-8"))

    def test_seed_has_no_subagents_forge_blocker(self):
        data = json.loads(SEED.read_text(encoding="utf-8"))
        invs = {i["id"]: i for i in data["invariants"]}
        self.assertIn("no-subagents-forge", invs)
        inv = invs["no-subagents-forge"]
        self.assertEqual(inv["severity"], "blocker")
        self.assertIn("deny_write_glob", inv["rules"])
        self.assertTrue(inv["rules"]["deny_write_glob"])


if __name__ == "__main__":
    unittest.main()
