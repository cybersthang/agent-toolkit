"""Smoke tests for analyze_halt_gate hook."""
from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_import_module():
    import analyze_halt_gate as ahg
    assert hasattr(ahg, "main")
    print("PASS test_import_module")


def test_module_uses_run_main_safe():
    import inspect
    import analyze_halt_gate
    src = inspect.getsource(analyze_halt_gate)
    assert "run_main_safe" in src
    print("PASS test_module_uses_run_main_safe")


if __name__ == "__main__":
    test_import_module()
    test_module_uses_run_main_safe()
    print("\n2 tests passed")
