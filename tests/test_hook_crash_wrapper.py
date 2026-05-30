# -*- coding: utf-8 -*-
"""Tests for P9 v0.8.0 — _common.run_main_safe + hook crash log ring buffer."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
COMMON = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "_common.py"


def _load_common():
    """Load _common module fresh per test (so internal state isolated)."""
    spec = importlib.util.spec_from_file_location("_common_under_test", str(COMMON))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_common_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestRunMainSafe(unittest.TestCase):

    def setUp(self):
        self.mod = _load_common()

    def test_normal_main_returns_value(self):
        def my_main():
            return 0
        rv = self.mod.run_main_safe(my_main)
        self.assertEqual(rv, 0)

    def test_main_returning_non_int_coerces_to_0(self):
        def my_main():
            return None
        rv = self.mod.run_main_safe(my_main)
        self.assertEqual(rv, 0)

    def test_sys_exit_honored(self):
        def my_main():
            sys.exit(0)
        rv = self.mod.run_main_safe(my_main)
        self.assertEqual(rv, 0)

    def test_crash_caught_and_logs(self):
        """v0.21: Default is now fail-CLOSED (rc=1). Crash still logged.
        Set AGENT_TOOLKIT_NO_STRICT=1 to revert to legacy fail-open (rc=0).
        """
        def my_main():
            raise RuntimeError("test crash")

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".agent-toolkit").mkdir()
            # Patch crash log workspace resolution + opt out of strict
            # to preserve legacy fail-open assertion semantics.
            with patch.object(self.mod, "_resolve_crash_workspace",
                              return_value=workspace), \
                 patch.dict(os.environ, {"AGENT_TOOLKIT_NO_STRICT": "1"}):
                rv = self.mod.run_main_safe(my_main)
            self.assertEqual(rv, 0, "NO_STRICT opt-out → rc=0 (fail-open)")
            log_path = workspace / ".agent-toolkit" / ".hook_crash_log.json"
            self.assertTrue(log_path.exists(), "Crash log file should be written")
            data = json.loads(log_path.read_text(encoding="utf-8"))
            events = data.get("events") or []
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["exc_type"], "RuntimeError")
            self.assertIn("test crash", events[0]["exc_msg"])


class TestAllHooksUseRunMainSafe(unittest.TestCase):
    """v0.8.1 — every shipped hook must import run_main_safe AND
    invoke it from `__main__` block. Closes P9 broken in v0.8.0
    where wrapper was defined but never applied."""

    HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
    EXCLUDED = {"_common.py", "_patterns.py", "__init__.py"}

    def _hook_files(self):
        for p in sorted(self.HOOKS_DIR.glob("*.py")):
            # Skip library modules: explicit excludes + any `_`-prefixed file
            # (e.g. _common, _patterns, _resume_state) — these are not hooks
            # and have no main()/run_main_safe wrapper.
            if p.name in self.EXCLUDED or p.name.startswith("_"):
                continue
            yield p

    def test_all_hooks_import_run_main_safe(self):
        missing = []
        for p in self._hook_files():
            src = p.read_text(encoding="utf-8")
            if "run_main_safe" not in src:
                missing.append(p.name)
        self.assertEqual(missing, [],
                         f"Hooks missing run_main_safe import: {missing}")

    def test_all_hooks_call_wrapper_in_main_block(self):
        missing = []
        import re
        pat = re.compile(
            r"if __name__ == [\"\']__main__[\"\']:\s*\n\s*sys\.exit\(run_main_safe\([\w]+\)\)",
            re.MULTILINE,
        )
        for p in self._hook_files():
            src = p.read_text(encoding="utf-8")
            if not pat.search(src):
                missing.append(p.name)
        self.assertEqual(missing, [],
                         f"Hooks not calling run_main_safe in __main__: {missing}")


if __name__ == "__main__":
    unittest.main()
