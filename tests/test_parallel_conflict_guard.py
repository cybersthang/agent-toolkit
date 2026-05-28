"""Tests for v0.25.0 parallel-subagent-guard (us1-us7).

Covers:
  - TestSkill           (us1)  — SKILL.md exists + has 5-step template.
  - TestWaveCli         (us2)  — emit/show/clear round-trip + schema.
  - TestGuard           (us3+us4+us5) — cross-zone block / same-owner allow / outside silent.
  - TestLifecycle       (us6)  — clear, TTL expire, bypass token.
  - TestBypass          (T1)   — intent_router bypass-parallel-guard capture.
  - cross-platform (us7) — implicit: every test runs on the CI matrix.

Run: pytest tests/test_parallel_conflict_guard.py -v
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
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "parallel_conflict_guard.py"
WAVE_CLI = TOOLKIT_ROOT / "tools" / "parallel_wave.py"
INTENT_ROUTER = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "intent_router.py"
SKILL = TOOLKIT_ROOT / "templates" / "cursor" / "skills" / "_common" / "parallel-batching" / "SKILL.md"
PY = os.environ.get("PYTHON_BIN", sys.executable)

MANIFEST_REL = ".agent-toolkit/.parallel_wave.json"
TOKEN_REL = ".agent-toolkit/.skip_parallel_guard_next.json"


def _run_hook(workspace: Path, envelope: dict,
              extra_env: dict = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    env.pop("AGENT_TOOLKIT_STRICT", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, env=env, cwd=str(workspace),
    )


def _run_cli(workspace: Path, args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(WAVE_CLI), "--project-dir", str(workspace), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, cwd=str(workspace),
    )


def _seed_manifest(workspace: Path, zones: list, wave: str = "w1",
                   wave_done: bool = False, ttl: int = 3600,
                   created_offset: int = 0) -> Path:
    p = workspace / MANIFEST_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "version": 1, "wave": wave,
        "created_ts": int(time.time()) + created_offset,
        "ttl_seconds": ttl, "zones": zones, "wave_done": wave_done,
    }, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return tmp_path


# -----------------------------------------------------------------------------
class TestSkill:
    """us1 — Skill ship 5-step template + frontmatter."""

    def test_skill_md_has_template(self):
        assert SKILL.exists(), f"Skill file missing: {SKILL}"
        txt = SKILL.read_text(encoding="utf-8")
        # Frontmatter contract.
        assert txt.startswith("---\nname: parallel-batching")
        assert "description:" in txt
        # 5 steps documented.
        for marker in ("Step 1", "Step 2", "Step 3", "Step 4", "Step 5"):
            assert marker in txt, f"missing {marker}"
        # CLI invocation example.
        assert "tools/parallel_wave.py emit" in txt
        # Anti-pattern table.
        assert "Anti-pattern" in txt or "Anti-patterns" in txt


# -----------------------------------------------------------------------------
class TestWaveCli:
    """us2 — CLI emit/show/clear round-trip + schema."""

    def test_emit_writes_valid_manifest(self, ws):
        r = _run_cli(ws, ["emit", "--wave", "w1",
                          "--zone", "agent-a:src/a.py,src/b.py",
                          "--zone", "agent-b:tests/test_a.py",
                          "--ttl", "1800"])
        assert r.returncode == 0, r.stderr
        data = json.loads((ws / MANIFEST_REL).read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["wave"] == "w1"
        assert data["ttl_seconds"] == 1800
        assert data["wave_done"] is False
        ids = [z["agent_id"] for z in data["zones"]]
        assert ids == ["agent-a", "agent-b"]
        assert data["zones"][0]["owned"] == ["src/a.py", "src/b.py"]
        assert data["zones"][1]["owned"] == ["tests/test_a.py"]

    def test_show_round_trip(self, ws):
        _run_cli(ws, ["emit", "--wave", "w2",
                      "--zone", "x:p1"])
        r = _run_cli(ws, ["show"])
        assert r.returncode == 0
        parsed = json.loads(r.stdout)
        assert parsed["wave"] == "w2"

    def test_clear_removes(self, ws):
        _run_cli(ws, ["emit", "--wave", "w3", "--zone", "x:p"])
        assert (ws / MANIFEST_REL).exists()
        r = _run_cli(ws, ["clear"])
        assert r.returncode == 0
        assert not (ws / MANIFEST_REL).exists()

    def test_declare_done_flips_flag(self, ws):
        _run_cli(ws, ["emit", "--wave", "w4", "--zone", "x:p"])
        r = _run_cli(ws, ["declare-done"])
        assert r.returncode == 0
        data = json.loads((ws / MANIFEST_REL).read_text(encoding="utf-8"))
        assert data["wave_done"] is True


# -----------------------------------------------------------------------------
class TestGuard:
    """us3 / us4 / us5 — block / allow / silent."""

    def _envelope(self, ws: Path, file_rel: str, agent_id=None,
                  tool="Edit"):
        env = {
            "tool_name": tool,
            "tool_input": {"file_path": str(ws / file_rel)},
            "cwd": str(ws),
        }
        if agent_id is not None:
            env["agent_id"] = agent_id
        return env

    def test_cross_zone_block_subagent_to_subagent(self, ws):
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["src/a.py"]},
            {"agent_id": "agent-b", "owned": ["src/b.py"]},
        ])
        r = _run_hook(ws, self._envelope(ws, "src/a.py", agent_id="agent-b"))
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "agent-a" in payload["hookSpecificOutput"]["permissionDecisionReason"]

    def test_cross_zone_block_main_to_subagent(self, ws):
        # D8: main agent (no agent_id) editing a sub-agent's zone → block.
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["src/a.py"]},
        ])
        r = _run_hook(ws, self._envelope(ws, "src/a.py", agent_id=None))
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_same_owner_allow(self, ws):
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["src/a.py"]},
        ])
        r = _run_hook(ws, self._envelope(ws, "src/a.py", agent_id="agent-a"))
        assert r.returncode == 0
        assert r.stdout.strip() == "", "same-owner = silent allow"

    def test_outside_zone_silent(self, ws):
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["src/a.py"]},
        ])
        r = _run_hook(ws, self._envelope(ws, "totally/unrelated.py", agent_id="agent-b"))
        assert r.returncode == 0
        assert r.stdout.strip() == ""
        assert r.stderr.strip() == ""

    def test_no_manifest_silent(self, ws):
        r = _run_hook(ws, self._envelope(ws, "src/a.py", agent_id="agent-x"))
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_glob_pattern_matches(self, ws):
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["templates/claude/hooks/*_gate.py"]},
        ])
        # File matching glob, edited by foreign agent → block.
        r = _run_hook(ws, self._envelope(
            ws, "templates/claude/hooks/foo_gate.py", agent_id="agent-b"))
        payload = json.loads(r.stdout) if r.stdout.strip() else {}
        assert payload.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    def test_dir_prefix_matches(self, ws):
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["templates/claude/hooks/"]},
        ])
        r = _run_hook(ws, self._envelope(
            ws, "templates/claude/hooks/anything.py", agent_id="agent-b"))
        payload = json.loads(r.stdout) if r.stdout.strip() else {}
        assert payload.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    def test_non_edit_tool_skipped(self, ws):
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["src/a.py"]},
        ])
        env = self._envelope(ws, "src/a.py", agent_id="agent-b", tool="Read")
        r = _run_hook(ws, env)
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_kill_switch(self, ws):
        _seed_manifest(ws, [
            {"agent_id": "agent-a", "owned": ["src/a.py"]},
        ])
        r = _run_hook(ws, self._envelope(ws, "src/a.py", agent_id="agent-b"),
                      extra_env={"AGENT_TOOLKIT_DISABLE": "1"})
        assert r.returncode == 0
        assert r.stdout.strip() == ""


# -----------------------------------------------------------------------------
class TestLifecycle:
    """us6 — clear / TTL / wave_done / bypass."""

    def _envelope(self, ws: Path):
        return {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(ws / "src/a.py")},
            "cwd": str(ws),
            "agent_id": "agent-b",
        }

    def test_wave_done_silent(self, ws):
        _seed_manifest(ws, [{"agent_id": "agent-a", "owned": ["src/a.py"]}],
                       wave_done=True)
        r = _run_hook(ws, self._envelope(ws))
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_ttl_expired_silent(self, ws):
        # Created 2h ago with ttl=1h → expired.
        _seed_manifest(ws, [{"agent_id": "agent-a", "owned": ["src/a.py"]}],
                       ttl=3600, created_offset=-7200)
        r = _run_hook(ws, self._envelope(ws))
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_clear_via_cli(self, ws):
        _seed_manifest(ws, [{"agent_id": "agent-a", "owned": ["src/a.py"]}])
        _run_cli(ws, ["clear"])
        r = _run_hook(ws, self._envelope(ws))
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_bypass_token_allows_then_consumed(self, ws):
        _seed_manifest(ws, [{"agent_id": "agent-a", "owned": ["src/a.py"]}])
        # Seed a fresh bypass token.
        tok = ws / TOKEN_REL
        tok.parent.mkdir(parents=True, exist_ok=True)
        tok.write_text(json.dumps({"ts": int(time.time()),
                                   "reason": "emergency-test"}),
                       encoding="utf-8")
        r = _run_hook(ws, self._envelope(ws))
        assert r.returncode == 0
        assert r.stdout.strip() == "", "bypass = silent allow"
        # Token consumed.
        assert not tok.exists()


# -----------------------------------------------------------------------------
class TestBypass:
    """T1 — intent_router writes the token on `bypass-parallel-guard:` prompt."""

    def test_token_capture_and_consume(self, ws):
        env = os.environ.copy()
        env.pop("AGENT_TOOLKIT_DISABLE", None)
        prompt = "bypass-parallel-guard: planning-a-rare-cross-edit"
        envelope = {"prompt": prompt, "cwd": str(ws)}
        r = subprocess.run(
            [PY, str(INTENT_ROUTER)],
            input=json.dumps(envelope),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10, env=env, cwd=str(ws),
        )
        assert r.returncode == 0
        tok = ws / TOKEN_REL
        assert tok.exists(), "intent_router must write the bypass token"
        data = json.loads(tok.read_text(encoding="utf-8"))
        assert data["reason"] == "planning-a-rare-cross-edit"
