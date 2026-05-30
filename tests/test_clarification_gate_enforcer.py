"""Tests for v0.13.0 clarification_gate_enforcer.py Stop hook.

7 test classes — one per User Story (us1..us7). Each class covers
exactly one acceptance_eval entry from the spec frontmatter.

Run: pytest tests/test_clarification_gate_enforcer.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "clarification_gate_enforcer.py"
INTENT_ROUTER = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "intent_router.py"
PY = os.environ.get("PYTHON_BIN", sys.executable)

REQUIRED_MARKERS = ("UNDERSTANDING", "ASSUMPTIONS", "QUESTIONS", "Searched:")
SHAPE_COMPLETE = (
    "## UNDERSTANDING\nparaphrase\n\n## ASSUMPTIONS\n- a\n\n"
    "## QUESTIONS\nQ1: ...\nSearched:\n- grep foo\n"
)


def _run_hook(workspace: Path, envelope: dict, env_extra: dict = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    env.pop("AGENT_TOOLKIT_STRICT", None)
    # v0.21: tests previously used `AGENT_TOOLKIT_STRICT=1` opt-in; flipped
    # to `AGENT_TOOLKIT_NO_STRICT=1` opt-out. Default behavior is now strict.
    env.pop("AGENT_TOOLKIT_NO_STRICT", None)
    if env_extra:
        env.update(env_extra)
    envelope.setdefault("cwd", str(workspace))
    # v0.21: _extract_response_text reads from transcript_path (JSONL), not
    # inline `response` key. Convert legacy test envelopes for backward
    # compat with the existing test corpus.
    if "response" in envelope and "transcript_path" not in envelope:
        response_text = envelope.pop("response")
        transcript_path = workspace / "_test_transcript.jsonl"
        with transcript_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"role": "user", "content": "test"}) + "\n")
            f.write(json.dumps({
                "role": "assistant",
                "content": [{"type": "text", "text": response_text}],
            }) + "\n")
        envelope["transcript_path"] = str(transcript_path)
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope),
        capture_output=True, text=True, env=env, timeout=10,
    )


def _seed_last_intent(workspace: Path, skills=("clarification-gate",), ts: int = None) -> Path:
    p = workspace / ".agent-toolkit" / ".last_intent_suggested.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "ts": ts if ts is not None else int(time.time()),
        "skills": list(skills),
        "prompt_hash": "deadbeef",
    }))
    return p


def _seed_autonomy(workspace: Path, expires_in_seconds: int = 3600) -> Path:
    from datetime import datetime, timedelta, timezone
    p = workspace / ".agent-toolkit" / ".autonomy_active.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    p.write_text(json.dumps({
        "spec": "test", "approved_at": "now",
        "expires_at": exp.isoformat(),
        "scopes": [], "still_blocked": [],
    }))
    return p


def _seed_skip_token(workspace: Path, reason: str = "emergency-fix",
                     ts: int = None) -> Path:
    p = workspace / ".agent-toolkit" / ".skip_clarification_next.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "ts": ts if ts is not None else int(time.time()),
        "reason": reason,
        "ttl_seconds": 300,
    }))
    return p


class TestUs1DenyWhenShapeMissing:
    """us1-deny-stop-when-clarification-shape-missing"""

    def test_text_only_no_markers_blocks(self, tmp_path):
        _seed_last_intent(tmp_path)
        r = _run_hook(tmp_path, {"response": "OK đã làm xong"})
        assert r.returncode == 2
        assert "missing markers" in r.stderr
        for m in REQUIRED_MARKERS:
            assert m in r.stderr, f"missing marker {m} should appear in stderr"

    def test_partial_markers_blocks_listing_missing_only(self, tmp_path):
        _seed_last_intent(tmp_path)
        resp = "## UNDERSTANDING\nfoo\n## ASSUMPTIONS\nbar\n"
        r = _run_hook(tmp_path, {"response": resp})
        assert r.returncode == 2
        assert "QUESTIONS" in r.stderr
        assert "Searched:" in r.stderr
        # Present markers should NOT appear in the missing list.
        # (heuristic — stderr contains "missing markers: QUESTIONS, Searched:")
        missing_line = [ln for ln in r.stderr.splitlines() if "missing markers" in ln][0]
        assert "UNDERSTANDING" not in missing_line
        assert "ASSUMPTIONS" not in missing_line


class TestUs2AllowWhenComplete:
    """us2-allow-when-all-four-markers-present"""

    def test_complete_response_allows_silently(self, tmp_path):
        _seed_last_intent(tmp_path)
        r = _run_hook(tmp_path, {"response": SHAPE_COMPLETE})
        assert r.returncode == 0
        assert "block" not in r.stderr
        assert "warn" not in r.stderr


class TestUs3SkipOnAutonomy:
    """us3-skip-when-autonomy-active"""

    def test_fresh_autonomy_skips_check(self, tmp_path):
        _seed_last_intent(tmp_path)
        _seed_autonomy(tmp_path, expires_in_seconds=3600)
        r = _run_hook(tmp_path, {"response": "no markers here"})
        assert r.returncode == 0, f"autonomy should skip but got rc={r.returncode}, stderr={r.stderr}"

    def test_expired_autonomy_still_enforces(self, tmp_path):
        _seed_last_intent(tmp_path)
        _seed_autonomy(tmp_path, expires_in_seconds=-3600)  # expired 1h ago
        r = _run_hook(tmp_path, {"response": "no markers here"})
        assert r.returncode == 2, f"expired autonomy should NOT skip; rc={r.returncode}"


class TestUs4EscapeTokenSingleUseAndReasonLength:
    """us4-skip-on-escape-token-single-use"""

    def test_token_consume_single_use_then_unlink(self, tmp_path):
        _seed_last_intent(tmp_path)
        token_path = _seed_skip_token(tmp_path, reason="emergency-fix")
        assert token_path.exists()
        # First run: consume + allow.
        r1 = _run_hook(tmp_path, {"response": "no markers"})
        assert r1.returncode == 0
        assert not token_path.exists(), "token file should be unlinked after first use"
        # Second run with no token: enforce normally.
        _seed_last_intent(tmp_path)  # re-seed (TTL still fresh, but doesn't matter)
        r2 = _run_hook(tmp_path, {"response": "no markers"})
        assert r2.returncode == 2, f"second run should enforce; rc={r2.returncode}"

    def test_short_reason_rejected_at_intent_router(self, tmp_path):
        """Verify regex \\S{8,200} on the router side rejects 'skip-clarification: x'.

        Use subprocess (not in-process import) because intent_router's
        module-level wrap_utf8_stdio() swaps stdin/stdout/stderr globally
        and breaks pytest capture.
        """
        skip_rel = ".agent-toolkit/.skip_clarification_next.json"

        def run_router(prompt: str):
            env = os.environ.copy()
            env.pop("AGENT_TOOLKIT_DISABLE", None)
            return subprocess.run(
                [PY, str(INTENT_ROUTER)],
                input=json.dumps({"prompt": prompt, "cwd": str(tmp_path)}),
                capture_output=True, text=True, env=env, timeout=10,
            )

        run_router("skip-clarification: x")
        assert not (tmp_path / skip_rel).exists(), "1-char reason should be rejected"
        # Wipe any leftover from prior run before next assert.
        (tmp_path / skip_rel).unlink(missing_ok=True) if (tmp_path / skip_rel).exists() else None
        run_router("skip-clarification: short")  # 5 chars
        assert not (tmp_path / skip_rel).exists(), "5-char reason should be rejected"
        run_router("skip-clarification: emergency-fix-prod")
        assert (tmp_path / skip_rel).exists(), "valid 18-char reason should create state file"
        data = json.loads((tmp_path / skip_rel).read_text())
        assert data["reason"] == "emergency-fix-prod"

    def test_expired_token_not_consumed(self, tmp_path):
        _seed_last_intent(tmp_path)
        # Token older than TTL (300s).
        _seed_skip_token(tmp_path, reason="stale-emergency", ts=int(time.time()) - 1000)
        r = _run_hook(tmp_path, {"response": "no markers"})
        assert r.returncode == 2, "expired token should not skip enforcement"


class TestUs5NoopWhenNoSuggestion:
    """us5-no-op-when-no-clarification-suggested"""

    def test_no_state_file_means_silent_allow(self, tmp_path):
        # No .last_intent_suggested.json at all.
        r = _run_hook(tmp_path, {"response": "this turn ignored entirely"})
        assert r.returncode == 0
        assert "block" not in r.stderr

    def test_state_without_clarification_gate_skill_skips(self, tmp_path):
        _seed_last_intent(tmp_path, skills=("code-review", "doubt-driven-review"))
        r = _run_hook(tmp_path, {"response": "no markers"})
        assert r.returncode == 0, f"non-clarification skill list should skip; rc={r.returncode}"


class TestUs6EnforceModeRespected:
    """us6-enforce-mode-and-strict-env-respected"""

    def _set_mode(self, workspace: Path, mode: str):
        cfg = workspace / ".agent-toolkit" / "enforce_mode.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({
            "default": "warn",
            "per_hook": {"clarification_gate_enforcer": mode},
        }))

    def test_mode_warn_allows_with_warning(self, tmp_path):
        _seed_last_intent(tmp_path)
        self._set_mode(tmp_path, "warn")
        r = _run_hook(tmp_path, {"response": "no markers"})
        assert r.returncode == 0
        assert "[clarification-gate-enforcer] warn:" in r.stderr

    def test_default_fallback_is_block(self, tmp_path):
        _seed_last_intent(tmp_path)
        # No enforce_mode.json → fall back to hook default ("block" per D8).
        r = _run_hook(tmp_path, {"response": "no markers"})
        assert r.returncode == 2
        assert "[clarification-gate-enforcer] block:" in r.stderr

    def test_strict_env_overrides_warn(self, tmp_path):
        _seed_last_intent(tmp_path)
        self._set_mode(tmp_path, "warn")
        r = _run_hook(tmp_path, {"response": "no markers"}, env_extra={"AGENT_TOOLKIT_STRICT": "1"})
        assert r.returncode == 2, "STRICT env should force block over warn"


class TestUs7InstallerWiringOrder:
    """us7-installer-wires-hook-into-stop-chain"""

    def test_settings_template_lists_enforcer_after_evidence_audit(self):
        settings_path = TOOLKIT_ROOT / "templates" / "claude" / "settings.json"
        cfg = json.loads(settings_path.read_text())
        stop_hooks = cfg["hooks"]["Stop"][0]["hooks"]
        names = [h["command"].rsplit("/", 1)[-1] for h in stop_hooks]
        assert "clarification_gate_enforcer.py" in names, "enforcer not wired into Stop chain"
        i_evidence = names.index("evidence_audit.py")
        i_enforcer = names.index("clarification_gate_enforcer.py")
        i_debug = names.index("debug_sentry.py")
        assert i_evidence < i_enforcer, "enforcer must run AFTER evidence_audit (D8)"
        assert i_enforcer < i_debug, "enforcer must run BEFORE debug_sentry (D8)"

    def test_enforce_mode_example_has_block_default(self):
        cfg_path = TOOLKIT_ROOT / "templates" / "agent_toolkit" / "enforce_mode.example.json"
        cfg = json.loads(cfg_path.read_text())
        assert cfg["per_hook"]["clarification_gate_enforcer"] == "block", \
            "enforce_mode.example.json must list clarification_gate_enforcer: block (D8)"
