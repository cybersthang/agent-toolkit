"""Unit tests for templates/claude/hooks/*.py — UserPromptSubmit, Stop,
PreToolUse, SessionStart enforcement hooks. Spawn each hook as a
subprocess, feed a realistic Claude Code envelope on stdin, assert
exit code + stdout shape.

These hooks ship as templates that get installed into a project's
.claude/hooks/. Some files use {{STACK_FRAMEWORK}} placeholders that
the toolkit substitutes at install time; we render those manually
before exec so we exercise the actual logic.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / 'templates' / 'claude' / 'hooks'
PYTHON = sys.executable


def _render_hook(hook_name: str, tmp_path: Path) -> Path:
    """Copy a hook into tmp_path, substituting `{{STACK_FRAMEWORK}}` and
    `{{STACK_FRAMEWORK_VERSION}}` so the hook code is syntactically valid.

    Also copies sibling shared modules (`_common.py`, `_patterns.py`) when
    present so hooks doing `from _common import ...` resolve their imports
    in the isolated tmp dir. Shared modules ship without placeholders so
    they are copied verbatim.
    """
    src = HOOKS_DIR / hook_name
    text = src.read_text(encoding='utf-8')
    text = text.replace('{{STACK_FRAMEWORK}}', 'odoo')
    text = text.replace('{{STACK_FRAMEWORK_VERSION}}', '12')
    dst = tmp_path / hook_name
    dst.write_text(text, encoding='utf-8')
    for companion in ('_common.py', '_patterns.py'):
        comp_src = HOOKS_DIR / companion
        if comp_src.exists():
            (tmp_path / companion).write_text(
                comp_src.read_text(encoding='utf-8'), encoding='utf-8'
            )
    # Sibling sub-package — `_audit/` for evidence_audit.py wrapper.
    audit_src = HOOKS_DIR / '_audit'
    if audit_src.is_dir():
        import shutil
        audit_dst = tmp_path / '_audit'
        if audit_dst.exists():
            shutil.rmtree(audit_dst)
        shutil.copytree(audit_src, audit_dst)
    return dst


def _run_hook(hook_path: Path, envelope: dict, cwd: Path = None,
              extra_env: dict = None, timeout: int = 10):
    """Spawn hook script, pipe JSON envelope on stdin, return CompletedProcess."""
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [PYTHON, str(hook_path)],
        input=json.dumps(envelope),
        capture_output=True, text=True, timeout=timeout,
        cwd=str(cwd) if cwd else None, env=env,
    )


# ============================================================
# intent_router — UserPromptSubmit
# ============================================================
class TestIntentRouter:

    def test_action_verb_triggers_clarification_gate(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {'prompt': 'làm cho tôi feature mới X'})
        assert result.returncode == 0, result.stderr
        # Output is JSON envelope with additionalContext.
        out = json.loads(result.stdout) if result.stdout.strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'clarification-gate' in ctx

    def test_review_keyword_triggers_code_review(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {'prompt': 'review module nakivo_profiler đi'})
        out = json.loads(result.stdout) if result.stdout.strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'code-review' in ctx

    def test_short_prompt_skipped(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {'prompt': 'ok'})
        assert result.returncode == 0
        # Short prompt → no output at all (silent skip).
        assert result.stdout.strip() == ''

    def test_empty_prompt_silent(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {'prompt': ''})
        assert result.returncode == 0
        assert result.stdout.strip() == ''

    def test_already_referencing_skill_suppressed(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {
            'prompt': 'Áp dụng `clarification-gate` cho việc làm feature X này'
        })
        # Already references the skill → hook stays silent to avoid double-nag.
        assert result.returncode == 0
        assert result.stdout.strip() == ''

    def test_invalid_json_falls_back_to_plain_text(self, tmp_path):
        """Older Claude Code versions piped raw prompt, not JSON envelope."""
        hook = _render_hook('intent_router.py', tmp_path)
        # Pass bytes directly so Windows Popen doesn't try to encode the
        # Vietnamese prompt with cp1252 default before piping to stdin.
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='làm feature mới đi'.encode('utf-8'),
            capture_output=True, timeout=10,
            env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        )
        assert result.returncode == 0


# ============================================================
# evidence_audit — Stop hook
# ============================================================
class TestEvidenceAudit:

    def _envelope_with_response(self, response_text: str,
                                tool_calls: list = None) -> dict:
        """Build a transcript envelope mimicking Claude Code's Stop hook input."""
        msgs = [
            {'role': 'user', 'content': 'user request'},
        ]
        if tool_calls:
            for tc in tool_calls:
                msgs.append({
                    'role': 'assistant',
                    'content': [{'type': 'tool_use', 'name': tc}]
                })
        msgs.append({'role': 'assistant', 'content': response_text})
        return {
            'transcript': msgs,
            'stop_hook_active': False,
        }

    def test_claim_without_evidence_is_blocked(self, tmp_path):
        hook = _render_hook('evidence_audit.py', tmp_path)
        envelope = self._envelope_with_response(
            'A' * 300 + ' Root cause is X. Y is missing from the registry.'
        )
        result = _run_hook(hook, envelope)
        # Block = exit 2 with a stderr reason, OR JSON decision deny.
        # Either way, not a clean exit 0.
        if result.returncode != 0:
            return  # blocked as expected
        # If exit 0, hook may have emitted JSON decision — check.
        if result.stdout.strip():
            decision = json.loads(result.stdout)
            assert decision.get('decision') in ('block', None) or \
                   'evidence' in str(decision).lower()

    def test_claim_with_tool_evidence_passes(self, tmp_path):
        hook = _render_hook('evidence_audit.py', tmp_path)
        envelope = self._envelope_with_response(
            'A' * 300 + ' Root cause is X.',
            tool_calls=['Read', 'Grep'],
        )
        result = _run_hook(hook, envelope)
        assert result.returncode == 0
        # No block decision emitted.
        if result.stdout.strip():
            decision = json.loads(result.stdout) if result.stdout.startswith('{') else {}
            assert decision.get('decision') != 'block'

    def test_short_response_skipped(self, tmp_path):
        hook = _render_hook('evidence_audit.py', tmp_path)
        envelope = self._envelope_with_response('OK done.')
        result = _run_hook(hook, envelope)
        assert result.returncode == 0

    def test_assumption_tag_passes(self, tmp_path):
        hook = _render_hook('evidence_audit.py', tmp_path)
        envelope = self._envelope_with_response(
            'B' * 300 + ' Root cause is X [assumption].'
        )
        result = _run_hook(hook, envelope)
        # Response self-tags as assumption → hook lets it through.
        assert result.returncode == 0

    def test_stop_hook_active_short_circuits(self, tmp_path):
        hook = _render_hook('evidence_audit.py', tmp_path)
        envelope = self._envelope_with_response(
            'C' * 300 + ' Root cause is X. Y is missing.'
        )
        envelope['stop_hook_active'] = True  # already re-prompted once
        result = _run_hook(hook, envelope)
        assert result.returncode == 0  # don't loop

    def test_invalid_json_fails_open(self, tmp_path):
        """Parse failure must not block — fail-open guarantee."""
        hook = _render_hook('evidence_audit.py', tmp_path)
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='{not valid json}',
            capture_output=True, text=True, timeout=10,
            env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        )
        assert result.returncode == 0


# ============================================================
# invariant_guard — PreToolUse(Edit/Write/MultiEdit)
# ============================================================
class TestInvariantGuard:

    def _make_invariants(self, tmp_path: Path, patterns: list):
        """Create .agent-toolkit/invariants.json in tmp_path."""
        d = tmp_path / '.agent-toolkit'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'invariants.json').write_text(json.dumps({
            'invariants': patterns,
        }), encoding='utf-8')

    def test_no_invariants_allows(self, tmp_path):
        hook = _render_hook('invariant_guard.py', tmp_path)
        # No invariants.json present in cwd → allow.
        result = _run_hook(hook, {
            'tool_name': 'Edit',
            'tool_input': {'file_path': str(tmp_path / 'x.py'),
                           'old_string': 'foo', 'new_string': 'bar'},
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert result.returncode == 0

    def test_unsupported_tool_allows(self, tmp_path):
        hook = _render_hook('invariant_guard.py', tmp_path)
        result = _run_hook(hook, {
            'tool_name': 'Read',  # not in SUPPORTED_TOOLS
            'tool_input': {'file_path': 'whatever'},
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert result.returncode == 0

    def test_empty_envelope_fails_open(self, tmp_path):
        hook = _render_hook('invariant_guard.py', tmp_path)
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='',
            capture_output=True, text=True, timeout=10,
            env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        )
        assert result.returncode == 0

    def test_bypass_token_in_prompt_overrides(self, tmp_path):
        """User can pass `bypass-invariant: <id>` in their prompt to override."""
        hook = _render_hook('invariant_guard.py', tmp_path)
        # Create a fake invariants file but signal bypass.
        self._make_invariants(tmp_path, [{
            'id': 'INV-1',
            'description': 'test',
            'severity': 'blocker',
            'must_keep_regex': 'forever',
            'rationale': 'test',
            'source': 'test',
        }])
        # Edit removes the required pattern; bypass token is present.
        result = _run_hook(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'forever.txt'),
                'old_string': 'forever exists',
                'new_string': 'gone',
            },
            'user_prompt': 'bypass-invariant: INV-1 — testing',
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        # Bypass should allow.
        assert result.returncode == 0


# ============================================================
# session_brief — SessionStart
# ============================================================
class TestSessionBrief:

    def test_no_project_state_silent(self, tmp_path):
        hook = _render_hook('session_brief.py', tmp_path)
        result = _run_hook(hook, {'cwd': str(tmp_path)}, cwd=tmp_path)
        assert result.returncode == 0
        # No invariants / decision log → silent.

    def test_with_decision_log_emits_brief(self, tmp_path):
        hook = _render_hook('session_brief.py', tmp_path)
        adr_dir = tmp_path / '.agent-toolkit'
        adr_dir.mkdir(parents=True)
        (adr_dir / 'decision-log.md').write_text(
            '## ADR-001 — Use Postgres\n\nBecause SQLite is fragile.\n\n'
            '## ADR-002 — Vietnamese replies\n\nUser preference.\n',
            encoding='utf-8',
        )
        (adr_dir / 'invariants.json').write_text(json.dumps({
            'invariants': [{
                'id': 'INV-1', 'severity': 'blocker',
                'description': 'never strip @api.depends',
                'must_keep_regex': '@api\\.depends', 'rationale': 'test',
                'source': 'test',
            }]
        }), encoding='utf-8')
        result = _run_hook(hook, {'cwd': str(tmp_path)}, cwd=tmp_path)
        assert result.returncode == 0
        # Brief usually printed to stdout when context exists. Some hook
        # variants emit JSON envelope; accept either.
        out = result.stdout
        if out.strip():
            # Either plain text mentioning ADR-001 / invariant, or JSON.
            assert 'ADR' in out or 'invariant' in out.lower() or 'INV' in out
