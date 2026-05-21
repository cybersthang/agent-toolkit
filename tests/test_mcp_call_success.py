# -*- coding: utf-8 -*-
"""Success-path tests for mcp_call.py CLI bridge.

Sets up a tmp workspace with `.mcp.json` referencing
`tests/fixtures/fake_mcp_server.py` and asserts mcp_call.py:
  - rc=0 + stdout JSON containing stub result for normal tool call
  - rc=1 when fake server returns isError envelope
  - claude_cli opt-in env var falls back to direct-spawn if `claude`
    binary unavailable (typical CI env)

Closes the gap noted in v0.6.0 verify_report — previously only error
paths (rc=2 on bad JSON / unknown server) were tested.
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
MCP_CALL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "mcp_call.py"
FAKE_SERVER = TOOLKIT_ROOT / "tests" / "fixtures" / "fake_mcp_server.py"
PY = sys.executable


def _make_tmp_workspace(td: Path) -> Path:
    """Create a tmp project layout:

        <project>/
          .mcp.json
          .codex/tools/mcp_call.py
    """
    project = td / "proj"
    project.mkdir()
    tools_dir = project / ".codex" / "tools"
    tools_dir.mkdir(parents=True)
    shutil.copy2(str(MCP_CALL), str(tools_dir / "mcp_call.py"))

    mcp_config = {
        "mcpServers": {
            "fake": {
                "command": PY,
                "args": [str(FAKE_SERVER)],
            },
        }
    }
    (project / ".mcp.json").write_text(
        json.dumps(mcp_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return project


def _run_mcp_call(project: Path, args: list, env_extra: dict = None,
                  timeout: int = 30) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [PY, str(project / ".codex" / "tools" / "mcp_call.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(project),
        env=env,
    )


class TestMcpCallSuccessPath(unittest.TestCase):
    """Verify mcp_call.py against fake MCP server stub."""

    def test_success_tool_call_returns_rc_0_with_stub_result(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_workspace(Path(td))
            proc = _run_mcp_call(
                project,
                ["fake", "ping_tool", "--args", '{"sample": 42}'],
            )
            self.assertEqual(
                proc.returncode, 0,
                "Expected rc=0; stdout=%r stderr=%r" % (proc.stdout, proc.stderr),
            )
            self.assertIn("stub-ok", proc.stdout)
            # Echoed args should appear
            try:
                parsed = json.loads(proc.stdout)
                self.assertEqual(parsed.get("tool"), "ping_tool")
                self.assertEqual(parsed.get("echo"), {"sample": 42})
                self.assertTrue(parsed.get("stub"))
            except json.JSONDecodeError:
                self.fail("stdout was not valid JSON: %r" % proc.stdout)

    def test_iserror_response_returns_rc_1(self):
        """Fake server with FAKE_MCP_RETURN_ERROR=1 should produce
        result.isError=True → mcp_call rc=1."""
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_workspace(Path(td))
            proc = _run_mcp_call(
                project,
                ["fake", "any_tool", "--args", "{}"],
                env_extra={"FAKE_MCP_RETURN_ERROR": "1"},
            )
            self.assertEqual(proc.returncode, 1,
                             "Expected rc=1 on isError; stdout=%r" % proc.stdout)
            self.assertIn("stub-error", proc.stdout)


class TestClaudeCliOptIn(unittest.TestCase):
    """When TOOLKIT_MCP_CLIENT=claude_cli but `claude` binary is
    missing, mcp_call should fall through to direct-spawn (transparent
    fallback)."""

    def test_claude_cli_opt_in_falls_back_when_binary_missing(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_tmp_workspace(Path(td))
            # Empty PATH on Windows would still hit System32; instead
            # rely on the fact that no `claude` binary is installed on
            # the typical CI box. _via_claude_cli returns None →
            # fallthrough to direct-spawn.
            proc = _run_mcp_call(
                project,
                ["fake", "echo_tool", "--args", '{"x": 1}'],
                env_extra={"TOOLKIT_MCP_CLIENT": "claude_cli"},
            )
            self.assertEqual(
                proc.returncode, 0,
                "Expected rc=0 fallthrough; stderr=%r" % proc.stderr,
            )
            self.assertIn("stub-ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
