"""Smoke tests for complexity_sentinel hook."""
from __future__ import annotations

import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def test_import_module():
    import complexity_sentinel as cs
    assert hasattr(cs, "main")
    print("PASS test_import_module")


def test_module_has_run_main_safe_wrapper():
    import inspect
    import complexity_sentinel
    src = inspect.getsource(complexity_sentinel)
    assert "run_main_safe" in src
    print("PASS test_module_has_run_main_safe_wrapper")


if __name__ == "__main__":
    test_import_module()
    test_module_has_run_main_safe_wrapper()
    print("\n2 tests passed")
