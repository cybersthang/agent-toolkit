"""Tests for session_brief.py resume-brief injection (v0.24.0, T5).

Asserts the SessionStart brief gains a RESUME block when an autonomous run
was interrupted (R9 scope manifest still has pending items). Supports the
VSCode-extension semi-auto resume path.

Run: pytest tests/test_session_brief.py -v
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
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "session_brief.py"
PY = os.environ.get("PYTHON_BIN", sys.executable)


def _run(ws: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    envelope = {"cwd": str(ws), "source": "resume"}
    return subprocess.run([PY, str(HOOK)], input=json.dumps(envelope),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=10, env=env, cwd=str(ws))


def _seed(ws: Path, items: list):
    ad = ws / ".agent-toolkit"
    ad.mkdir(parents=True, exist_ok=True)
    (ad / ".scope_manifest.json").write_text(json.dumps({
        "version": 1, "spec": "feat", "source": "tasks.md",
        "created_ts": int(time.time()), "items": items,
    }, ensure_ascii=False), encoding="utf-8")
    from datetime import datetime, timedelta, timezone
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    (ad / ".autonomy_active.json").write_text(
        json.dumps({"spec": "feat", "expires_at": exp.isoformat()}), encoding="utf-8")


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return tmp_path


def test_resume_block_when_pending(ws):
    _seed(ws, [
        {"id": "S1", "ref": "T1", "desc": "alpha", "status": "done"},
        {"id": "S2", "ref": "T2", "desc": "beta", "status": "pending"},
    ])
    r = _run(ws)
    assert r.returncode == 0, r.stderr
    assert "RESUME" in r.stdout
    assert "S2" in r.stdout
    assert "S1" not in r.stdout  # done item not re-listed (idempotent)


def test_no_resume_block_when_all_done(ws):
    _seed(ws, [
        {"id": "S1", "ref": "T1", "desc": "alpha", "status": "done"},
    ])
    r = _run(ws)
    assert r.returncode == 0
    assert "RESUME" not in r.stdout
