"""Tests for git_guardrails.py PreToolUse(Bash) hook.

One test class per behavior bucket:
- allow_paths : reads / safe ops pass through.
- deny_paths  : destructive git ops are blocked.
- bypass      : single-use token grants exactly ONE pass.
- enforce_mode: `warn` / `off` per `.agent-toolkit/enforce_mode.json`.

Run: pytest tests/test_git_guardrails.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "git_guardrails.py"
# Portable fallback — `sys.executable` is the interpreter currently running
# pytest. Override via `PYTHON_BIN` env var for cross-venv test runs.
PY = os.environ.get("PYTHON_BIN", sys.executable)


def _run(workspace: Path, command: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    env.pop("AGENT_TOOLKIT_STRICT", None)
    envelope = {"tool_input": {"command": command}, "cwd": str(workspace)}
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True, text=True, env=env, timeout=10,
        cwd=str(workspace),
    )


def _decision(proc: subprocess.CompletedProcess) -> str:
    payload = json.loads(proc.stdout)
    return payload["hookSpecificOutput"]["permissionDecision"]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / ".agent-toolkit").mkdir()
    return tmp_path


class TestAllowPaths:
    def test_non_git_bash(self, workspace: Path):
        proc = _run(workspace, "ls -la")
        assert _decision(proc) == "allow"

    def test_git_status_readonly(self, workspace: Path):
        proc = _run(workspace, "git status")
        assert _decision(proc) == "allow"

    def test_git_log(self, workspace: Path):
        proc = _run(workspace, "git log --oneline -5")
        assert _decision(proc) == "allow"

    def test_git_diff(self, workspace: Path):
        proc = _run(workspace, "git diff HEAD")
        assert _decision(proc) == "allow"

    def test_empty_command(self, workspace: Path):
        proc = _run(workspace, "")
        assert _decision(proc) == "allow"

    def test_git_in_filename(self, workspace: Path):
        # Word boundary: `cat git_log.txt` is NOT a git command.
        proc = _run(workspace, "cat my_git_notes.txt")
        assert _decision(proc) == "allow"


class TestDenyPaths:
    @pytest.mark.parametrize("cmd,label", [
        ("git commit -m foo",          "git commit"),
        ("git commit --amend",         "git commit"),
        ("git push origin main",       "git push"),
        ("git push --force",           "git push"),
        ("git add .",                  "git add"),
        ("git add -A",                 "git add"),
        ("git reset --hard HEAD~1",    "git reset --hard"),
        ("git clean -fd",              "git clean -f"),
        ("git clean -f",               "git clean -f"),
        ("git branch -D feature",      "git branch -D"),
        ("git checkout .",             "git checkout ."),
        ("git restore .",              "git restore ."),
    ])
    def test_dangerous_blocked(self, workspace: Path, cmd: str, label: str):
        proc = _run(workspace, cmd)
        assert _decision(proc) == "deny", f"expected deny for {cmd!r}, got: {proc.stdout!r}"
        reason = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        assert label in reason

    def test_no_verify_flag_blocked(self, workspace: Path):
        # The --no-verify check fires; the specific match label may be
        # the commit verb (which is checked first) or the flag — either
        # is a valid block.
        proc = _run(workspace, "git commit -m x --no-verify")
        assert _decision(proc) == "deny"

    def test_chained_via_and(self, workspace: Path):
        # `pwd && git push` should still be caught — the regex anchors
        # on whitespace / `&&` / `||` / `;`.
        proc = _run(workspace, "pwd && git push origin main")
        assert _decision(proc) == "deny"


class TestBypass:
    def _drop_token(self, workspace: Path):
        (workspace / ".agent-toolkit" / ".skip_git_guard_next.json").write_text("{}")

    def test_token_grants_one_pass(self, workspace: Path):
        self._drop_token(workspace)
        proc = _run(workspace, "git add foo")
        assert _decision(proc) == "allow"

    def test_token_consumed_after_use(self, workspace: Path):
        self._drop_token(workspace)
        first = _run(workspace, "git add foo")
        assert _decision(first) == "allow"
        # Token should now be gone.
        token = workspace / ".agent-toolkit" / ".skip_git_guard_next.json"
        assert not token.exists()
        # Second call → block.
        second = _run(workspace, "git add foo")
        assert _decision(second) == "deny"

    def test_stale_token_does_not_bypass(self, workspace: Path):
        token = workspace / ".agent-toolkit" / ".skip_git_guard_next.json"
        token.write_text("{}")
        # Force mtime far in the past (TTL = 600s).
        old = time.time() - 3600
        os.utime(token, (old, old))
        proc = _run(workspace, "git push")
        assert _decision(proc) == "deny"
        # Stale token cleaned up on read.
        assert not token.exists()


class TestEnforceMode:
    def _write_mode(self, workspace: Path, mode: str):
        cfg = workspace / ".agent-toolkit" / "enforce_mode.json"
        cfg.write_text(json.dumps({"per_hook": {"git_guardrails": mode}}))

    def test_warn_mode_allows_with_reason(self, workspace: Path):
        self._write_mode(workspace, "warn")
        proc = _run(workspace, "git push origin main")
        payload = json.loads(proc.stdout)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert "warn" in payload["hookSpecificOutput"].get("permissionDecisionReason", "")

    def test_off_mode_silent_allow(self, workspace: Path):
        self._write_mode(workspace, "off")
        proc = _run(workspace, "git push origin main")
        payload = json.loads(proc.stdout)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"
        # `off` mode should not surface any reason — silent pass.
        assert "permissionDecisionReason" not in payload["hookSpecificOutput"]

    def test_default_is_block(self, workspace: Path):
        # No enforce_mode.json → git_guardrails defaults to `block`
        # (overrides toolkit-wide `warn` default per feedback_no_ai_commit).
        proc = _run(workspace, "git push origin main")
        assert _decision(proc) == "deny"
