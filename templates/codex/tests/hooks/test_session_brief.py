"""Smoke tests for session_brief hook."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_bypass_rate_warning_emits_when_threshold_hit():
    """Hook with bypass ≥ 20% on ≥5 events → warning string emitted."""
    from session_brief import _read_fire_log_bypass_rates
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".agent-toolkit").mkdir()
        log = {"events": [
            {"hook": "foo.py", "verdict": "bypass"},
            {"hook": "foo.py", "verdict": "bypass"},
            {"hook": "foo.py", "verdict": "bypass"},
            {"hook": "foo.py", "verdict": "allow"},
            {"hook": "foo.py", "verdict": "allow"},
            {"hook": "foo.py", "verdict": "block"},
        ]}
        (ws / ".agent-toolkit" / ".hook_fire_log.json").write_text(json.dumps(log))
        warnings = _read_fire_log_bypass_rates(ws)
        assert any("HIGH BYPASS" in w for w in warnings), f"Expected warning, got {warnings}"
    print("PASS test_bypass_rate_warning_emits_when_threshold_hit")


def test_no_warning_below_threshold():
    from session_brief import _read_fire_log_bypass_rates
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".agent-toolkit").mkdir()
        log = {"events": [
            {"hook": "foo.py", "verdict": "allow"} for _ in range(10)
        ]}
        (ws / ".agent-toolkit" / ".hook_fire_log.json").write_text(json.dumps(log))
        warnings = _read_fire_log_bypass_rates(ws)
        assert warnings == [], f"Expected no warnings, got {warnings}"
    print("PASS test_no_warning_below_threshold")


if __name__ == "__main__":
    test_bypass_rate_warning_emits_when_threshold_hit()
    test_no_warning_below_threshold()
    print("\n2 tests passed")
