# -*- coding: utf-8 -*-
"""Tests for AGENT_TOOLKIT_STRICT env var dual-mode — Phase E eval e1."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
COMMON = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "_common.py"


def _load_common():
    spec = importlib.util.spec_from_file_location("_common_strict_test", str(COMMON))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_common_strict_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestStrictMode(unittest.TestCase):

    def setUp(self):
        self.mod = _load_common()

    def test_default_unset_returns_false(self):
        env = {k: v for k, v in os.environ.items() if k != "AGENT_TOOLKIT_STRICT"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(self.mod.is_strict_mode())

    def test_strict_env_var_returns_true(self):
        with patch.dict(os.environ, {"AGENT_TOOLKIT_STRICT": "1"}):
            self.assertTrue(self.mod.is_strict_mode())

    def test_other_value_not_strict(self):
        with patch.dict(os.environ, {"AGENT_TOOLKIT_STRICT": "0"}):
            self.assertFalse(self.mod.is_strict_mode())
        with patch.dict(os.environ, {"AGENT_TOOLKIT_STRICT": "true"}):
            self.assertFalse(self.mod.is_strict_mode())

    def test_strict_mode_makes_crash_propagate_rc1(self):
        def crashing_main():
            raise RuntimeError("test crash")

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            with patch.object(self.mod, "_resolve_crash_workspace",
                              return_value=workspace), \
                 patch.dict(os.environ, {"AGENT_TOOLKIT_STRICT": "1"}):
                rv = self.mod.run_main_safe(crashing_main)
            self.assertEqual(rv, 1, "STRICT mode should propagate crash → rc=1")

    def test_default_mode_crash_returns_rc1_v0_21(self):
        """v0.21 breaking change: default is now fail-CLOSED (rc=1).
        Set AGENT_TOOLKIT_NO_STRICT=1 to opt out → rc=0 (legacy fail-open).
        """
        def crashing_main():
            raise RuntimeError("test crash")

        env = {k: v for k, v in os.environ.items()
               if k not in ("AGENT_TOOLKIT_STRICT", "AGENT_TOOLKIT_NO_STRICT")}
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            with patch.object(self.mod, "_resolve_crash_workspace",
                              return_value=workspace), \
                 patch.dict(os.environ, env, clear=True):
                rv = self.mod.run_main_safe(crashing_main)
            self.assertEqual(rv, 1, "v0.21 default → fail-closed (rc=1)")

    def test_no_strict_opt_out_crash_returns_rc0(self):
        """v0.21: AGENT_TOOLKIT_NO_STRICT=1 reverts to legacy fail-open."""
        def crashing_main():
            raise RuntimeError("test crash")

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            with patch.object(self.mod, "_resolve_crash_workspace",
                              return_value=workspace), \
                 patch.dict(os.environ, {"AGENT_TOOLKIT_NO_STRICT": "1"}):
                rv = self.mod.run_main_safe(crashing_main)
            self.assertEqual(rv, 0, "NO_STRICT opt-out → rc=0 (fail-open)")


if __name__ == "__main__":
    unittest.main()
