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
        'ADDON_ROOTS': ['nakivo', 'base_addons'],
        'MCP_SERVERS': ['codebase', 'postgres'],
        'TODAY_ISO_DATE': '2026-05-15',
    }
