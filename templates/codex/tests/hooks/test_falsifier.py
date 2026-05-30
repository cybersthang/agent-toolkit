"""Falsifier CLI tests — injection logic + restoration + delta compare.

Live measurement (curl etc.) NOT exercised — those depend on a running
service. We test the file-mutation logic against a controlled fixture.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / ".codex" / "tools" / "falsify.py"
PY = sys.executable


def _read_falsify_module():
    """Import the falsify module by path for direct unit testing."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("falsify_under_test", str(CLI))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["falsify_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFalsifierInjection(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="falsify_test_"))
        self.fixture = self.tmp / "controller.py"
        self.fixture.write_text(
            "class Web:\n"
            "    def load_views(self, model, views):\n"
            "        return self._load(model, views)\n"
            "\n"
            "    def other(self):\n"
            "        return None\n",
            encoding="utf-8",
        )
        self.falsify = _read_falsify_module()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_inject_then_restore(self):
        original = self.fixture.read_text(encoding="utf-8")
        backup = self.falsify._inject_sleep(
            self.fixture, r"def load_views\(", 2.0, inject_after_match=True,
        )
        modified = self.fixture.read_text(encoding="utf-8")
        self.assertIn("_falsify_time.sleep(2.0)", modified)
        # Restore
        self.falsify._restore(self.fixture, backup)
        restored = self.fixture.read_text(encoding="utf-8")
        self.assertEqual(original, restored)
        self.assertFalse(backup.exists())

    def test_02_inject_missing_pattern_raises(self):
        with self.assertRaises(RuntimeError):
            self.falsify._inject_sleep(
                self.fixture, r"def NONEXISTENT\(", 2.0,
            )

    def test_03_inject_only_first_match(self):
        # Fixture has two `def `; pattern should match only `load_views`.
        backup = self.falsify._inject_sleep(
            self.fixture, r"def load_views\(", 1.0, inject_after_match=True,
        )
        modified = self.fixture.read_text(encoding="utf-8")
        # Sleep injected exactly once.
        count = modified.count("_falsify_time.sleep(")
        self.assertEqual(count, 1)
        self.falsify._restore(self.fixture, backup)


class TestFalsifierCLI(unittest.TestCase):

    def test_01_dry_run_real_probe(self):
        """Dry-run on the registered load-views-blocking probe should print
        config without executing commands."""
        proc = subprocess.run(
            [PY, str(CLI), "--probe", "load-views-blocking", "--dry-run"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("DRY RUN", proc.stdout)
        self.assertIn("load-views-blocking", proc.stdout)

    def test_02_unknown_probe_exits_2(self):
        proc = subprocess.run(
            [PY, str(CLI), "--probe", "does-not-exist", "--dry-run"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
