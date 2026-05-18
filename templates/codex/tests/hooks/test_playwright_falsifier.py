"""playwright falsifier tests — schema validation + sandbox + dry-run.

Cannot exercise live `npx playwright test` in CI (no browser binaries
guaranteed). Tests focus on:
  - Config parsing (browser, timeout_ms, workers, headed)
  - Schema validation (spec_file required, browser must be valid)
  - Sandbox: `npx` is whitelisted
  - Dry-run command construction
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / ".codex" / "tools" / "falsify.py"
PROBES_PATH = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"
PY = sys.executable


def _load_falsify():
    spec = importlib.util.spec_from_file_location("falsify_pw_under_test", str(CLI))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["falsify_pw_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _add_temp_probe(probe: dict) -> None:
    """Inject a probe into the real acceptance-probes.json for testing."""
    data = json.loads(PROBES_PATH.read_text(encoding="utf-8-sig"))
    data["probes"].append(probe)
    PROBES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")


def _remove_temp_probe(probe_id: str) -> None:
    data = json.loads(PROBES_PATH.read_text(encoding="utf-8-sig"))
    data["probes"] = [p for p in data["probes"] if p.get("id") != probe_id]
    PROBES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")


class TestPlaywrightSchema(unittest.TestCase):

    def setUp(self):
        self.f = _load_falsify()

    def test_01_npx_in_allowed_binaries(self):
        self.assertIn("npx", self.f._ALLOWED_BINARIES)

    def test_02_node_in_allowed_binaries(self):
        self.assertIn("node", self.f._ALLOWED_BINARIES)

    def test_03_playwright_direct_in_allowed(self):
        self.assertIn("playwright", self.f._ALLOWED_BINARIES)

    def test_04_npx_command_passes_sandbox(self):
        cmd = "npx playwright test tests/foo.spec.ts --reporter=json"
        err = self.f._validate_command(cmd)
        self.assertIsNone(err)


class TestPlaywrightDryRun(unittest.TestCase):
    """End-to-end via CLI subprocess: register probe, run --dry-run, cleanup."""

    PROBE_ID = "test-playwright-dryrun"

    def setUp(self):
        _add_temp_probe({
            "id": self.PROBE_ID,
            "description": "test playwright dry-run",
            "applies_when": {"path_globs": ["app-server/addons/**.py"]},
            "evidence": {"required_tools": ["mcp__realdata_test__run_smoke_test"]},
            "falsification": {
                "type": "playwright",
                "description": "Run E2E spec",
                "runner": {
                    "spec_file": "tests/e2e/dummy.spec.ts",
                    "browser": "chromium",
                    "timeout_ms": 15000,
                    "workers": 1,
                    "headed": False,
                },
            },
            "severity": "warn",
        })

    def tearDown(self):
        _remove_temp_probe(self.PROBE_ID)

    def test_01_dry_run_succeeds(self):
        proc = subprocess.run(
            [PY, str(CLI), "--probe", self.PROBE_ID, "--dry-run"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("DRY RUN", proc.stdout)
        self.assertIn("playwright", proc.stdout)
        self.assertIn("chromium", proc.stdout)
        self.assertIn("--workers=1", proc.stdout)

    def test_02_dry_run_invalid_browser_rejects(self):
        _remove_temp_probe(self.PROBE_ID)
        _add_temp_probe({
            "id": self.PROBE_ID,
            "description": "invalid browser test",
            "applies_when": {"path_globs": ["app-server/addons/**.py"]},
            "evidence": {"required_tools": ["mcp__realdata_test__run_smoke_test"]},
            "falsification": {
                "type": "playwright",
                "runner": {
                    "spec_file": "tests/e2e/x.spec.ts",
                    "browser": "edge",  # not valid
                },
            },
            "severity": "warn",
        })
        proc = subprocess.run(
            [PY, str(CLI), "--probe", self.PROBE_ID, "--dry-run"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid", proc.stderr.lower())

    def test_03_dry_run_missing_spec_file_field_rejects(self):
        _remove_temp_probe(self.PROBE_ID)
        _add_temp_probe({
            "id": self.PROBE_ID,
            "description": "missing spec",
            "applies_when": {"path_globs": ["app-server/addons/**.py"]},
            "evidence": {"required_tools": ["mcp__realdata_test__run_smoke_test"]},
            "falsification": {
                "type": "playwright",
                "runner": {"browser": "chromium"},  # no spec_file
            },
            "severity": "warn",
        })
        proc = subprocess.run(
            [PY, str(CLI), "--probe", self.PROBE_ID, "--dry-run"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("spec_file", proc.stderr)


class TestPlaywrightDispatch(unittest.TestCase):
    """Verify the main dispatch recognizes 'playwright' type."""

    def test_01_unknown_type_still_rejected(self):
        # Register probe with bogus type → falsify should print supported types
        PROBE_ID = "test-bogus-type"
        _add_temp_probe({
            "id": PROBE_ID,
            "description": "bogus",
            "applies_when": {"path_globs": ["x"]},
            "evidence": {"required_tools": []},
            "falsification": {"type": "magic_pixie_dust"},
            "severity": "warn",
        })
        try:
            proc = subprocess.run(
                [PY, str(CLI), "--probe", PROBE_ID, "--dry-run"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 2)
            # Error message lists playwright as one of the supported types
            self.assertIn("playwright", proc.stderr)
        finally:
            _remove_temp_probe(PROBE_ID)


if __name__ == "__main__":
    unittest.main()
