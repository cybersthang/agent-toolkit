"""CI gate for the shipped codex-side Python under templates/codex/**.

The canonical suite is `tests/` (pytest.ini testpaths=tests). The codex tree
ships to user projects and its own hook tests run post-install, so the codex
tools + mcp_servers had NO CI coverage — that is how an f-string NameError in
agent_toolkit_init._starter_settings shipped undetected.

This gate gives the whole codex tree a CI net:
  - py_compile every .py (syntax / parse regression),
  - import every tool in templates/codex/tools/ (module-level NameError / bad
    import), tolerating missing optional third-party deps.
"""
from __future__ import annotations

import importlib.util
import py_compile
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
CODEX_ROOT = TOOLKIT_ROOT / "templates" / "codex"


def _codex_py():
    return sorted(CODEX_ROOT.rglob("*.py"))


def _codex_tools():
    return sorted((CODEX_ROOT / "tools").glob("*.py"))


def test_codex_tree_discovered():
    assert _codex_py(), f"no .py found under {CODEX_ROOT}"
    assert _codex_tools(), f"no tools found under {CODEX_ROOT / 'tools'}"


@pytest.mark.parametrize(
    "py", _codex_py(), ids=lambda p: str(p.relative_to(CODEX_ROOT)),
)
def test_codex_py_compiles(py: Path):
    """Syntax/parse gate for the entire shipped codex tree."""
    py_compile.compile(str(py), doraise=True)


@pytest.mark.parametrize("tool", _codex_tools(), ids=lambda p: p.name)
def test_codex_tool_imports(tool: Path):
    """Module-level import sanity: catches bad imports / top-level NameError.

    Tolerates missing optional third-party deps (psycopg2, requests, ...).
    Tools are CLI scripts guarded by `if __name__ == '__main__'`, so importing
    them is side-effect-free.
    """
    spec = importlib.util.spec_from_file_location(f"codex_tool_{tool.stem}", tool)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as exc:
        pytest.skip(f"optional dependency missing: {exc.name}")
    except SystemExit:
        # A tool that exits under an import-time guard — acceptable.
        pass
