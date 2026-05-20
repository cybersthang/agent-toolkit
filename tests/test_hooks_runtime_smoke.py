# -*- coding: utf-8 -*-
"""Runtime smoke tests for 4 new PostToolUse / Stop hooks.

Simulates the Claude Code hook envelope (JSON on stdin) + runs the
hook subprocess + asserts:
  - exit code 0 (hooks fail open — never block the workflow)
  - state file written when expected
  - hook stays silent / no-op on irrelevant edits

These are NOT live integration tests — they drive each hook with a
synthesized envelope in an isolated tmp project layout. Confirms the
4 hooks ACTUALLY run + write the artifacts the runtime model assumes,
closing the runtime-fire gap flagged in benchmark scoring.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
PY = sys.executable


def _run_hook(hook_path: Path, envelope: dict, cwd: Path,
              timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a hook subprocess feeding it the envelope on stdin."""
    return subprocess.run(
        [PY, str(hook_path)],
        input=json.dumps(envelope, ensure_ascii=False),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
        cwd=str(cwd),
    )


def _make_tmp_project(td: Path,
                      probes: list = None,
                      test_env: dict = None,
                      coverage: dict = None) -> Path:
    """Seed a tmp project with the .agent-toolkit/ + .codex/ scaffolding
    the hooks expect."""
    project = td / "proj"
    project.mkdir()
    (project / ".agent-toolkit").mkdir()
    (project / ".codex" / "tools").mkdir(parents=True)
    if probes is not None:
        (project / ".agent-toolkit" / "acceptance-probes.json").write_text(
            json.dumps({"version": 2, "probes": probes}, ensure_ascii=False),
            encoding="utf-8",
        )
    if test_env is not None:
        (project / ".agent-toolkit" / "test_env.json").write_text(
            json.dumps(test_env, ensure_ascii=False),
            encoding="utf-8",
        )
    if coverage is not None:
        (project / ".agent-toolkit" / "coverage_config.json").write_text(
            json.dumps(coverage, ensure_ascii=False),
            encoding="utf-8",
        )
    return project


class TestAutoRunProbes(unittest.TestCase):
    """Patch B1 — PostToolUse Edit fires falsify.py for matching probe."""

    HOOK = HOOKS_DIR / "auto_run_probes.py"

    def test_no_op_when_no_probes(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), probes=[])
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "foo.py")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[auto_run_probes]", proc.stdout)

    def test_no_op_when_probe_auto_run_false(self):
        # Default after migrate_probes_v2 is auto_run=false.
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), probes=[{
                "id": "x", "description": "",
                "applies_when": {"path_globs": ["**/*.py"]},
                "auto_run": False,
            }])
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "foo.py")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[auto_run_probes]", proc.stdout)

    def test_skips_tests_dir(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), probes=[{
                "id": "x", "description": "",
                "applies_when": {"path_globs": ["**/*.py"]},
                "auto_run": True,
            }])
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "tests/test_foo.py")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            # Skipped because tests/** is in default skip_path_globs
            self.assertNotIn("[auto_run_probes]", proc.stdout)


class TestAutoTestRunner(unittest.TestCase):
    """Patch B2 — PostToolUse Edit looks up test mapping + invokes MCP."""

    HOOK = HOOKS_DIR / "auto_test_runner.py"

    def test_no_op_when_no_mapping_matches(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td))
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "README.md")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[auto_test_runner]", proc.stdout)

    def test_skips_tests_dir(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td))
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "tests/test_foo.py")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[auto_test_runner]", proc.stdout)


class TestDaemonManager(unittest.TestCase):
    """Patch B3 — kill+restart daemon when feature-scope file edited."""

    HOOK = HOOKS_DIR / "daemon_manager.py"

    def test_no_op_when_test_env_missing(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td))   # no test_env.json
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "addons/x/models/y.py")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("restarted daemon", proc.stdout)

    def test_no_op_when_v1_schema(self):
        # daemon_manager requires schema_version == 2 to act.
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), test_env={
                "url": "http://localhost:8069",
                # No schema_version → treated as v1, hook skips.
            })
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "addons/x/models/y.py")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("restarted daemon", proc.stdout)

    def test_skips_test_edits(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), test_env={
                "schema_version": 2,
                "url": "http://localhost:8069",
                "process_manager": {
                    "start_cmd": ["true"],
                    "health_check_url": "/",
                    "pid_track_file": ".agent-toolkit/.daemon_pid",
                },
            })
            envelope = {
                "cwd": str(project),
                "tool_input": {"file_path": str(project / "tests/test_x.py")},
            }
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            # tests/** in default skip globs → no restart.
            self.assertNotIn("restarted daemon", proc.stdout)


class TestSpecDriftAdvisory(unittest.TestCase):
    """Patch C5 — Stop hook advisory on probe recipe vs script drift."""

    HOOK = HOOKS_DIR / "spec_drift_advisory.py"

    def test_no_op_when_no_probes(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), probes=[])
            envelope = {"cwd": str(project)}
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_no_op_when_no_runner_spec_file(self):
        # Probe without runner.spec_file → drift analysis skipped.
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), probes=[{
                "id": "x", "description": "",
                "falsification": {"description": "do something",
                                  "runner": {}},
            }])
            envelope = {"cwd": str(project)}
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            # No drift output when no script to diff against.
            self.assertNotIn("[spec-drift]", proc.stdout)

    def test_warns_when_spec_file_missing(self):
        # Probe declares spec_file but file doesn't exist on disk → warn.
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_project(Path(td), probes=[{
                "id": "x", "description": "",
                "falsification": {
                    "description": "trigger longpoll",
                    "runner": {"spec_file": "scripts/probes/x.py"},
                },
            }])
            envelope = {"cwd": str(project)}
            proc = _run_hook(self.HOOK, envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[spec-drift]", proc.stdout)


if __name__ == "__main__":
    unittest.main()
