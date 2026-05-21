# -*- coding: utf-8 -*-
"""Tests for Phase D v0.9.0 — get_enforce_mode() helper + hook integration."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
COMMON = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "_common.py"
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "implement_notes_gate.py"
PY = sys.executable


def _load_common():
    spec = importlib.util.spec_from_file_location("_common_enforce_test", str(COMMON))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_common_enforce_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestGetEnforceMode(unittest.TestCase):
    """Phase D eval d1: config-driven enforce_mode.json."""

    def setUp(self):
        self.mod = _load_common()
        # Clear STRICT env so it doesn't override per-hook lookup
        self._patcher = patch.dict(
            os.environ,
            {k: v for k, v in os.environ.items() if k != "AGENT_TOOLKIT_STRICT"},
            clear=True,
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_default_returned_when_no_config(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            mode = self.mod.get_enforce_mode(workspace, "some_hook")
            self.assertEqual(mode, "warn")

    def test_per_hook_override_honored(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            (workspace / ".agent-toolkit" / "enforce_mode.json").write_text(
                json.dumps({"default": "warn",
                            "per_hook": {"my_hook": "block"}}),
                encoding="utf-8",
            )
            self.assertEqual(self.mod.get_enforce_mode(workspace, "my_hook"),
                             "block")
            self.assertEqual(self.mod.get_enforce_mode(workspace, "other_hook"),
                             "warn")

    def test_default_fallback_when_hook_missing(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            (workspace / ".agent-toolkit" / "enforce_mode.json").write_text(
                json.dumps({"default": "block"}),
                encoding="utf-8",
            )
            self.assertEqual(self.mod.get_enforce_mode(workspace, "unknown"),
                             "block")

    def test_strict_env_var_overrides_everything(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            (workspace / ".agent-toolkit" / "enforce_mode.json").write_text(
                json.dumps({"default": "warn",
                            "per_hook": {"my_hook": "warn"}}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"AGENT_TOOLKIT_STRICT": "1"}):
                self.assertEqual(
                    self.mod.get_enforce_mode(workspace, "my_hook"),
                    "block",
                    "STRICT env var should override config",
                )

    def test_malformed_config_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            (workspace / ".agent-toolkit" / "enforce_mode.json").write_text(
                "{not valid json", encoding="utf-8",
            )
            self.assertEqual(self.mod.get_enforce_mode(workspace, "x"), "warn")


class TestHooksHonorEnforceMode(unittest.TestCase):
    """Phase D eval d2: implement_notes_gate emits block when enforce=block."""

    def _setup(self, td, enforce_mode):
        project = Path(td) / "proj"
        project.mkdir()
        subprocess.run(["git", "init"], cwd=str(project), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(project),
                       capture_output=True, timeout=5)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(project),
                       capture_output=True, timeout=5)
        subprocess.run(["git", "checkout", "-B", "feature-foo"], cwd=str(project),
                       capture_output=True, timeout=5)
        sd = project / ".agent-toolkit" / "specs"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "feature-foo.md").write_text(
            "---\nslug: feature-foo\nmodule: demo\nstatus: implementing\n"
            "feature_kind: orchestration\n"
            "acceptance_evals:\n  - id: e1\n    story: x\n    grader: code\n"
            "    probe: {}\n    expected: {}\n    target_pass_rate: 1.0\n"
            "---\n# spec\n", encoding="utf-8",
        )
        if enforce_mode:
            (project / ".agent-toolkit" / "enforce_mode.json").write_text(
                json.dumps({"default": "warn",
                            "per_hook": {"implement_notes_gate": enforce_mode}}),
                encoding="utf-8",
            )
        # Build transcript with done-claim
        t = project / ".claude" / "transcript.jsonl"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(
            json.dumps({"role": "user", "content": "go"}) + "\n" +
            json.dumps({"role": "assistant",
                        "content": [{"type": "text",
                                     "text": "Implement done."}]}) + "\n",
            encoding="utf-8",
        )
        return project, t

    def _run(self, envelope, cwd):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # Make sure strict mode not set
        env.pop("AGENT_TOOLKIT_STRICT", None)
        return subprocess.run(
            [PY, str(HOOK)],
            input=json.dumps(envelope), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=15, cwd=str(cwd), env=env,
        )

    def test_warn_mode_emits_additional_context(self):
        with tempfile.TemporaryDirectory() as td:
            project, t = self._setup(td, enforce_mode="warn")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = self._run(envelope, project)
            self.assertEqual(proc.returncode, 0)
            # Warn mode → additionalContext (not block)
            self.assertIn("additionalContext", proc.stdout)
            self.assertNotIn('"decision": "block"', proc.stdout)

    def test_block_mode_emits_decision_block(self):
        with tempfile.TemporaryDirectory() as td:
            project, t = self._setup(td, enforce_mode="block")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = self._run(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn('"decision": "block"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
