"""Tests for v0.24.0 tools/agent_supervisor.py (agent-resilience-supervisor).

Covers us2-stall-detect-readonly (detect + notify, read-only) and
us4-cli-relaunch-cap (CLI auto-relaunch cap + backoff → notify).

Run: pytest tests/test_stall_watcher.py -v
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


def _seed_autonomy(ws: Path, spec: str = "feat", hours: int = 1):
    from datetime import datetime, timedelta, timezone
    p = ws / ".agent-toolkit/.autonomy_active.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    exp = datetime.now(timezone.utc) + timedelta(hours=hours)
    p.write_text(json.dumps({"spec": spec, "expires_at": exp.isoformat()}),
                 encoding="utf-8")


def _make_transcript(ws: Path, age_seconds: float) -> Path:
    p = ws / "transcript.jsonl"
    p.write_text('{"type":"assistant"}\n', encoding="utf-8")
    past = time.time() - age_seconds
    os.utime(p, (past, past))
    return p


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return tmp_path


class TestDetect:
    """us2: stale transcript + autonomy → notify (read-only)."""

    def test_stale_transcript_triggers_notify(self, ws, monkeypatch):
        _seed_autonomy(ws)
        tp = _make_transcript(ws, age_seconds=600)  # 10 min stale
        calls = {"n": 0}
        monkeypatch.setattr(notify, "dispatch",
                            lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or {})
        cfg = {"stall_seconds": 180, "notify_cooldown": 300}
        action, _ = sup.check_once(ws, tp, cfg, now=time.time(), proc_alive=True)
        assert action == "notify"
        assert calls["n"] == 1

    def test_fresh_transcript_no_notify(self, ws, monkeypatch):
        _seed_autonomy(ws)
        tp = _make_transcript(ws, age_seconds=5)
        calls = {"n": 0}
        monkeypatch.setattr(notify, "dispatch",
                            lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or {})
        action, _ = sup.check_once(ws, tp, {"stall_seconds": 180}, now=time.time())
        assert action == "ok"
        assert calls["n"] == 0

    def test_no_autonomy_no_notify(self, ws, monkeypatch):
        # autonomy file absent → never stalled even if transcript old.
        tp = _make_transcript(ws, age_seconds=600)
        monkeypatch.setattr(notify, "dispatch", lambda *a, **k: {})
        action, _ = sup.check_once(ws, tp, {"stall_seconds": 180}, now=time.time())
        assert action == "ok"

    def test_process_dead_is_stalled(self, ws):
        _seed_autonomy(ws)
        tp = _make_transcript(ws, age_seconds=5)  # fresh, but process gone
        assert sup.is_stalled(tp, autonomy_on=True, stall_seconds=180,
                              now=time.time(), proc_alive=False) is True

    def test_cooldown_suppresses_repeat(self, ws, monkeypatch):
        _seed_autonomy(ws)
        tp = _make_transcript(ws, age_seconds=600)
        monkeypatch.setattr(notify, "dispatch", lambda *a, **k: {})
        now = time.time()
        action, _ = sup.check_once(ws, tp, {"stall_seconds": 180, "notify_cooldown": 300},
                                   now=now, last_notify_ts=now - 100)
        assert action == "stalled-cooldown"

    def test_detect_path_is_readonly(self):
        """us2 contract: the detect/notify path must not kill or spawn."""
        src = inspect.getsource(sup.check_once) + inspect.getsource(sup.is_stalled)
        for forbidden in ("os.kill", "terminate(", "Popen", ".kill("):
            assert forbidden not in src, f"read-only path must not contain {forbidden}"


class TestCliRelaunch:
    """us4: --relaunch auto-relaunch cap 10 + backoff → notify on exhaustion."""

    def test_cap_10_then_notify(self, ws, monkeypatch):
        _seed_autonomy(ws)
        runs = {"n": 0}
        def always_fail(brief):
            runs["n"] += 1
            return False
        notifies = {"n": 0}
        monkeypatch.setattr(notify, "dispatch",
                            lambda *a, **k: notifies.__setitem__("n", notifies["n"] + 1) or {})
        cfg = {"relaunch_cap": 10, "backoff_base": 2}
        action, attempts = sup.relaunch_loop(ws, cfg, run_claude=always_fail,
                                             sleep_fn=lambda s: None)
        assert action == "cap-exhausted"
        assert runs["n"] == 10, "relaunch đúng 10 lần, lần 11 KHÔNG"
        assert notifies["n"] == 1, "cạn cap → notify DEV 1 lần"

    def test_success_stops_early(self, ws, monkeypatch):
        _seed_autonomy(ws)
        runs = {"n": 0}
        def succeed_on_3rd(brief):
            runs["n"] += 1
            return runs["n"] >= 3
        monkeypatch.setattr(notify, "dispatch", lambda *a, **k: {})
        action, attempts = sup.relaunch_loop(ws, {"relaunch_cap": 10, "backoff_base": 2},
                                             run_claude=succeed_on_3rd, sleep_fn=lambda s: None)
        assert action == "done"
        assert attempts == 3

    def test_relaunch_command_shape(self):
        cmd = sup.build_relaunch_command("resume here")
        assert cmd[:3] == ["claude", "-c", "-p"]
        assert cmd[3] == "resume here"
