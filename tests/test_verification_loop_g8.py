"""G8 v0.11.0 — verification_loop decoupling from Odoo via preset-driven
`probe_rules` / `probe_metadata` in `.agent-toolkit/verification.json`.

Backward compat: when neither field is set, the hook must continue to
emit Odoo defaults (.py → syntax, __manifest__.py → manifest, .xml →
xml_validate). New: when `probe_rules` is set, classification follows
the declarative rules; when `probe_metadata` is set, kinds map to
project-specific MCP probe names.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / 'templates' / 'claude' / 'hooks'
PYTHON = sys.executable


def _render_hook(tmp_path: Path) -> Path:
    src = HOOKS_DIR / 'verification_loop.py'
    dst = tmp_path / 'verification_loop.py'
    dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    for companion in ('_common.py', '_patterns.py'):
        comp_src = HOOKS_DIR / companion
        if comp_src.exists():
            (tmp_path / companion).write_text(
                comp_src.read_text(encoding='utf-8'), encoding='utf-8'
            )
    return dst


def _write_config(workspace: Path, cfg: dict) -> None:
    d = workspace / '.agent-toolkit'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'verification.json').write_text(json.dumps(cfg), encoding='utf-8')


def _run(hook: Path, envelope: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, str(hook)],
        input=json.dumps(envelope),
        capture_output=True, text=True, timeout=10,
        cwd=str(cwd),
        env=dict(os.environ, PYTHONIOENCODING='utf-8'),
    )


def _make_py_file(tmp_path: Path, rel: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('# stub', encoding='utf-8')
    return p


class TestBackwardCompatOdoo:

    def test_no_probe_rules_falls_back_to_odoo_defaults(self, tmp_path):
        """Empty config (no probe_rules) → still nudges Odoo probes for .py."""
        hook = _render_hook(tmp_path)
        _write_config(tmp_path, {
            'enabled': True,
            'addon_globs': ['**/*.py'],
        })
        py_file = _make_py_file(tmp_path, 'models/account.py')
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {'file_path': str(py_file),
                           'old_string': 'a', 'new_string': 'b'},
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'python_syntax_check' in ctx, (
            f'Default Odoo behaviour must nudge python_syntax_check; got: {ctx[:300]}'
        )

    def test_manifest_still_gets_special_probe(self, tmp_path):
        hook = _render_hook(tmp_path)
        _write_config(tmp_path, {
            'enabled': True,
            'addon_globs': ['**/__manifest__.py'],
        })
        # Need a real addon dir structure
        addon = tmp_path / 'my_addon'
        addon.mkdir()
        manifest = addon / '__manifest__.py'
        manifest.write_text("{'name': 'test'}", encoding='utf-8')
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {'file_path': str(manifest),
                           'old_string': 'a', 'new_string': 'b'},
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'odoo_manifest_validate' in ctx


class TestPresetDrivenProbeRules:

    def test_django_style_probe_rules_django_check(self, tmp_path):
        """Django project ships probe_rules + probe_metadata mapping
        .py → django_check (instead of python_syntax_check)."""
        hook = _render_hook(tmp_path)
        _write_config(tmp_path, {
            'enabled': True,
            'mcp_prefix': 'mcp__django__',
            'addon_globs': ['**/*.py'],
            'probe_rules': [
                {'match': {'suffix': '.py'}, 'kinds': ['django_check']},
            ],
            'probe_metadata': {
                'django_check': {
                    'mcp': 'django_system_check',
                    'desc': 'django manage.py check equivalent',
                },
            },
        })
        py_file = _make_py_file(tmp_path, 'app/models.py')
        result = _run(hook, {
            'tool_name': 'Write',
            'tool_input': {'file_path': str(py_file), 'content': 'x'},
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'django_system_check' in ctx, (
            f'Custom probe should appear; got: {ctx[:300]}'
        )
        # Crucial: Odoo defaults must NOT leak when probe_rules is set.
        assert 'python_syntax_check' not in ctx, (
            'Odoo default must NOT leak when probe_rules is defined'
        )

    def test_unknown_kind_emits_generic_line(self, tmp_path):
        """probe_rules emits kind with no probe_metadata entry → generic
        fallback line so the kind isn't silently dropped."""
        hook = _render_hook(tmp_path)
        _write_config(tmp_path, {
            'enabled': True,
            'addon_globs': ['**/*.py'],
            'probe_rules': [
                {'match': {'suffix': '.py'}, 'kinds': ['mystery_kind']},
            ],
        })
        py_file = _make_py_file(tmp_path, 'foo.py')
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {'file_path': str(py_file),
                           'old_string': 'a', 'new_string': 'b'},
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'mystery_kind' in ctx
        assert 'probe_metadata' in ctx  # generic line points DEV at config

    def test_multiple_rules_emit_multiple_kinds(self, tmp_path):
        hook = _render_hook(tmp_path)
        _write_config(tmp_path, {
            'enabled': True,
            'addon_globs': ['**/*.py'],
            'probe_rules': [
                {'match': {'suffix': '.py'}, 'kinds': ['k1', 'k2']},
                {'match': {'basename': 'special.py'}, 'kinds': ['k3']},
            ],
            'probe_metadata': {
                'k1': {'mcp': 'probe_one', 'desc': 'first'},
                'k2': {'mcp': 'probe_two', 'desc': 'second'},
                'k3': {'mcp': 'probe_three', 'desc': 'third'},
            },
        })
        py_file = _make_py_file(tmp_path, 'special.py')
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {'file_path': str(py_file),
                           'old_string': 'a', 'new_string': 'b'},
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        for probe in ('probe_one', 'probe_two', 'probe_three'):
            assert probe in ctx, f'{probe} missing from output'

    def test_glob_match_criteria(self, tmp_path):
        hook = _render_hook(tmp_path)
        _write_config(tmp_path, {
            'enabled': True,
            'addon_globs': ['**/*.py'],
            'probe_rules': [
                {'match': {'glob': '*/views/*.py'},
                 'kinds': ['views_only']},
            ],
            'probe_metadata': {
                'views_only': {'mcp': 'view_check', 'desc': 'view files'},
            },
        })
        # File matching glob:
        py_file = _make_py_file(tmp_path, 'app/views/list.py')
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {'file_path': str(py_file),
                           'old_string': 'a', 'new_string': 'b'},
            'cwd': str(tmp_path),
        }, tmp_path)
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'view_check' in ctx

        # File NOT matching glob — hook should be silent (no kinds).
        py_file2 = _make_py_file(tmp_path, 'app/models/account.py')
        result2 = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {'file_path': str(py_file2),
                           'old_string': 'a', 'new_string': 'b'},
            'cwd': str(tmp_path),
        }, tmp_path)
        # No matching kinds → silent exit.
        assert (result2.stdout or "").strip() == '' or 'view_check' not in (
            json.loads(result2.stdout).get('hookSpecificOutput', {})
                .get('additionalContext', '') if (result2.stdout or "").strip() else ''
        )
