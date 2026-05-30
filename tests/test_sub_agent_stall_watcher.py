"""Tests for v0.26.0 sub-agent-stall-watcher (extends v0.24 agent_supervisor).

Covers acceptance_evals us1-us7 per spec
specs/v0.26.0-sub-agent-stall-watcher.md. Multi-transcript mode auto-
activates when v0.25 `.parallel_wave.json` is active; notify-only, no
relaunch.

Run: pytest tests/test_sub_agent_stall_watcher.py -v
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import time
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / "tools"))
sys.path.insert(0, str(TOOLKIT_ROOT / "templates" / "claude" / "hooks"))

import agent_supervisor as sup  # noqa: E402
import notify  # noqa: E402


# -------- helpers --------------------------------------------------------

def _seed_autonomy(ws: Path, spec: str = "feat", hours: int = 1):
    from datetime import datetime, timedelta, timezone
    p = ws / ".agent-toolkit/.autonomy_active.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    exp = datetime.now(timezone.utc) + timedelta(hours=hours)
    p.write_text(json.dumps({"spec": spec, "expires_at": exp.isoformat()}),
                 encoding="utf-8")


def _seed_manifest(ws: Path, wave: str = "w1", ttl: int = 3600,
                   created_offset: int = 0, wave_done: bool = False):
    p = ws / ".agent-toolkit/.parallel_wave.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "version": 1, "wave": wave,
        "created_ts": int(time.time()) + created_offset,
        "ttl_seconds": ttl,
        "zones": [{"agent_id": "agent-a", "owned": ["src/a.py"]}],
        "wave_done": wave_done,
    }, ensure_ascii=False), encoding="utf-8")


def _projects_dir(tmp_root: Path, ws: Path) -> Path:
    """Return the dir where `discover_sub_agent_transcripts(projects_root=tmp_root)`
    will look — i.e. `<tmp_root>/<encoded-workspace>/`."""
    enc = sup.encode_project_path(ws)
    d = tmp_root / enc
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_jsonl(dir: Path, name: str, age_seconds: float) -> Path:
    p = dir / f"{name}.jsonl"
    p.write_text('{"type":"assistant"}\n', encoding="utf-8")
    past = time.time() - age_seconds
    os.utime(p, (past, past))
    return p


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return tmp_path


# -------- TestDiscovery (us1) -------------------------------------------

class TestDiscovery:
    """us1 — list *.jsonl in projects dir, mtime > created_ts, exclude main."""

    def test_lists_new_transcripts_only(self, ws, tmp_path):
        _seed_manifest(ws)
        manifest = json.loads(
            (ws / ".agent-toolkit/.parallel_wave.json").read_text(encoding="utf-8"))
        proj_root = tmp_path / "projects-root"
        proj_dir = _projects_dir(proj_root, ws)
        # Three jsonl: one OLD (pre-wave), one MAIN (newest mtime = main session),
        # one SUB (post-wave, not the main).
        _make_jsonl(proj_dir, "old", age_seconds=3600)        # pre-wave (> 1h old)
        _make_jsonl(proj_dir, "main", age_seconds=10)         # newest = main
        sub = _make_jsonl(proj_dir, "sub", age_seconds=60)    # post-wave, not main
        # Ensure manifest.created_ts ~ 2 minutes ago so 'old' (1h) is pre-wave.
        manifest["created_ts"] = int(time.time()) - 120
        (ws / ".agent-toolkit/.parallel_wave.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        found = sup.discover_sub_agent_transcripts(ws, manifest, projects_root=proj_root)
        found_names = {p.name for p in found}
        assert sub.name in found_names
        assert "main.jsonl" not in found_names, "main session must be excluded"
        assert "old.jsonl" not in found_names, "pre-wave file must be excluded"

    def test_no_projects_dir_returns_empty(self, ws, tmp_path):
        _seed_manifest(ws)
        manifest = json.loads(
            (ws / ".agent-toolkit/.parallel_wave.json").read_text(encoding="utf-8"))
        proj_root = tmp_path / "no-such-root"
        found = sup.discover_sub_agent_transcripts(ws, manifest, projects_root=proj_root)
        assert found == []

    def test_nested_subagents_layout_v0_27(self, ws, tmp_path):
        """v0.27 B2 fix — Claude Code's real layout is
        `<proj>/<sessionUUID>/subagents/agent-<hash>.jsonl`, NOT flat.
        Field-verified 2026-05-28 on /home/voducthang/Toolkit session."""
        _seed_manifest(ws, created_offset=-120)
        manifest = json.loads(
            (ws / ".agent-toolkit/.parallel_wave.json").read_text(encoding="utf-8"))
        proj_root = tmp_path / "projects-root"
        proj_dir = _projects_dir(proj_root, ws)
        # Main session at top level (real layout). Sub-agents nest under the
        # CURRENT session's UUID dir (= the main transcript stem) since the
        # watcher scopes discovery to the active session (STALL-1).
        _make_jsonl(proj_dir, "session-uuid-mainjsonl", age_seconds=5)
        sess_dir = proj_dir / "session-uuid-mainjsonl"
        subagents_dir = sess_dir / "subagents"
        subagents_dir.mkdir(parents=True)
        sub_a = _make_jsonl(subagents_dir, "agent-aaa111", age_seconds=30)
        sub_b = _make_jsonl(subagents_dir, "agent-bbb222", age_seconds=60)
        found = sup.discover_sub_agent_transcripts(ws, manifest, projects_root=proj_root)
        found_paths = {str(p) for p in found}
        assert str(sub_a) in found_paths, f"sub_a not found in {found_paths}"
        assert str(sub_b) in found_paths, f"sub_b not found in {found_paths}"

    def test_combined_flat_and_nested_layouts(self, ws, tmp_path):
        """Mix-mode safety: if a future Claude Code revision writes some
        sub-agents flat and some nested (or during migration), both are
        discovered without duplicates."""
        _seed_manifest(ws, created_offset=-120)
        manifest = json.loads(
            (ws / ".agent-toolkit/.parallel_wave.json").read_text(encoding="utf-8"))
        proj_root = tmp_path / "projects-root"
        proj_dir = _projects_dir(proj_root, ws)
        # Main + 1 flat sub + 1 nested sub. Nested sub lives under the CURRENT
        # session's UUID dir (= main transcript stem "main") since discovery
        # is scoped to the active session (STALL-1).
        _make_jsonl(proj_dir, "main", age_seconds=1)  # newest = main
        flat_sub = _make_jsonl(proj_dir, "sub-flat", age_seconds=30)
        nested_dir = proj_dir / "main" / "subagents"
        nested_dir.mkdir(parents=True)
        nested_sub = _make_jsonl(nested_dir, "agent-nested", age_seconds=45)
        found = sup.discover_sub_agent_transcripts(ws, manifest, projects_root=proj_root)
        found_paths = {str(p) for p in found}
        assert str(flat_sub) in found_paths
        assert str(nested_sub) in found_paths
        # No dups.
        assert len(found) == len(set(found_paths))


# -------- TestDetect (us2) ----------------------------------------------

class TestDetect:
    """us2 — per-transcript stall + per-transcript cooldown."""

    def test_per_transcript_independent(self, ws, tmp_path, monkeypatch):
        _seed_autonomy(ws)
        _seed_manifest(ws, created_offset=-1200)
        manifest = sup.read_parallel_wave_manifest(ws)
        proj_root = tmp_path / "proj-root"
        proj_dir = _projects_dir(proj_root, ws)
        # A stale, B fresh, plus a "main" newest sibling so A/B aren't picked
        # as the main transcript.
        _make_jsonl(proj_dir, "main", age_seconds=1)
        _make_jsonl(proj_dir, "sub-A", age_seconds=600)   # stale
        _make_jsonl(proj_dir, "sub-B", age_seconds=5)     # fresh

        calls = []
        monkeypatch.setattr(notify, "dispatch",
                            lambda alert, cfg, ws: calls.append(alert) or {})
        cfg = {"stall_seconds": 180, "notify_cooldown": 300}
        result = sup.check_subagent_transcripts(
            ws, manifest, cfg, projects_root=proj_root,
            last_notify_per_transcript={})
        assert result is not None
        assert len(calls) == 1, "aggregate: one dispatch per tick"
        alert = calls[0]
        assert alert["kind"] == "sub-agent"
        assert alert["stalled_count"] == 1
        # Only sub-A should be in stalled.
        assert any("sub-A" in str(p) for p in result["stalled"])
        assert not any("sub-B" in str(p) for p in result["stalled"])

    def test_pending_tool_use_suppresses_stall(self, ws, tmp_path, monkeypatch):
        """v0.28 regression — sub-agent mid-tool-call must NOT be flagged.

        Mirrors the main-session fix on `check_subagent_transcripts`:
        when a sub-agent transcript's last record is an `assistant.tool_use`
        with no matching `user.tool_result`, the sub-agent is awaiting a
        long Bash / MCP / Task and is NOT idle."""
        _seed_autonomy(ws)
        _seed_manifest(ws, created_offset=-1200)
        manifest = sup.read_parallel_wave_manifest(ws)
        proj_root = tmp_path / "proj-root"
        proj_dir = _projects_dir(proj_root, ws)
        _make_jsonl(proj_dir, "main", age_seconds=1)
        # Sub-agent with stale mtime AND unmatched tool_use → mid-tool-call.
        sub = proj_dir / "sub-A.jsonl"
        sub.write_text(json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tu_pending", "name": "Bash",
                     "input": {"command": "sleep 999"}},
                ],
            },
        }) + "\n", encoding="utf-8")
        past = time.time() - 600
        os.utime(sub, (past, past))

        calls = []
        monkeypatch.setattr(notify, "dispatch",
                            lambda alert, cfg, ws: calls.append(alert) or {})
        cfg = {"stall_seconds": 180, "notify_cooldown": 300}
        result = sup.check_subagent_transcripts(
            ws, manifest, cfg, projects_root=proj_root,
            last_notify_per_transcript={})
        assert result is not None
        assert len(calls) == 0, "mid-tool-call sub-agent must NOT notify"
        assert result["stalled"] == [], "no transcripts must be marked stalled"

    def test_completed_tool_use_still_stalls(self, ws, tmp_path, monkeypatch):
        """Positive control — sub-agent with completed tool_use + stale
        mtime is still flagged (truly idle between turns)."""
        _seed_autonomy(ws)
        _seed_manifest(ws, created_offset=-1200)
        manifest = sup.read_parallel_wave_manifest(ws)
        proj_root = tmp_path / "proj-root"
        proj_dir = _projects_dir(proj_root, ws)
        _make_jsonl(proj_dir, "main", age_seconds=1)
        sub = proj_dir / "sub-A.jsonl"
        lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "tu_done", "name": "Bash",
                         "input": {"command": "echo hi"}},
                    ],
                },
            }),
            json.dumps({
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tu_done",
                         "content": "hi\n"},
                    ],
                },
            }),
        ]
        sub.write_text("\n".join(lines) + "\n", encoding="utf-8")
        past = time.time() - 600
        os.utime(sub, (past, past))

        calls = []
        monkeypatch.setattr(notify, "dispatch",
                            lambda alert, cfg, ws: calls.append(alert) or {})
        cfg = {"stall_seconds": 180, "notify_cooldown": 300}
        result = sup.check_subagent_transcripts(
            ws, manifest, cfg, projects_root=proj_root,
            last_notify_per_transcript={})
        assert result is not None
        assert len(calls) == 1, "completed tool_use + stale → still notify"
        assert any("sub-A" in str(p) for p in result["stalled"])

    def test_cooldown_suppresses_same_transcript(self, ws, tmp_path, monkeypatch):
        _seed_autonomy(ws)
        _seed_manifest(ws, created_offset=-1200)
        manifest = sup.read_parallel_wave_manifest(ws)
        proj_root = tmp_path / "proj-root"
        proj_dir = _projects_dir(proj_root, ws)
        _make_jsonl(proj_dir, "main", age_seconds=1)
        sub = _make_jsonl(proj_dir, "sub-A", age_seconds=600)

        calls = []
        monkeypatch.setattr(notify, "dispatch",
                            lambda alert, cfg, ws: calls.append(alert) or {})
        cfg = {"stall_seconds": 180, "notify_cooldown": 300}
        last_map = {str(sub): time.time() - 60}   # notified 60s ago
        result = sup.check_subagent_transcripts(
            ws, manifest, cfg, projects_root=proj_root,
            last_notify_per_transcript=last_map)
        assert result is not None
        assert len(calls) == 0, "within cooldown — no dispatch"


# -------- TestNotifyPayload (us3) ---------------------------------------

class TestNotifyPayload:
    """us3 — payload carries kind/wave/transcript/stalled_count + prefix."""

    def test_payload_fields(self, ws, tmp_path, monkeypatch):
        _seed_autonomy(ws)
        _seed_manifest(ws, wave="my-wave", created_offset=-1200)
        manifest = sup.read_parallel_wave_manifest(ws)
        proj_root = tmp_path / "proj-root"
        proj_dir = _projects_dir(proj_root, ws)
        _make_jsonl(proj_dir, "main", age_seconds=1)
        _make_jsonl(proj_dir, "sub-A", age_seconds=600)

        captured = []
        monkeypatch.setattr(notify, "dispatch",
                            lambda alert, cfg, ws: captured.append(alert) or {})
        sup.check_subagent_transcripts(
            ws, manifest, {"stall_seconds": 180, "notify_cooldown": 300},
            projects_root=proj_root, last_notify_per_transcript={})
        assert captured, "must dispatch"
        a = captured[0]
        for key in ("kind", "wave", "transcript", "stalled_count", "idle_seconds"):
            assert key in a, f"alert missing {key}"
        assert a["kind"] == "sub-agent"
        assert a["wave"] == "my-wave"
        assert a["stalled_count"] == 1
        # Subject prefix from notify._alert_title.
        title = notify._alert_title(a)
        assert title.startswith("[sub-agent my-wave]")


# -------- TestActivation (us4) ------------------------------------------

class TestActivation:
    """us4 — silent outside active wave (4 conditions)."""

    def _proj_setup(self, ws, tmp_path):
        proj_root = tmp_path / "proj-root"
        proj_dir = _projects_dir(proj_root, ws)
        _make_jsonl(proj_dir, "main", age_seconds=1)
        _make_jsonl(proj_dir, "sub-A", age_seconds=600)
        return proj_root

    def _capture(self, monkeypatch):
        calls = []
        monkeypatch.setattr(notify, "dispatch",
                            lambda alert, cfg, ws: calls.append(alert) or {})
        return calls

    def test_no_manifest_silent(self, ws, tmp_path, monkeypatch):
        _seed_autonomy(ws)
        proj_root = self._proj_setup(ws, tmp_path)
        calls = self._capture(monkeypatch)
        r = sup.check_subagent_transcripts(
            ws, None, {"stall_seconds": 180}, projects_root=proj_root)
        assert r is None
        assert calls == []

    def test_wave_done_silent(self, ws, tmp_path, monkeypatch):
        _seed_autonomy(ws)
        _seed_manifest(ws, wave_done=True, created_offset=-120)
        # read_parallel_wave_manifest treats wave_done=true as inactive → None.
        m = sup.read_parallel_wave_manifest(ws)
        assert m is None
        # Even if caller passes the raw dict, autonomy check is the other guard.
        # Here we verify the manifest reader is the activation gate.

    def test_ttl_expired_silent(self, ws):
        _seed_autonomy(ws)
        _seed_manifest(ws, ttl=3600, created_offset=-7200)  # expired
        assert sup.read_parallel_wave_manifest(ws) is None

    def test_autonomy_off_silent(self, ws, tmp_path, monkeypatch):
        # No autonomy file written.
        _seed_manifest(ws, created_offset=-1200)
        manifest = sup.read_parallel_wave_manifest(ws)
        proj_root = self._proj_setup(ws, tmp_path)
        calls = self._capture(monkeypatch)
        r = sup.check_subagent_transcripts(
            ws, manifest, {"stall_seconds": 180}, projects_root=proj_root)
        assert r is None
        assert calls == []


# -------- TestLifecycle (us5) -------------------------------------------

class TestLifecycle:
    """us5 — v0.24 main path unchanged + multi-mode integrates cleanly."""

    def test_main_path_independent_of_multi_mode(self, ws, tmp_path):
        """Sanity: v0.24 check_once still works with a stale main transcript
        regardless of whether a manifest is present. This is the contract:
        multi-mode never touches main-session logic."""
        _seed_autonomy(ws)
        tp = ws / "transcript.jsonl"
        tp.write_text('{"type":"assistant"}\n', encoding="utf-8")
        past = time.time() - 600
        os.utime(tp, (past, past))
        action, _ = sup.check_once(
            ws, tp, {"stall_seconds": 180, "notify_cooldown": 300},
            now=time.time(), proc_alive=True)
        assert action == "notify", "v0.24 main path must still detect stall"

    def test_multi_mode_inactive_after_wave_done(self, ws):
        _seed_autonomy(ws)
        _seed_manifest(ws, wave_done=True, created_offset=-120)
        assert sup.read_parallel_wave_manifest(ws) is None


# -------- TestNoRelaunch (us7) ------------------------------------------

class TestNoRelaunch:
    """us7 — sub-agent path NEVER calls relaunch_loop / subprocess.run /
    spawns claude. Notify-only contract (D8)."""

    def test_subagent_path_has_no_relaunch_call(self):
        src = (inspect.getsource(sup.check_subagent_transcripts)
               + inspect.getsource(sup.discover_sub_agent_transcripts))
        for forbidden in ("subprocess.run", "Popen", "claude -c",
                          "relaunch_loop", "os.kill"):
            assert forbidden not in src, (
                f"sub-agent path must NOT contain {forbidden}")

    def test_relaunch_loop_not_invoked_on_subagent_tick(self, ws, tmp_path, monkeypatch):
        _seed_autonomy(ws)
        _seed_manifest(ws, created_offset=-1200)
        manifest = sup.read_parallel_wave_manifest(ws)
        proj_root = tmp_path / "proj-root"
        proj_dir = _projects_dir(proj_root, ws)
        _make_jsonl(proj_dir, "main", age_seconds=1)
        _make_jsonl(proj_dir, "sub-A", age_seconds=600)
        # Spy on relaunch_loop: must NOT be called.
        called = []
        monkeypatch.setattr(sup, "relaunch_loop",
                            lambda *a, **k: called.append(1) or ("done", 0))
        monkeypatch.setattr(notify, "dispatch", lambda *a, **k: {})
        sup.check_subagent_transcripts(
            ws, manifest, {"stall_seconds": 180, "notify_cooldown": 300},
            projects_root=proj_root, last_notify_per_transcript={})
        assert called == [], "relaunch_loop must not fire on sub-agent path"
