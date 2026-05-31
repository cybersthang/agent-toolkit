"""v0.34 T2 — shared convergence-cap (R5.1) · ev6-convergence-no-deadlock.

A block-default gate can NEVER infinite-loop: after `cap` consecutive blocks the
action becomes TERMINAL — 'hold' for crisp/cheaply-satisfiable triggers (escalate
+ require bypass; no auto-allow), 'degrade' for legitimately-unsatisfiable ones.
"""
from __future__ import annotations

import sys
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / "templates" / "claude" / "hooks"))
from _common import converge_or_degrade, converge_reset  # noqa: E402


def test_crisp_with_bypass_holds(tmp_path):
    # crisp + a registered bypass → streak 1,2 block; 3,4 hold (escape via token)
    acts = [converge_or_degrade(tmp_path, "g", "k", cap=3, crisp=True, has_bypass=True)
            for _ in range(4)]
    assert acts == ["block", "block", "hold", "hold"], acts


def test_crisp_without_bypass_degrades(tmp_path):
    # SAFETY GUARD (T1+T2 review): crisp but NO bypass → degrade, never deadlock by holding
    acts = [converge_or_degrade(tmp_path, "g0", "k", cap=3, crisp=True, has_bypass=False)
            for _ in range(3)]
    assert acts == ["block", "block", "degrade"], acts


def test_noncrisp_degrades_at_cap(tmp_path):
    acts = [converge_or_degrade(tmp_path, "g2", "k", cap=3, crisp=False) for _ in range(3)]
    assert acts == ["block", "block", "degrade"], acts


def test_reset_clears_streak(tmp_path):
    converge_or_degrade(tmp_path, "gr", "k", cap=2, crisp=True, has_bypass=True)   # streak 1 → block
    assert converge_or_degrade(tmp_path, "gr", "k", cap=2, crisp=True, has_bypass=True) == "hold"
    converge_reset(tmp_path, "gr", "k")
    assert converge_or_degrade(tmp_path, "gr", "k", cap=2, crisp=True, has_bypass=True) == "block"


def test_independent_keys_isolated(tmp_path):
    converge_or_degrade(tmp_path, "g", "k1", cap=2, crisp=True)  # k1 streak 1
    assert converge_or_degrade(tmp_path, "g", "k2", cap=2, crisp=True) == "block"  # k2 fresh
