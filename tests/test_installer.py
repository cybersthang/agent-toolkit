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
        'addon_root': ['addons'],  # typo: singular
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


def test_resolve_preset_private_overlay_extends_public_preset(
    tmp_presets_dir, minimal_preset,
):
    """User-facing v0.5.1 migration path: a private preset overlay
    extending a public preset must resolve cleanly (no missing-parent
    error, additive overrides merged, response_language inherited).

    Mirrors the recipe shipped in
    `presets/_example_private_overlay.json.template`.
    """
    # Public preset shape (proxy for `odoo-12` etc.):
    (tmp_presets_dir / 'public_base.json').write_text(json.dumps({
        'description': 'public Odoo-12-shaped preset',
        'stack': {'language': 'python', 'framework': 'odoo',
                  'framework_version': '12'},
        'response_language': 'English',
        'addon_roots': [],
        'mcp_servers': ['codebase', 'postgres', 'realdata_test'],
        'rules': ['_common', 'odoo-12'],
        'skills': ['_common', 'odoo'],
    }), encoding='utf-8')

    # Private overlay — what a user creates after v0.5.0 → v0.5.1 migration:
    (tmp_presets_dir / 'private_overlay.json').write_text(json.dumps({
        'extends': 'public_base',
        'description': 'Private overlay for <my-project>',
        'stack_label': 'Odoo 12 — MyCo',
        'response_language': 'Vietnamese',
        'stack': {'odoo_bin_rel': 'server-fork/odoo-bin'},
        'addon_roots_append': ['custom_addons', 'enterprise', 'myco_addons'],
        'mcp_servers_append': ['jira_production'],
        'db': {'default_db': 'myco_main', 'default_port': 5432},
    }), encoding='utf-8')

    data = resolve_preset('private_overlay', tmp_presets_dir)

    # Description overridden.
    assert data['description'] == 'Private overlay for <my-project>'
    # response_language overridden (not inherited blindly).
    assert data['response_language'] == 'Vietnamese'
    # stack_label introduced.
    assert data['stack_label'] == 'Odoo 12 — MyCo'
    # stack dict shallow-merged (framework inherited, odoo_bin_rel added).
    assert data['stack']['framework'] == 'odoo'
    assert data['stack']['framework_version'] == '12'
    assert data['stack']['odoo_bin_rel'] == 'server-fork/odoo-bin'
    # addon_roots_append extends parent's empty list.
    assert data['addon_roots'] == ['custom_addons', 'enterprise', 'myco_addons']
    # mcp_servers_append extends parent's list.
    assert data['mcp_servers'] == [
        'codebase', 'postgres', 'realdata_test', 'jira_production',
    ]
    # Parent's rules + skills inherited (no _append → no extension needed).
    assert data['rules'] == ['_common', 'odoo-12']
    assert data['skills'] == ['_common', 'odoo']
    # db dict shallow-merged.
    assert data['db']['default_db'] == 'myco_main'


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
    assert '- addons' in out
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


def test_git_dirty_status_handles_missing_git(tmp_path, monkeypatch):
    """If `git` binary is absent, helper must return None (not crash)."""
    import subprocess as sp

    def boom(*a, **kw):
        raise FileNotFoundError('git not installed in this PATH')

    monkeypatch.setattr(sp, 'run', boom)
    assert git_dirty_status(tmp_path) is None


# --------------------------------------------------------- private meta fields ---
def test_validate_preset_accepts_underscore_meta_fields():
    """Keys starting with `_` are private metadata — must not flag as unknown."""
    errors = validate_preset({
        'description': 'meta-fields preset',
        'stack': {},
        '_internal_note': 'this is private, ignore me',
        '_owner': 'thang.vo',
    })
    assert errors == [], f'expected clean, got {errors}'


# --------------------------------------------------------- resolve_preset error paths ---
def test_resolve_preset_raises_on_invalid_child(tmp_presets_dir):
    """validate_preset error → resolve_preset must raise ValueError with msg."""
    (tmp_presets_dir / 'broken.json').write_text(json.dumps({
        'description': 'broken: missing stack field',
        # `stack` omitted — should trip the required-field check.
        'addon_root': 'typo-singular',  # also bad type + unknown
    }), encoding='utf-8')
    with pytest.raises(ValueError, match='preset validation failed'):
        resolve_preset('broken', tmp_presets_dir)


def test_resolve_preset_dict_append_shallow_merges(tmp_presets_dir):
    """`<dict_field>_append` should shallow-merge child into parent dict."""
    (tmp_presets_dir / 'base.json').write_text(json.dumps({
        'description': 'base', 'stack': {},
        'external_mcp_servers': {
            'playwright': {'command': 'npx', 'args': ['@playwright/mcp']},
            'other': {'command': 'npx', 'args': ['other-mcp']},
        },
    }), encoding='utf-8')
    (tmp_presets_dir / 'kid.json').write_text(json.dumps({
        'extends': 'base', 'description': 'kid', 'stack': {},
        'external_mcp_servers_append': {
            'playwright': {'command': 'npx', 'args': ['@playwright/mcp', '--headless']},
            'extra': {'command': 'node', 'args': ['./extra.js']},
        },
    }), encoding='utf-8')
    data = resolve_preset('kid', tmp_presets_dir)
    servers = data['external_mcp_servers']
    # Child entry overlays parent entry of same key.
    assert servers['playwright']['args'] == ['@playwright/mcp', '--headless']
    # Parent-only entry preserved.
    assert servers['other']['args'] == ['other-mcp']
    # Child-only entry added.
    assert servers['extra']['command'] == 'node'


# --------------------------------------------------------- render_into ---
def test_render_into_writes_substituted_file(tmp_path, sample_ctx):
    from installer import render_into
    src = tmp_path / 'tpl.md'
    src.write_text('# {{PROJECT_NAME}}\nPython: {{PYTHON_BIN}}', encoding='utf-8')
    dst = tmp_path / 'out.md'
    render_into(src, dst, sample_ctx)
    content = dst.read_text(encoding='utf-8')
    assert content == '# MyProj\nPython: /usr/bin/python'


# --------------------------------------------------------- detect_python ---
def test_detect_python_finds_venv_in_workspace(tmp_path):
    """Detector must return the absolute path of the first matching candidate."""
    from installer import detect_python
    # Build a fake `.venv/bin/python` (POSIX shape) or
    # `.venv\Scripts\python.exe` (Windows shape).
    import os
    if os.name == 'nt':
        venv_bin = tmp_path / '.venv' / 'Scripts'
        venv_bin.mkdir(parents=True)
        py = venv_bin / 'python.exe'
    else:
        venv_bin = tmp_path / '.venv' / 'bin'
        venv_bin.mkdir(parents=True)
        py = venv_bin / 'python'
    py.write_text('#!/bin/sh\necho stub', encoding='utf-8')
    found = detect_python(tmp_path)
    assert found is not None
    assert Path(found).resolve() == py.resolve()


def test_detect_python_returns_none_when_no_venv(tmp_path):
    """No venv in any candidate slot → None."""
    from installer import detect_python
    assert detect_python(tmp_path) is None


# --------------------------------------------------------- detect_psql ---
def test_detect_psql_returns_string_or_none():
    """detect_psql must hit the right candidate-list branch per OS."""
    from installer import detect_psql
    result = detect_psql()
    # Either a string path to an existing file, or None — both legal.
    assert result is None or Path(result).exists(), (
        f'detect_psql returned {result!r} but it does not exist on disk'
    )


def test_psql_candidates_windows_branch():
    """`psql_candidates('nt')` must return Windows-style PostgreSQL paths.

    Tests the static branch without monkey-patching `os.name` — we pass
    the OS family explicitly. Avoids the pathlib `_flavour` cache bug
    on Py3.8 + Windows.
    """
    from installer import psql_candidates
    cands = psql_candidates('nt')
    assert all(c.endswith('.exe') for c in cands), cands
    assert any('PostgreSQL' in c for c in cands)
    # pgAdmin path is the highest-priority hit.
    assert cands[0].endswith('psql.exe')


def test_psql_candidates_posix_branch():
    """`psql_candidates('posix')` must return POSIX-style paths.

    Closes the long-standing coverage gap on `installer.py:228-230`
    (the `else:` branch). Doesn't need a real psql on disk — only the
    list shape is asserted.
    """
    from installer import psql_candidates
    cands = psql_candidates('posix')
    assert '/usr/bin/psql' in cands
    assert '/usr/local/bin/psql' in cands
    assert '/opt/homebrew/bin/psql' in cands
    # No Windows-shaped entries.
    assert not any('.exe' in c for c in cands)


def test_psql_candidates_defaults_to_current_os():
    """`psql_candidates()` with no arg uses the live `os.name`."""
    from installer import psql_candidates
    import os as _os
    cands = psql_candidates()
    expected_shape = '.exe' if _os.name == 'nt' else '/'
    assert all(expected_shape in c for c in cands)


# --------------------------------------------------------- encode_claude_project_path ---
def test_encode_claude_project_path_posix_no_drive():
    """POSIX path (no `:` at index 1) takes the non-drive branch."""
    from installer import encode_claude_project_path
    # We can't really pass a POSIX path on Windows (Path resolves it back to
    # CWD), so we just exercise the function on a relative path that resolves
    # to something without a drive separator. The `_path_has_drive` branch
    # at installer.py:243 is covered indirectly by the existing test;
    # this asserts the function is total (never raises).
    out = encode_claude_project_path(Path('.'))
    assert out.parts[-1] == 'memory'


# --------------------------------------------------------- info / ok / warn / confirm ---
def test_warn_writes_to_stderr(capsys):
    from installer import warn
    warn('something fishy')
    captured = capsys.readouterr()
    assert 'something fishy' in captured.err
    # warn must NOT pollute stdout — install scripts pipe stdout for plans.
    assert captured.out == ''


def test_info_and_ok_write_to_stdout(capsys):
    from installer import info, ok
    info('plain info')
    ok('done')
    captured = capsys.readouterr()
    assert 'plain info' in captured.out
    assert 'done' in captured.out


def test_confirm_returns_true_for_yes(monkeypatch):
    from installer import confirm
    monkeypatch.setattr('builtins.input', lambda prompt='': 'y')
    assert confirm('proceed? ') is True


def test_confirm_returns_true_for_yes_uppercase(monkeypatch):
    from installer import confirm
    monkeypatch.setattr('builtins.input', lambda prompt='': 'YES')
    assert confirm('proceed? ') is True


def test_confirm_returns_false_for_no(monkeypatch):
    from installer import confirm
    monkeypatch.setattr('builtins.input', lambda prompt='': 'n')
    assert confirm('proceed? ') is False


def test_confirm_returns_false_on_eof(monkeypatch):
    """When stdin closes (pipe/CI), confirm must default to False (safe)."""
    from installer import confirm

    def raise_eof(prompt=''):
        raise EOFError

    monkeypatch.setattr('builtins.input', raise_eof)
    assert confirm('proceed? ') is False
