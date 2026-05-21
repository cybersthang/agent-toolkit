# -*- coding: utf-8 -*-
"""Integration tests for 3 PostToolUse hooks (wire-level contract).

Goes beyond exit-code smoke tests (test_hooks_runtime_smoke.py) by
verifying the actual payload each hook sends to its subprocess:

  - auto_test_runner → mcp_call.py: assert correct server + tool +
    args_json shape (module_name resolution, allow_db_write flag,
    test_tag template).
  - auto_run_probes → falsify.py: assert probe id is passed in argv +
    state file gets updated with verdict.
  - debounce: assert second invocation within debounce window is no-op.

Recording fixtures:
  tests/fixtures/recording_mcp_call.py
  tests/fixtures/recording_falsify.py

Each fixture records argv to RECORDING_FILE env var (JSON list). Tests
inspect the recorded calls.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
FIXTURES = TOOLKIT_ROOT / "tests" / "fixtures"
PY = sys.executable


def _make_tmp_project(td: Path, probes: list = None,
                      with_recording_mcp_call: bool = False,
                      with_recording_falsify: bool = False,
                      mappings: list = None) -> tuple:
    """Seed tmp workspace with .agent-toolkit/ + .codex/tools/ recording
    stubs. Returns (project, recording_file_path)."""
    project = td / "proj"
    project.mkdir()
    (project / ".agent-toolkit").mkdir()
    (project / ".codex" / "tools").mkdir(parents=True)

    if with_recording_mcp_call:
        shutil.copy2(
            str(FIXTURES / "recording_mcp_call.py"),
            str(project / ".codex" / "tools" / "mcp_call.py"),
        )
    if with_recording_falsify:
        shutil.copy2(
            str(FIXTURES / "recording_falsify.py"),
            str(project / ".codex" / "tools" / "falsify.py"),
        )

    if probes is not None:
        (project / ".agent-toolkit" / "acceptance-probes.json").write_text(
            json.dumps({"version": 2, "probes": probes}, ensure_ascii=False),
            encoding="utf-8",
        )

    if mappings is not None:
        (project / ".agent-toolkit" / "auto_test.json").write_text(
            json.dumps({
                "enabled": True,
                "debounce_s": 10,
                "mcp_server": "realdata_test",
                "mcp_tool": "run_module_test",
                "test_mappings": mappings,
                "skip_path_globs": ["**/tests/**"],
                "state_file": ".agent-toolkit/.auto_test_state.json",
                "timeout_s": 60,
            }, ensure_ascii=False),
            encoding="utf-8",
        )

    rec = project / "recording.json"
    return project, rec


def _run_hook(hook_path: Path, envelope: dict, cwd: Path, env_extra: dict = None,
              timeout: int = 30) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [PY, str(hook_path)],
        input=json.dumps(envelope, ensure_ascii=False),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
        cwd=str(cwd),
        env=env,
    )


class TestAutoTestRunnerIntegration(unittest.TestCase):
    """auto_test_runner sends correct MCP payload to mcp_call.py."""

    HOOK = HOOKS_DIR / "auto_test_runner.py"

    def test_mcp_called_with_module_name_resolved(self):
        with tempfile.TemporaryDirectory() as td:
            project, rec = _make_tmp_project(
                Path(td),
                with_recording_mcp_call=True,
                mappings=[{
                    "src_regex": r"addons/(?P<module>[^/]+)/models/[^/]+\.py$",
                    "mcp_args_template": {
                        "module_name": "{module_name}",
                        "module_action": "update",
                        "allow_db_write": True,
                        "test_tag": "/{module_name}",
                    },
                    "module_name_from": "module_basename",
                }],
            )
            envelope = {
                "cwd": str(project),
                "tool_input": {
                    "file_path": str(project / "addons/widgets/models/widget.py"),
                },
            }
            proc = _run_hook(
                self.HOOK, envelope, project,
                env_extra={"RECORDING_FILE": str(rec)},
            )
            self.assertEqual(proc.returncode, 0,
                             "stderr=%r stdout=%r" % (proc.stderr, proc.stdout))
            self.assertTrue(rec.exists(),
                            "Expected recording file but got stdout=%r" % proc.stdout)
            recorded = json.loads(rec.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(recorded), 1)
            call = recorded[0]
            argv = call["argv"]
            self.assertIn("realdata_test", argv)
            self.assertIn("run_module_test", argv)
            args_json = call.get("args_json") or {}
            self.assertEqual(args_json.get("module_name"), "widgets")
            self.assertEqual(args_json.get("module_action"), "update")
            self.assertTrue(args_json.get("allow_db_write"))
            self.assertEqual(args_json.get("test_tag"), "/widgets")

    def test_debounce_skips_second_call_within_window(self):
        with tempfile.TemporaryDirectory() as td:
            project, rec = _make_tmp_project(
                Path(td),
                with_recording_mcp_call=True,
                mappings=[{
                    "src_regex": r"addons/(?P<module>[^/]+)/models/[^/]+\.py$",
                    "mcp_args_template": {"module_name": "{module_name}"},
                    "module_name_from": "module_basename",
                }],
            )
            envelope = {
                "cwd": str(project),
                "tool_input": {
                    "file_path": str(project / "addons/widgets/models/widget.py"),
                },
            }
            # First call
            proc1 = _run_hook(self.HOOK, envelope, project,
                              env_extra={"RECORDING_FILE": str(rec)})
            self.assertEqual(proc1.returncode, 0)
            # Second call immediately — should be debounced
            proc2 = _run_hook(self.HOOK, envelope, project,
                              env_extra={"RECORDING_FILE": str(rec)})
            self.assertEqual(proc2.returncode, 0)
            recorded = json.loads(rec.read_text(encoding="utf-8"))
            self.assertEqual(len(recorded), 1,
                             "Expected only 1 mcp_call (debounced); got %d" % len(recorded))


class TestAutoRunProbesIntegration(unittest.TestCase):
    """auto_run_probes invokes falsify.py with the matched probe id."""

    HOOK = HOOKS_DIR / "auto_run_probes.py"

    def test_falsify_called_with_probe_id_for_matching_edit(self):
        with tempfile.TemporaryDirectory() as td:
            project, rec = _make_tmp_project(
                Path(td),
                with_recording_falsify=True,
                probes=[{
                    "id": "demo-probe",
                    "description": "Demo probe.",
                    "severity": "warn",
                    "auto_run": True,
                    "applies_when": {"path_globs": ["**/models/*.py"]},
                    "evidence": {"required_tools": ["code-grader"]},
                }],
            )
            envelope = {
                "cwd": str(project),
                "tool_input": {
                    "file_path": str(project / "addons/widgets/models/widget.py"),
                },
            }
            proc = _run_hook(
                self.HOOK, envelope, project,
                env_extra={"RECORDING_FILE": str(rec)},
            )
            self.assertEqual(proc.returncode, 0,
                             "stderr=%r stdout=%r" % (proc.stderr, proc.stdout))
            self.assertTrue(rec.exists(),
                            "Expected recording file; stdout=%r" % proc.stdout)
            recorded = json.loads(rec.read_text(encoding="utf-8"))
            self.assertEqual(len(recorded), 1)
            argv = recorded[0]["argv"]
            self.assertIn("--probe", argv)
            self.assertIn("demo-probe", argv)
            # auto_run_probes should also update state with verdict
            state_path = project / ".agent-toolkit" / ".auto_probes_state.json"
            self.assertTrue(state_path.exists())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("demo-probe", state)
            self.assertEqual(state["demo-probe"]["status"], "proven")


if __name__ == "__main__":
    unittest.main()
