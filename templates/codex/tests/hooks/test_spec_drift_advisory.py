"""Smoke tests for spec_drift_advisory hook."""
from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_default_config_has_enabled_flag():
    from spec_drift_advisory import _DEFAULT_CONFIG
    assert "enabled" in _DEFAULT_CONFIG
    assert _DEFAULT_CONFIG["enabled"] is True
    print("PASS test_default_config_has_enabled_flag")


def test_default_config_has_ignore_words():
    from spec_drift_advisory import _DEFAULT_CONFIG
    assert isinstance(_DEFAULT_CONFIG.get("ignore_words"), list)
    assert "the" in _DEFAULT_CONFIG["ignore_words"]
    print("PASS test_default_config_has_ignore_words")


if __name__ == "__main__":
    test_default_config_has_enabled_flag()
    test_default_config_has_ignore_words()
    print("\n2 tests passed")
