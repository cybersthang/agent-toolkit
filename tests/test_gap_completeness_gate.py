"""Tests for v0.19.0 gap_completeness_gate.py Stop hook.

7 test classes — one per User Story (us1..us7) per spec
`specs/v0.19.0-gap-completeness-gate.md` § Acceptance evals.

Run: pytest tests/test_gap_completeness_gate.py -v
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
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "gap_completeness_gate.py"
PY = os.environ.get("PYTHON_BIN", sys.executable)

OPEN_GAPS_REL = ".agent-toolkit/.open_gaps.json"


def _run(workspace: Path, response_text: str,
         extra_env: dict = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    env.pop("stop_hook_active", None)
    if extra_env:
        env.update(extra_env)
    envelope = {"response": response_text, "cwd": str(workspace)}
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=10, env=env, cwd=str(workspace),
    )


def _seed_gaps(workspace: Path, gaps: list, pending_bypass: dict = None) -> Path:
    """Write `.open_gaps.json` with given gap entries."""
    path = workspace / OPEN_GAPS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"version": 1, "gaps": gaps}
    if pending_bypass:
        state["pending_bypass"] = pending_bypass
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return path


def _seed_autonomy(workspace: Path, expires_in: int = 3600) -> Path:
    from datetime import datetime, timedelta, timezone
    path = workspace / ".agent-toolkit/.autonomy_active.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    path.write_text(json.dumps({
        "spec": "test", "approved_at": "now",
        "expires_at": exp.isoformat(),
    }), encoding="utf-8")
    return path


def _seed_block_mode(workspace: Path) -> Path:
    """v0.27: gap_completeness_gate default flipped to warn. Tests that
    want to exercise the block path must explicitly opt in via
    enforce_mode.json (mirrors how DEV opts in to strict mode in prod)."""
    path = workspace / ".agent-toolkit/enforce_mode.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "per_hook": {"gap_completeness_gate": "block"},
    }), encoding="utf-8")
    return path


def _read_state(workspace: Path) -> dict:
    return json.loads((workspace / OPEN_GAPS_REL).read_text(encoding="utf-8"))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


class TestUs1BlockOnOpenGaps:
    """US1: done-claim with N>0 open gaps → BLOCK (when enforce=block)
    or WARN (default v0.27)."""

    def test_done_with_open_gaps_blocks_when_strict(self, workspace):
        """v0.27: explicit strict mode → rc=2 block."""
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "Missing config", "status": "open"},
            {"id": "G2", "surfaced_ts": now, "desc": "Missing test", "status": "open"},
        ])
        _seed_block_mode(workspace)
        r = _run(workspace, "Everything done — ready to merge.")
        assert r.returncode == 2, f"expected block, got rc={r.returncode}, stderr={r.stderr}"
        assert "G1" in r.stderr
        assert "G2" in r.stderr

    def test_done_with_open_gaps_warns_by_default(self, workspace):
        """v0.27: no enforce_mode.json → warn-by-default (rc=0 + stderr
        warn). Surfaces gaps without paralyzing the agent."""
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "Missing config", "status": "open"},
        ])
        r = _run(workspace, "Everything done — ready to merge.")
        assert r.returncode == 0, f"expected warn-allow, got rc={r.returncode}"
        assert "[gap-completeness-gate] warn:" in r.stderr
        assert "G1" in r.stderr

    def test_done_with_zero_open_gaps_allows(self, workspace):
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": int(time.time()), "desc": "old",
             "status": "fixed", "resolution_ts": int(time.time())},
        ])
        r = _run(workspace, "All done.")
        assert r.returncode == 0


class TestUs2CaptureNewGapsInResponse:
    """US7 (renumbered): response with `G1 — desc` patterns → state updated."""

    def test_response_emits_new_gaps_persisted(self, workspace):
        r = _run(workspace,
                 "Found issues:\nG1 — missing default config\nG2 — no test file")
        assert r.returncode == 0  # no done-claim → allow
        state = _read_state(workspace)
        ids = {g["id"] for g in state["gaps"]}
        assert {"G1", "G2"}.issubset(ids)


class TestUs3GapDeferMarker:
    """US3: `gap-defer: G<N> <reason>` resolves gap, allows done-claim."""

    def test_defer_resolves_then_allows(self, workspace):
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "Missing X", "status": "open"},
        ])
        r = _run(workspace,
                 "Done. gap-defer: G1 stale-no-repro-needs-DEV-review")
        assert r.returncode == 0, r.stderr
        state = _read_state(workspace)
        assert state["gaps"][0]["status"] == "deferred"


class TestUs4CantFixEscalation:
    """US4: `gap-cant-fix` resolves + surfaces escalation."""

    def test_cant_fix_resolves(self, workspace):
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "Needs prod DB", "status": "open"},
        ])
        r = _run(workspace, "Done. gap-cant-fix: G1 needs-DEV-to-grant-DB-access")
        assert r.returncode == 0
        state = _read_state(workspace)
        assert state["gaps"][0]["status"] == "cant_fix"

    def test_partial_resolution_still_blocks(self, workspace):
        """G1 cant_fix'd, G2 still open → still BLOCK on qualified done-claim
        when strict enforce mode is on (v0.27 explicit opt-in)."""
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "Needs prod", "status": "open"},
            {"id": "G2", "surfaced_ts": now, "desc": "Missing test", "status": "open"},
        ])
        _seed_block_mode(workspace)
        r = _run(workspace,
                 "Everything done. gap-cant-fix: G1 needs-DEV-prod-access")
        assert r.returncode == 2, (
            f"expected block (G2 still open), got rc={r.returncode}, "
            f"stderr={r.stderr}"
        )
        assert "G2" in r.stderr


class TestUs5BypassGateSingleShot:
    """US5: `pending_bypass` field consumed → allow done-claim."""

    def test_bypass_token_allows_then_consumed(self, workspace):
        now = int(time.time())
        _seed_gaps(
            workspace,
            [{"id": "G1", "surfaced_ts": now, "desc": "X", "status": "open"}],
            pending_bypass={"ts": now, "reason": "emergency-hotfix-prod"},
        )
        r = _run(workspace, "Everything done.")
        assert r.returncode == 0, r.stderr
        state = _read_state(workspace)
        assert "pending_bypass" not in state, "token must be consumed"
        assert state.get("bypass_history", [])  # audit log written


class TestUs6AutonomySkipsCheck:
    """US6: autonomy active → skip gate (auto-chain mid-fix)."""

    def test_autonomy_active_skips(self, workspace):
        now = int(time.time())
        _seed_gaps(
            workspace,
            [{"id": "G1", "surfaced_ts": now, "desc": "X", "status": "open"}],
        )
        _seed_autonomy(workspace, expires_in=3600)
        r = _run(workspace, "All done with everything.")
        assert r.returncode == 0, "autonomy should skip but got block"


class TestUs7NoOpWhenNoStateOrNoDoneClaim:
    """US7-edge: no state file OR no done-claim → silent allow."""

    def test_no_state_file_allows(self, workspace):
        r = _run(workspace, "Everything done — first turn ever.")
        assert r.returncode == 0

    def test_no_done_claim_allows_even_with_open_gaps(self, workspace):
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "X", "status": "open"},
        ])
        r = _run(workspace, "Step 1 finished — moving to step 2.")
        assert r.returncode == 0, f"expected allow, got {r.returncode}, {r.stderr}"

    def test_stale_gap_auto_expires(self, workspace):
        """Gap older than 24h auto-flips to status=stale, no longer blocks."""
        old_ts = int(time.time()) - 86400 - 10  # 24h + 10s ago
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": old_ts, "desc": "ancient", "status": "open"},
        ])
        r = _run(workspace, "Everything done.")
        assert r.returncode == 0, "stale gap should not block"
        state = _read_state(workspace)
        assert state["gaps"][0]["status"] == "stale"


class TestKillSwitchHonored:
    """Toolkit-wide AGENT_TOOLKIT_DISABLE=1 → hook is no-op."""

    def test_kill_switch_skips_hook(self, workspace):
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "X", "status": "open"},
        ])
        r = _run(workspace, "Everything done.",
                 extra_env={"AGENT_TOOLKIT_DISABLE": "1"})
        assert r.returncode == 0, "kill-switch should bypass gate"


class TestV027CrossGateDedup:
    """v0.27 — when response carries any scope-* marker, gap_completeness_gate
    auto-downgrades from block to warn so scope_completeness_gate (the
    authoritative completion gate for declared scopes) doesn't double-fire."""

    def test_scope_done_marker_downgrades_block(self, workspace):
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "X", "status": "open"},
        ])
        _seed_block_mode(workspace)  # would normally block
        r = _run(workspace,
                 "Everything done. scope-done: S1")
        assert r.returncode == 0, (
            f"scope-* marker should downgrade gap-gate to warn; got "
            f"rc={r.returncode}, stderr={r.stderr}"
        )
        assert "[gap-completeness-gate] warn:" in r.stderr

    def test_scope_defer_marker_downgrades_block(self, workspace):
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "X", "status": "open"},
        ])
        _seed_block_mode(workspace)
        r = _run(workspace,
                 "Everything done. scope-defer: S1 punt-to-next-sprint")
        assert r.returncode == 0
        assert "[gap-completeness-gate] warn:" in r.stderr

    def test_no_scope_marker_keeps_block_when_strict(self, workspace):
        """Sanity: dedup is conditional on scope-* presence."""
        now = int(time.time())
        _seed_gaps(workspace, [
            {"id": "G1", "surfaced_ts": now, "desc": "X", "status": "open"},
        ])
        _seed_block_mode(workspace)
        r = _run(workspace, "Everything done.")
        assert r.returncode == 2, "without scope-* marker, strict mode still blocks"
