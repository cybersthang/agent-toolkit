"""v0.34 T10 (R5.2) — flip_readiness per-trigger would-block telemetry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / "templates" / "codex" / "tools"))
import flip_readiness as fr  # noqa: E402


def _ws(tmp: Path, events) -> Path:
    ws = tmp / "ws"
    (ws / ".agent-toolkit").mkdir(parents=True, exist_ok=True)
    (ws / ".agent-toolkit" / ".hook_fire_log.json").write_text(
        json.dumps({"events": events}), encoding="utf-8")
    return ws


def test_would_block_counts_warn_and_block(tmp_path):
    ws = _ws(tmp_path, [
        {"ts": 1, "hook": "verify_lint.py", "verdict": "warn"},
        {"ts": 2, "hook": "verify_lint.py", "verdict": "warn"},
        {"ts": 3, "hook": "verify_lint.py", "verdict": "ok"},
        {"ts": 4, "hook": "review_proof_gate.py", "verdict": "block"},
    ])
    by = {t["trigger"]: t for t in fr.readiness(ws)["triggers"]}
    assert by["verify_lint.py"]["would_block"] == 2
    assert "HOLD" in by["verify_lint.py"]["flip"]
    assert by["review_proof_gate.py"]["would_block"] == 1


def test_zero_would_block_is_ready(tmp_path):
    ws = _ws(tmp_path, [
        {"ts": 1, "hook": "analyze_halt_gate.py", "verdict": "ok"},
        {"ts": 2, "hook": "analyze_halt_gate.py", "verdict": "cached"},
    ])
    by = {t["trigger"]: t for t in fr.readiness(ws)["triggers"]}
    assert by["analyze_halt_gate.py"]["would_block"] == 0
    assert "READY" in by["analyze_halt_gate.py"]["flip"]


def test_bypass_holds_even_with_zero_would_block(tmp_path):
    ws = _ws(tmp_path, [{"ts": 1, "hook": "implement_notes_gate.py", "verdict": "bypass"}])
    by = {t["trigger"]: t for t in fr.readiness(ws)["triggers"]}
    assert "HOLD" in by["implement_notes_gate.py"]["flip"]


def test_missing_log_all_ready(tmp_path):
    ws = tmp_path / "empty"
    (ws / ".agent-toolkit").mkdir(parents=True)
    rep = fr.readiness(ws)
    assert rep["events_seen"] == 0
    assert all("READY" in t["flip"] for t in rep["triggers"])


def test_all_candidates_present(tmp_path):
    rep = fr.readiness(_ws(tmp_path, []))
    assert {t["trigger"] for t in rep["triggers"]} == set(fr.FLIP_CANDIDATES)
