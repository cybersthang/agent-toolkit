"""Shared pytest fixtures for agent-toolkit tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / 'lib'))
sys.path.insert(0, str(TOOLKIT_ROOT))


@pytest.fixture
def tmp_presets_dir(tmp_path: Path) -> Path:
    """Empty presets directory the test writes JSON into."""
    d = tmp_path / 'presets'
    d.mkdir()
    return d


@pytest.fixture
def minimal_preset(tmp_presets_dir: Path) -> Path:
    """A preset that satisfies validate_preset minimums."""
    p = tmp_presets_dir / 'minimal.json'
    p.write_text(json.dumps({
        'description': 'minimal test preset',
        'stack': {'language': 'python', 'framework': ''},
        'addon_roots': [],
        'mcp_servers': ['codebase'],
        'rules': ['_common'],
        'skills': ['_common'],
        'memory_packs': [],
    }), encoding='utf-8')
    return p


@pytest.fixture
def child_preset_with_extends(tmp_presets_dir: Path, minimal_preset: Path) -> Path:
    """A preset that extends `minimal` and adds appends/removes."""
    p = tmp_presets_dir / 'child.json'
    p.write_text(json.dumps({
        'extends': 'minimal',
        'description': 'child of minimal',
        'stack': {'language': 'python'},
        'addon_roots_append': ['extra_root'],
        'mcp_servers_append': ['postgres'],
    }), encoding='utf-8')
    return p


@pytest.fixture
def sample_ctx() -> dict:
    """Realistic-ish ctx for render_text tests."""
    return {
        'WORKSPACE_ROOT': '/tmp/proj',
        'PROJECT_NAME': 'MyProj',
        'PYTHON_BIN': '/usr/bin/python',
        'STACK_LABEL': 'Odoo 12 Enterprise',
        'ADDON_ROOTS': ['addons', 'base_addons'],
        'MCP_SERVERS': ['codebase', 'postgres'],
        'TODAY_ISO_DATE': '2026-05-15',
    }


# ============================================================
# G9 v0.11.0 — canonical invariant fixture
#
# Found during v0.10.0 G2 work: `_make_invariants` in test_hooks.py was
# writing `must_keep_regex` at the top of the invariant dict (wrong),
# while production code reads `inv["rules"]["must_keep_regex"]`. Result:
# any test using that fixture exercised the "no violation found" path,
# not the violation path — `test_bypass_token_in_prompt_overrides` PASS-ed
# without ever triggering the bypass logic it claimed to test.
#
# The actual builders live in `_invariant_fixtures.py` (importable). The
# fixtures below wrap them for tests that prefer DI over `from
# _invariant_fixtures import make_invariant`.
# ============================================================
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _invariant_fixtures import make_invariant, write_invariants  # noqa: E402,F401


@pytest.fixture
def make_invariant_fixture():
    """Pytest fixture wrapping `make_invariant` for tests that prefer
    fixture injection over module-level import."""
    return make_invariant


@pytest.fixture
def write_invariants_fixture():
    """Pytest fixture wrapping `write_invariants`."""
    return write_invariants
