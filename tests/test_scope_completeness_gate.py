"""Tests for v0.23.0 scope_completeness_gate.py Stop hook (R9).

5 test classes — one per acceptance_eval (us1..us5) per spec
`specs/v0.23.0-scope-completeness-gate.md` § acceptance_evals — plus a
kill-switch test.

Run: pytest tests/test_scope_completeness_gate.py -v
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
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "scope_completeness_gate.py"
PY = os.environ.get("PYTHON_BIN", sys.executable)

MANIFEST_REL = ".agent-toolkit/.scope_manifest.json"


def _run(workspace: Path, response_text: str, transcript: Path = None,
         extra_env: dict = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    env.pop("stop_hook_active", None)
    env.pop("AGENT_TOOLKIT_STRICT", None)
    if extra_env:
        env.update(extra_env)
    envelope = {"response": response_text, "cwd": str(workspace)}
    if transcript is not None:
        envelope["transcript_path"] = str(transcript)
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, env=env, cwd=str(workspace),
    )


def _seed_autonomy(workspace: Path, spec: str = "test-feature",
                   expires_in: int = 3600) -> Path:
    from datetime import datetime, timedelta, timezone
    path = workspace / ".agent-toolkit/.autonomy_active.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    path.write_text(json.dumps({
        "spec": spec, "approved_at": "now", "expires_at": exp.isoformat(),
    }), encoding="utf-8")
    return path


def _seed_manifest(workspace: Path, items: list, source: str = "tasks.md") -> Path:
    path = workspace / MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 1, "spec": "test-feature", "source": source,
        "created_ts": int(time.time()), "items": items, "bypass_history": [],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def _read_manifest(workspace: Path) -> dict:
    return json.loads((workspace / MANIFEST_REL).read_text(encoding="utf-8"))


def _write_tasks_md(workspace: Path, slug: str, body: str) -> Path:
    path = workspace / "specs" / f"{slug}.tasks.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_transcript(workspace: Path, todos: list) -> Path:
    """Write a minimal JSONL transcript whose last TodoWrite call carries
    `todos`."""
    path = workspace / "transcript.jsonl"
    line = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "TodoWrite",
                 "input": {"todos": todos}},
            ],
        },
    }
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


class TestManifestDerive:
    """us1: manifest derives from tasks.md (priority 1), NOT DEV prompt."""

    def test_source_priority_tasks_then_evals(self, workspace):
        _seed_autonomy(workspace, spec="myfeat")
        _write_tasks_md(workspace, "myfeat", (
            "## T1 — first thing\n- status: passed\n\n"
            "## T2 — second thing\n- not yet run\n"
        ))
        # Non-done response → no block, but manifest derived + persisted.
        r = _run(workspace, "Working on it, T1 ok.")
        assert r.returncode == 0, r.stderr
        m = _read_manifest(workspace)
        assert m["source"] == "tasks.md"
        ids = {it["id"]: it["status"] for it in m["items"]}
        assert ids == {"S1": "done", "S2": "pending"}

    def test_no_dev_prompt_keyword_parsing(self):
        """Anti-requirement §7: gate must NOT parse DEV prompt keywords."""
        src = HOOK.read_text(encoding="utf-8")
        assert "trigger_patterns" not in src
        assert 'envelope.get("prompt")' not in src
        assert "user_prompt" not in src


class TestBlockSemantics:
    """us2: done/full claim + pending item → BLOCK (exit 2)."""

    def test_block_when_pending_and_done_claim(self, workspace):
        _seed_manifest(workspace, [
            {"id": "S1", "ref": "T1", "desc": "alpha", "status": "done"},
            {"id": "S2", "ref": "T2", "desc": "beta", "status": "pending"},
        ])
        r = _run(workspace, "Implement done — everything complete.")
        assert r.returncode == 2, f"expected block, got {r.returncode}: {r.stderr}"
        assert "S2" in r.stderr

    def test_all_resolved_allows(self, workspace):
        _seed_manifest(workspace, [
            {"id": "S1", "ref": "T1", "desc": "alpha", "status": "done"},
            {"id": "S2", "ref": "T2", "desc": "beta", "status": "deferred"},
        ])
        r = _run(workspace, "Everything done.")
        assert r.returncode == 0, r.stderr

    def test_pending_without_done_claim_allows(self, workspace):
        _seed_manifest(workspace, [
            {"id": "S1", "ref": "T1", "desc": "alpha", "status": "pending"},
        ])
        r = _run(workspace, "Finished T-prep, moving to next step now.")
        assert r.returncode == 0, r.stderr


class TestResolutionMarkers:
    """us3: scope-done / scope-defer / scope-cant flip item status."""

    def test_markers_transition_status(self, workspace):
        _seed_manifest(workspace, [
            {"id": "S1", "ref": "T1", "desc": "a", "status": "pending"},
            {"id": "S2", "ref": "T2", "desc": "b", "status": "pending"},
            {"id": "S3", "ref": "T3", "desc": "c", "status": "pending"},
        ])
        resp = ("Done.\n"
                "scope-done: S1\n"
                "scope-defer: S2 punt-to-next-sprint-low-prio\n"
                "scope-cant: S3 needs-DEV-prod-access-decision\n")
        r = _run(workspace, resp)
        assert r.returncode == 0, r.stderr
        st = {it["id"]: it["status"] for it in _read_manifest(workspace)["items"]}
        assert st == {"S1": "done", "S2": "deferred", "S3": "cant"}

    def test_partial_resolution_still_blocks(self, workspace):
        _seed_manifest(workspace, [
            {"id": "S1", "ref": "T1", "desc": "a", "status": "pending"},
            {"id": "S2", "ref": "T2", "desc": "b", "status": "pending"},
        ])
        r = _run(workspace, "All done. scope-done: S1")
        assert r.returncode == 2, f"S2 still pending → block; got {r.returncode}"
        assert "S2" in r.stderr


class TestActivation:
    """us4: no manifest → gate silent (exit 0, zero output)."""

    def test_silent_when_no_manifest_no_autonomy(self, workspace):
        r = _run(workspace, "Everything done — first turn ever.")
        assert r.returncode == 0
        assert r.stdout.strip() == ""
        assert r.stderr.strip() == ""
        assert not (workspace / MANIFEST_REL).exists()

    def test_silent_when_autonomy_but_no_source(self, workspace):
        _seed_autonomy(workspace, spec="nope-no-artifact")
        r = _run(workspace, "Everything done.")
        assert r.returncode == 0
        assert r.stderr.strip() == ""
        assert not (workspace / MANIFEST_REL).exists()


class TestAdhocManifest:
    """us5: ad-hoc manifest auto-emit when TodoWrite >= 3 (D1)."""

    def test_todowrite_threshold_3_emits(self, workspace):
        _seed_autonomy(workspace, spec="adhoc-run")
        tr = _write_transcript(workspace, [
            {"content": "fix R1", "status": "completed"},
            {"content": "fix R2", "status": "pending"},
            {"content": "fix R3", "status": "in_progress"},
        ])
        r = _run(workspace, "Making progress.", transcript=tr)
        assert r.returncode == 0, r.stderr
        m = _read_manifest(workspace)
        assert m["source"] == "todowrite"
        st = {it["id"]: it["status"] for it in m["items"]}
        assert st == {"S1": "done", "S2": "pending", "S3": "pending"}

    def test_todowrite_below_threshold_silent(self, workspace):
        _seed_autonomy(workspace, spec="adhoc-run")
        tr = _write_transcript(workspace, [
            {"content": "fix R1", "status": "pending"},
            {"content": "fix R2", "status": "pending"},
        ])
        r = _run(workspace, "Everything done.", transcript=tr)
        assert r.returncode == 0
        assert not (workspace / MANIFEST_REL).exists()


class TestKillSwitchHonored:
    """Toolkit-wide AGENT_TOOLKIT_DISABLE=1 → hook is a no-op."""

    def test_kill_switch_skips_hook(self, workspace):
        _seed_manifest(workspace, [
            {"id": "S1", "ref": "T1", "desc": "x", "status": "pending"},
        ])
        r = _run(workspace, "Everything done.",
                 extra_env={"AGENT_TOOLKIT_DISABLE": "1"})
        assert r.returncode == 0, "kill-switch should bypass gate"
