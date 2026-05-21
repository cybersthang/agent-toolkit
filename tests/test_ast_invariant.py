"""G3 v0.11.0 — AST-aware invariant tests.

Regex `must_keep_call: ['foo']` matches `foo(` literally. Breaks under
whitespace reformat (`foo (`) and import-alias rename (`from x import
foo as bar; bar()` → no `foo(` in code). AST `must_keep_call_ast` parses
the snippet and inspects Call nodes by name — stricter semantic check.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _invariant_fixtures import make_invariant, write_invariants

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / 'templates' / 'claude' / 'hooks'
PYTHON = sys.executable


def _render_hook(tmp_path: Path) -> Path:
    src = HOOKS_DIR / 'invariant_guard.py'
    dst = tmp_path / 'invariant_guard.py'
    dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    for companion in ('_common.py', '_patterns.py'):
        (tmp_path / companion).write_text(
            (HOOKS_DIR / companion).read_text(encoding='utf-8'),
            encoding='utf-8',
        )
    return dst


def _run(hook: Path, envelope: dict, cwd: Path):
    return subprocess.run(
        [PYTHON, str(hook)],
        input=json.dumps(envelope),
        capture_output=True, text=True, timeout=10,
        cwd=str(cwd),
        env=dict(os.environ, PYTHONIOENCODING='utf-8'),
    )


def _make_inv_ast(inv_id: str, names, severity='blocker',
                  applies_to=('**/*.py',)) -> dict:
    """Build an invariant with must_keep_call_ast rule."""
    if isinstance(names, str):
        names = [names]
    inv = make_invariant(inv_id, must_keep_regex='__placeholder__',
                         severity=severity, applies_to=list(applies_to))
    # Replace the placeholder rule with AST-only.
    inv['rules'] = {'must_keep_call_ast': list(names)}
    return inv


class TestASTCallDetection:

    def test_direct_call_removed_caught_by_ast(self, tmp_path):
        """Edit removes `foo()` call → AST detects, hook denies."""
        hook = _render_hook(tmp_path)
        write_invariants(tmp_path, _make_inv_ast('INV-AST', 'compute_total'))
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'app.py'),
                'old_string': 'x = compute_total(items)',
                'new_string': 'x = 0',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if result.stdout.strip() else {}
        out = decision.get('hookSpecificOutput', {})
        assert out.get('permissionDecision') == 'deny', (
            f'AST must catch direct call removal; got: {decision}'
        )
        reason = out.get('permissionDecisionReason', '')
        assert 'ast-call:compute_total' in reason

    def test_method_call_removed_caught_by_ast(self, tmp_path):
        """Edit removes `obj.method()` → AST detects via Attribute node."""
        hook = _render_hook(tmp_path)
        write_invariants(tmp_path, _make_inv_ast('INV-AST', 'dispatch'))
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'app.py'),
                'old_string': 'self.dispatch(request)',
                'new_string': 'pass',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if result.stdout.strip() else {}
        out = decision.get('hookSpecificOutput', {})
        assert out.get('permissionDecision') == 'deny'

    def test_call_kept_allows(self, tmp_path):
        """Edit reformats but keeps `foo()` → AST sees call present, allow."""
        hook = _render_hook(tmp_path)
        write_invariants(tmp_path, _make_inv_ast('INV-AST', 'compute_total'))
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'app.py'),
                'old_string': 'x = compute_total(items)',
                'new_string': 'x = compute_total(\n    items\n)',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if result.stdout.strip() else {}
        out = decision.get('hookSpecificOutput', {})
        assert out.get('permissionDecision') == 'allow'

    def test_non_python_file_skips_ast_check(self, tmp_path):
        """Invariant with only must_keep_call_ast + applies_to *.xml →
        AST shouldn't try to parse XML. File extension check skips AST."""
        hook = _render_hook(tmp_path)
        inv = _make_inv_ast('INV-AST', 'compute_total',
                            applies_to=['**/*.xml'])
        write_invariants(tmp_path, inv)
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'view.xml'),
                'old_string': '<compute_total/>',
                'new_string': '<other/>',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if result.stdout.strip() else {}
        out = decision.get('hookSpecificOutput', {})
        # AST skip for non-Python → must_keep_call_ast is the ONLY rule →
        # no patterns, no violation, allow.
        assert out.get('permissionDecision') == 'allow'

    def test_parse_failure_falls_back_silently(self, tmp_path):
        """Partial Python that fails ast.parse → AST inconclusive, no
        false-positive violation. (Falls back to allow when only AST rule.)"""
        hook = _render_hook(tmp_path)
        write_invariants(tmp_path, _make_inv_ast('INV-AST', 'foo'))
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'app.py'),
                'old_string': 'def half_function(',  # syntax error
                'new_string': 'def half_function(',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if result.stdout.strip() else {}
        out = decision.get('hookSpecificOutput', {})
        # AST can't parse old OR new → returns empty removed list → allow.
        assert out.get('permissionDecision') == 'allow'

    def test_ast_complements_regex_must_keep_call(self, tmp_path):
        """Same invariant has BOTH regex must_keep_call AND must_keep_call_ast
        — both should report removal. Belt-and-suspenders."""
        hook = _render_hook(tmp_path)
        inv = make_invariant('INV-BOTH',
                             must_keep_call='process',
                             applies_to=['**/*.py'],
                             severity='blocker')
        # Add AST rule alongside.
        inv['rules']['must_keep_call_ast'] = ['process']
        write_invariants(tmp_path, inv)
        result = _run(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'app.py'),
                'old_string': 'result = process(data)',
                'new_string': 'result = None',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if result.stdout.strip() else {}
        out = decision.get('hookSpecificOutput', {})
        assert out.get('permissionDecision') == 'deny'
        reason = out.get('permissionDecisionReason', '')
        # Both rule signals should appear (regex + ast).
        assert 'call:process' in reason
        assert 'ast-call:process' in reason

    def test_write_tool_full_file_ast(self, tmp_path):
        """Write tool gets full file content; AST checks new content
        contains required call names."""
        hook = _render_hook(tmp_path)
        write_invariants(tmp_path, _make_inv_ast('INV-W', 'init_logger'))
        # New file content WITHOUT init_logger call → violation.
        result = _run(hook, {
            'tool_name': 'Write',
            'tool_input': {
                'file_path': str(tmp_path / 'main.py'),
                'content': 'def run():\n    pass\n',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        decision = json.loads(result.stdout) if result.stdout.strip() else {}
        out = decision.get('hookSpecificOutput', {})
        assert out.get('permissionDecision') == 'deny'

        # Write with init_logger call → allowed.
        result2 = _run(hook, {
            'tool_name': 'Write',
            'tool_input': {
                'file_path': str(tmp_path / 'main.py'),
                'content': 'def run():\n    init_logger()\n',
            },
            'cwd': str(tmp_path),
        }, tmp_path)
        decision2 = json.loads(result2.stdout) if result2.stdout.strip() else {}
        out2 = decision2.get('hookSpecificOutput', {})
        assert out2.get('permissionDecision') == 'allow'
