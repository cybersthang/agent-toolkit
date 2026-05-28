"""Tests for v0.24.0 _resume_state.py core (agent-resilience-supervisor).

Covers acceptance_evals us1-resume-state-core + us5-resume-idempotent per
spec specs/v0.24.0-agent-resilience-supervisor.md.

Run: pytest tests/test_resume_state.py -v
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import _resume_state  # noqa: E402


def _seed_manifest(ws: Path, items: list, spec: str = "feat", source: str = "tasks.md"):
    p = ws / ".agent-toolkit/.scope_manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "version": 1, "spec": spec, "source": source,
        "created_ts": int(time.time()), "items": items,
    }, ensure_ascii=False), encoding="utf-8")


def _seed_autonomy(ws: Path, spec: str = "feat"):
    from datetime import datetime, timedelta, timezone
    p = ws / ".agent-toolkit/.autonomy_active.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    p.write_text(json.dumps({"spec": spec, "expires_at": exp.isoformat()}),
                 encoding="utf-8")


def _seed_tasks(ws: Path, slug: str, body: str):
    p = ws / "specs" / f"{slug}.tasks.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return tmp_path


class TestResumeBrief:
    """us1: brief từ manifest + autonomy, chỉ liệt kê pending."""

    def test_brief_from_manifest_tasks_autonomy(self, ws):
        _seed_manifest(ws, [
            {"id": "S1", "ref": "T1", "desc": "alpha", "status": "done"},
            {"id": "S2", "ref": "T2", "desc": "beta", "status": "pending"},
            {"id": "S3", "ref": "T3", "desc": "gamma", "status": "pending"},
        ], spec="feat")
        _seed_autonomy(ws, spec="feat")
        brief = _resume_state.build_brief(ws)
        assert brief is not None
        assert "S2" in brief and "S3" in brief
        assert "S1" not in brief  # done → excluded
        assert "RESUME" in brief

    def test_no_manifest_returns_none(self, ws):
        assert _resume_state.build_brief(ws) is None

    def test_all_resolved_returns_none(self, ws):
        _seed_manifest(ws, [
            {"id": "S1", "ref": "T1", "desc": "a", "status": "done"},
            {"id": "S2", "ref": "T2", "desc": "b", "status": "deferred"},
        ])
        assert _resume_state.build_brief(ws) is None


class TestIdempotent:
    """us5: tasks.md passed → item excluded (không redo)."""

    def test_passed_tasks_excluded(self, ws):
        # Manifest says both pending, but tasks.md now marks T1 passed.
        _seed_manifest(ws, [
            {"id": "S1", "ref": "T1", "desc": "first", "status": "pending"},
            {"id": "S2", "ref": "T2", "desc": "second", "status": "pending"},
        ], spec="myfeat")
        _seed_tasks(ws, "myfeat",
                    "## T1 — first\n- status: passed\n\n## T2 — second\n- not run\n")
        brief = _resume_state.build_brief(ws)
        assert brief is not None
        assert "S2" in brief
        assert "S1" not in brief, "T1 passed → phải bị loại (idempotent)"
