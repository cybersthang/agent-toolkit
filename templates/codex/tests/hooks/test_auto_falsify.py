"""auto_falsify pre-commit hook tests."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".codex" / "precommit_hooks" / "auto_falsify.py"
PY = sys.executable


def _run_hook(files: List[str], cwd: Path = REPO_ROOT, extra_env: dict = None) -> Tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [PY, str(HOOK)] + files,
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(cwd),
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


class TestAutoFalsifyHook(unittest.TestCase):

    def test_01_no_matching_probe_allows(self):
        # README.md doesn't match any probe path_globs.
        rc, _, _ = _run_hook(["README.md"])
        self.assertEqual(rc, 0)

    def test_02_no_files_allows(self):
        rc, _, _ = _run_hook([])
        self.assertEqual(rc, 0)

    def test_03_disable_via_env_skips(self):
        # Even if a probe would match, AGENT_TOOLKIT_DISABLE=1 short-circuits.
        rc, _, _ = _run_hook(
            ["app-server/addons/sample_module/controllers/profiler.py"],
            extra_env={"AGENT_TOOLKIT_DISABLE": "1"},
        )
        self.assertEqual(rc, 0)


class TestAutoFalsifyLogic(unittest.TestCase):
    """Unit-test the path matching + stub skip logic directly."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("auto_falsify_under_test", str(HOOK))
        self.mod = importlib.util.module_from_spec(spec)
        sys.modules["auto_falsify_under_test"] = self.mod
        spec.loader.exec_module(self.mod)

    def test_01_path_glob_match(self):
        self.assertTrue(self.mod._matches_any("app/controllers/foo.py", ["app/controllers/**.py"]))
        # ** requires intermediate path component to fnmatch — use **/*.py with subdir
        self.assertTrue(self.mod._matches_any("app-server/addons/sample_module/sub/x.py",
                                              ["app-server/addons/sample_module/**/*.py"]))

    def test_02_path_glob_no_match(self):
        self.assertFalse(self.mod._matches_any("tests/test_x.py", ["app/controllers/**.py"]))

    def test_03_empty_globs_no_match(self):
        self.assertFalse(self.mod._matches_any("x.py", []))


if __name__ == "__main__":
    unittest.main()
