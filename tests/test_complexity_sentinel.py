# -*- coding: utf-8 -*-
"""Tests for complexity_sentinel.py Stop hook — v0.12.0."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "complexity_sentinel.py"


def _make_transcript(workspace: Path, edited_files: list) -> Path:
    """Write a minimal JSONL transcript with assistant tool_use entries."""
    path = workspace / ".transcript.jsonl"
    lines = []
    for fp in edited_files:
        msg = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Write", "input": {"file_path": str(fp)}}
                ],
            },
        }
        lines.append(json.dumps(msg))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run_hook(workspace: Path, transcript: Path,
              extra_env: dict = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    envelope = {
        "cwd": str(workspace),
        "transcript_path": str(transcript),
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        env=env,
    )


class TestComplexitySentinel(unittest.TestCase):

    def setUp(self):
        self.td_obj = tempfile.TemporaryDirectory()
        self.workspace = Path(self.td_obj.name).resolve()
        (self.workspace / ".agent-toolkit").mkdir()

    def tearDown(self):
        self.td_obj.cleanup()

    def test_clean_file_silent(self):
        f = self.workspace / "feature.py"
        f.write_text("def x():\n    return 1\n", encoding="utf-8")
        tx = _make_transcript(self.workspace, [f])
        result = _run_hook(self.workspace, tx)
        self.assertEqual(result.stdout.strip(), "",
                         "Clean file → no warning")

    def test_deep_loop_nest_warned(self):
        f = self.workspace / "feature.py"
        f.write_text(
            "def x(d):\n"
            "    for a in d:\n"
            "        for b in a:\n"
            "            for c in b:\n"
            "                print(c)\n",
            encoding="utf-8",
        )
        tx = _make_transcript(self.workspace, [f])
        result = _run_hook(self.workspace, tx)
        self.assertIn("complexity-sentinel", result.stdout)
        self.assertIn("loop nest", result.stdout)

    def test_long_function_warned(self):
        f = self.workspace / "feature.py"
        body = "\n".join(f"    x{i} = {i}" for i in range(70))
        f.write_text(f"def big_fn():\n{body}\n", encoding="utf-8")
        tx = _make_transcript(self.workspace, [f])
        result = _run_hook(self.workspace, tx)
        self.assertIn("function body", result.stdout)
        self.assertIn("big_fn", result.stdout)

    def test_test_file_exempt(self):
        f = self.workspace / "tests" / "test_huge.py"
        f.parent.mkdir()
        body = "\n".join([
            "def huge():",
            "    for a in []:",
            "        for b in []:",
            "            for c in []:",
            "                for d in []:",
            "                    pass",
        ])
        f.write_text(body, encoding="utf-8")
        tx = _make_transcript(self.workspace, [f])
        result = _run_hook(self.workspace, tx)
        self.assertEqual(result.stdout.strip(), "",
                         "Test files exempt from complexity sentinel")

    def test_syntax_error_skipped(self):
        f = self.workspace / "broken.py"
        f.write_text("def bad(\n  this is not python", encoding="utf-8")
        tx = _make_transcript(self.workspace, [f])
        result = _run_hook(self.workspace, tx)
        self.assertEqual(result.stdout.strip(), "",
                         "Unparseable file → silent (no false positive)")

    def test_disable_env_var(self):
        f = self.workspace / "feature.py"
        f.write_text(
            "def x(d):\n"
            "    for a in d:\n"
            "        for b in a:\n"
            "            for c in b:\n"
            "                print(c)\n",
            encoding="utf-8",
        )
        tx = _make_transcript(self.workspace, [f])
        result = _run_hook(self.workspace, tx,
                           extra_env={"AGENT_TOOLKIT_DISABLE": "1"})
        self.assertEqual(result.stdout.strip(), "")

    def test_config_override(self):
        cfg = self.workspace / ".agent-toolkit" / "complexity_budget.json"
        cfg.write_text(json.dumps({"max_loop_nest": 99}), encoding="utf-8")
        f = self.workspace / "feature.py"
        f.write_text(
            "def x(d):\n"
            "    for a in d:\n"
            "        for b in a:\n"
            "            for c in b:\n"
            "                print(c)\n",
            encoding="utf-8",
        )
        tx = _make_transcript(self.workspace, [f])
        result = _run_hook(self.workspace, tx)
        # Loop nest threshold raised to 99 → no warn on 3-deep loop
        self.assertNotIn("loop nest", result.stdout)


if __name__ == "__main__":
    unittest.main()
