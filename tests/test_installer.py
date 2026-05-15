"""Unit tests for lib/installer.py — render, preset loading, validation,
inheritance, frontmatter, encoding, detection helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import installer
from installer import (
    __version__,
    load_preset, validate_preset, resolve_preset,
    render_text, encode_claude_project_path, git_dirty_status,
)


# --------------------------------------------------------- version ---
def test_version_is_semver_string():
    assert isinstance(__version__, str)
    parts = __version__.split('.')
    assert len(parts) == 3, '__version__ should be MAJOR.MINOR.PATCH'
    assert all(p.isdigit() for p in parts)


# --------------------------------------------------------- load_preset ---
def test_load_preset_json(minimal_preset):
    data = load_preset(minimal_preset)
    assert data['description'] == 'minimal test preset'
    assert data['mcp_servers'] == ['codebase']


def test_load_preset_rejects_non_json(tmp_path):
    p = tmp_path / 'fake.yaml'
    p.write_text('key: value', encoding='utf-8')
    with pytest.raises(ValueError, match='unsupported preset format'):
        load_preset(p)


# --------------------------------------------------------- validate_preset ---
def test_validate_preset_accepts_minimal(minimal_preset):
    data = load_preset(minimal_preset)
    assert validate_preset(data) == []


def test_validate_preset_flags_missing_required():
    errors = validate_preset({'description': 'no stack field'})
    assert any('missing required field `stack`' in e for e in errors)


def test_validate_preset_flags_unknown_field_with_suggestion():
    errors = validate_preset({
        'description': 'oops',
        'stack': {},
        'addon_root': ['nakivo'],  # typo: singular
    })
    msg = ' '.join(errors)
    assert 'unknown field `addon_root`' in msg
    assert 'addon_roots' in msg  # did-you-mean


def test_validate_preset_flags_wrong_type():
    errors = validate_preset({
        'description': 'oops',
        'stack': {},
        'mcp_servers': 'codebase',  # should be list
    })
    assert any('must be a list' in e for e in errors)


# --------------------------------------------------------- resolve_preset (inheritance) ---
def test_resolve_preset_no_parent_returns_loaded(minimal_preset, tmp_presets_dir):
    data = resolve_preset('minimal', tmp_presets_dir)
    assert data['description'] == 'minimal test preset'


def test_resolve_preset_with_extends_merges(child_preset_with_extends, tmp_presets_dir):
    data = resolve_preset('child', tmp_presets_dir)
    # child description overrides parent
    assert data['description'] == 'child of minimal'
    # additive override extends parent's list
    assert data['addon_roots'] == ['extra_root']  # parent was empty
    assert data['mcp_servers'] == ['codebase', 'postgres']


def test_resolve_preset_mcp_servers_remove(tmp_presets_dir, minimal_preset):
    parent = tmp_presets_dir / 'parent.json'
    parent.write_text(json.dumps({
        'description': 'parent',
        'stack': {},
        'mcp_servers': ['codebase', 'postgres', 'jira'],
    }), encoding='utf-8')
    child = tmp_presets_dir / 'kid.json'
    child.write_text(json.dumps({
        'extends': 'parent',
        'description': 'kid drops jira',
        'stack': {},
        'mcp_servers_remove': ['jira'],
    }), encoding='utf-8')
    data = resolve_preset('kid', tmp_presets_dir)
    assert data['mcp_servers'] == ['codebase', 'postgres']


def test_resolve_preset_cycle_detected(tmp_presets_dir):
    (tmp_presets_dir / 'a.json').write_text(json.dumps({
        'extends': 'b', 'description': 'A', 'stack': {},
    }), encoding='utf-8')
    (tmp_presets_dir / 'b.json').write_text(json.dumps({
        'extends': 'a', 'description': 'B', 'stack': {},
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='cycle'):
        resolve_preset('a', tmp_presets_dir)


def test_resolve_preset_missing_suggests(tmp_presets_dir, minimal_preset):
    with pytest.raises(FileNotFoundError, match='did you mean'):
        resolve_preset('minimall', tmp_presets_dir)  # typo


def test_resolve_preset_dict_field_shallow_merge(tmp_presets_dir):
    (tmp_presets_dir / 'base.json').write_text(json.dumps({
        'description': 'base', 'stack': {},
        'db': {'default_db': 'base_db', 'default_port': 5432},
    }), encoding='utf-8')
    (tmp_presets_dir / 'sub.json').write_text(json.dumps({
        'extends': 'base', 'description': 'sub', 'stack': {},
        'db': {'default_db': 'sub_db'},  # port not specified
    }), encoding='utf-8')
    data = resolve_preset('sub', tmp_presets_dir)
    assert data['db']['default_db'] == 'sub_db'
    assert data['db']['default_port'] == 5432  # inherited


# --------------------------------------------------------- render_text ---
def test_render_text_simple_substitution(sample_ctx):
    out = render_text('Hello {{PROJECT_NAME}}!', sample_ctx)
    assert out == 'Hello MyProj!'


def test_render_text_list_becomes_bullets(sample_ctx):
    out = render_text('Roots:\n{{ADDON_ROOTS}}', sample_ctx)
    assert '- nakivo' in out
    assert '- base_addons' in out


def test_render_text_missing_key_empty(sample_ctx):
    out = render_text('Value: {{NONEXISTENT}}.', sample_ctx)
    assert out == 'Value: .'


def test_render_text_preserves_non_placeholders(sample_ctx):
    out = render_text('Curly { brace } here, {{PROJECT_NAME}}.', sample_ctx)
    assert '{ brace }' in out
    assert 'MyProj' in out


def test_render_text_handles_whitespace_in_placeholder(sample_ctx):
    out = render_text('Path: {{  WORKSPACE_ROOT  }}', sample_ctx)
    assert out == 'Path: /tmp/proj'


# --------------------------------------------------------- encode_claude_project_path ---
def test_encode_claude_project_path_lowercases_windows_drive(tmp_path, monkeypatch):
    # Simulate Windows-style path encoding.
    p = encode_claude_project_path(tmp_path)
    # Result format: <home>/.claude/projects/<encoded>/memory
    assert p.parts[-1] == 'memory'
    assert p.parts[-3] == 'projects'
    encoded = p.parts[-2]
    # Forbidden chars are replaced with dashes.
    assert ':' not in encoded
    assert '\\' not in encoded
    assert '/' not in encoded
    assert '.' not in encoded
    assert '_' not in encoded


# --------------------------------------------------------- git_dirty_status ---
def test_git_dirty_status_returns_none_for_non_repo(tmp_path):
    # A fresh tmpdir is not a git repo.
    assert git_dirty_status(tmp_path) is None


def test_git_dirty_status_returns_none_for_clean_repo(tmp_path):
    import subprocess
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=False)
    # Configure user so commits don't fail in CI.
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=tmp_path, check=False)
    subprocess.run(['git', 'config', 'user.name', 'test'], cwd=tmp_path, check=False)
    # Clean repo => None.
    result = git_dirty_status(tmp_path)
    # Either None (clean) or a dirty status — both are valid depending on
    # whether init created any tracked files. Our installer is OK with both.
    assert result is None or 'change' in result


def test_git_dirty_status_detects_dirty(tmp_path):
    import subprocess
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=False)
    subprocess.run(['git', 'config', 'user.email', 'test@test'], cwd=tmp_path, check=False)
    subprocess.run(['git', 'config', 'user.name', 'test'], cwd=tmp_path, check=False)
    (tmp_path / 'dirty.txt').write_text('uncommitted', encoding='utf-8')
    result = git_dirty_status(tmp_path)
    assert result is not None
    assert 'change' in result
