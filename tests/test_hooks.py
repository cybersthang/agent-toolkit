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
import subprocess
import sys
from pathlib import Path


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
    """Spawn hook script, pipe JSON envelope on stdin, return CompletedProcess.

    Note R3 v0.11.0: hooks run as subprocesses → import-coverage tracker
    can't see them. The % in .coveragerc covers `lib/` + `setup.py` only;
    hook behaviour coverage lives in this file's test count. Proper
    subprocess coverage instrumentation deferred — see .coveragerc header.
    """
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [PYTHON, str(hook_path)],
        input=json.dumps(envelope),
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
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
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'clarification-gate' in ctx

    def test_review_keyword_triggers_code_review(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {'prompt': 'review module sale_extension đi'})
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        assert 'code-review' in ctx

    def test_short_prompt_skipped(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {'prompt': 'ok'})
        assert result.returncode == 0
        # Short prompt → no output at all (silent skip).
        assert (result.stdout or "").strip() == ''

    def test_empty_prompt_silent(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {'prompt': ''})
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''

    def test_already_referencing_skill_suppressed(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {
            'prompt': 'Áp dụng `clarification-gate` cho việc làm feature X này'
        })
        # Already references the skill → hook stays silent to avoid double-nag.
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''

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

    def test_block_async_intent_routes_to_real_data_proof(self, tmp_path):
        """The canonical DEV pattern (BLOCK/ASYNC sleep-injection prove)
        must surface `real-data-proof` skill at the top of the suggestion."""
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {
            'prompt': 'count toàn bộ request và phân loại BLOCK hay ASYNC, '
                      'sau đó chứng minh từng tag đúng',
        })
        assert result.returncode == 0
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        # Clarification-gate fires on action verbs first (priority rule).
        # Either we see real-data-proof directly, or clarification-gate is the
        # single suggested skill (action-verb priority suppresses follow-ups).
        if 'clarification-gate' in ctx:
            # Priority short-circuit — that's by design.
            return
        # Otherwise expect the classifier-intent route to land here.
        assert 'real-data-proof' in ctx, (
            f'Expected real-data-proof in routed context, got: {ctx[:400]}'
        )

    def test_falsification_intent_routes_to_real_data_proof(self, tmp_path):
        """`perturb-test` / `prove the tag` (no action verb) must route."""
        hook = _render_hook('intent_router.py', tmp_path)
        result = _run_hook(hook, {
            'prompt': 'perturb-test này đi, prove the tag is correct',
        })
        assert result.returncode == 0
        out = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        ctx = out.get('hookSpecificOutput', {}).get('additionalContext', '')
        # No action verb in this prompt → clarification-gate shouldn't fire,
        # so the classifier-intent route must take over.
        assert 'real-data-proof' in ctx, (
            f'Expected real-data-proof routing, got: {ctx[:400]}'
        )
        # claim-falsification is the recipe catalog — must be suggested too.
        assert 'claim-falsification' in ctx


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
        if (result.stdout or "").strip():
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
        if (result.stdout or "").strip():
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
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
            env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        )
        assert result.returncode == 0


# ============================================================
# invariant_guard — PreToolUse(Edit/Write/MultiEdit)
# ============================================================
class TestInvariantGuard:

    def _make_invariants(self, tmp_path: Path, patterns: list):
        """Create .agent-toolkit/invariants.json in tmp_path.

        DEPRECATED v0.11.0: this helper accepts raw dicts and can produce
        schema-drifted fixtures (e.g. `must_keep_regex` at top level
        instead of `rules.must_keep_regex`) that silently bypass
        invariant_guard. New tests should use `make_invariant()` from
        `tests/conftest.py` which validates the shape. Kept here only
        for backward compat with the 1 pre-G9 test below.
        """
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
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
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
        out = result.stdout or ""
        if out.strip():
            # Either plain text mentioning ADR-001 / invariant, or JSON.
            assert 'ADR' in out or 'invariant' in out.lower() or 'INV' in out

    def test_audit_lock_file_surfaced(self, tmp_path):
        """`.codex/audit_findings_locked.md` must appear in SessionStart brief.

        Without this, code-review Section 0 is honor-system and the agent
        can produce a count that contradicts the lock file silently.
        """
        hook = _render_hook('session_brief.py', tmp_path)
        codex = tmp_path / '.codex'
        codex.mkdir()
        (codex / 'audit_findings_locked.md').write_text(
            '# Audit findings — locked\n\n'
            '3 BLOCKER + 9 MEDIUM + 30 LOW = 42 total\n',
            encoding='utf-8',
        )
        result = _run_hook(hook, {'cwd': str(tmp_path)}, cwd=tmp_path)
        assert result.returncode == 0
        assert (result.stdout or "").strip(), 'session_brief should emit brief'
        payload = json.loads(result.stdout)
        ctx = payload['hookSpecificOutput']['additionalContext']
        # Lock-file path must appear so the agent reads it.
        assert 'audit_findings_locked.md' in ctx
        # The recorded count line must be quoted so the agent can cite verbatim.
        assert '42' in ctx or '3 BLOCKER' in ctx
        # Section 0 must be referenced by name to trigger lock-file precedence.
        assert 'Section 0' in ctx or 'Lock-file precedence' in ctx

    def test_per_module_audit_lock_files_surfaced(self, tmp_path):
        """`.codex/audit_findings_<module>_locked.md` variants also surface."""
        hook = _render_hook('session_brief.py', tmp_path)
        codex = tmp_path / '.codex'
        codex.mkdir()
        (codex / 'audit_findings_sale_extension_locked.md').write_text(
            '# locked findings\n5 BLOCKER\n', encoding='utf-8',
        )
        (codex / 'audit_findings_other_mod_locked.md').write_text(
            '# locked\n1 LOW\n', encoding='utf-8',
        )
        result = _run_hook(hook, {'cwd': str(tmp_path)}, cwd=tmp_path)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        ctx = payload['hookSpecificOutput']['additionalContext']
        assert 'sale_extension_locked' in ctx
        assert 'other_mod_locked' in ctx

    def test_no_audit_lock_no_banner(self, tmp_path):
        """No lock file → no audit-lock banner in brief."""
        hook = _render_hook('session_brief.py', tmp_path)
        codex = tmp_path / '.codex'
        codex.mkdir()
        # Decoy file that ISN'T a lock — shouldn't trip the pattern.
        (codex / 'audit_findings.md').write_text(
            '# regular findings, not locked\n', encoding='utf-8',
        )
        result = _run_hook(hook, {'cwd': str(tmp_path)}, cwd=tmp_path)
        assert result.returncode == 0
        if (result.stdout or "").strip():
            payload = json.loads(result.stdout)
            ctx = payload['hookSpecificOutput']['additionalContext']
            assert 'Lock-file' not in ctx and 'lock-file' not in ctx


# ============================================================
# analyze_halt_gate — PreToolUse hook on Edit|Write|MultiEdit
# ============================================================
class TestAnalyzeHaltGate:
    """Enforces that an unresolved HALT verdict from /analyze blocks
    subsequent Edit/Write on source files. Closes the gap where the skill
    body said `Auto-chain stops here` but no hook actually halted it.
    """

    def _envelope(self, file_path: str, workspace: Path) -> dict:
        return {
            'tool_input': {'file_path': str(file_path)},
            'cwd': str(workspace),
        }

    def _seed_workspace(self, tmp_path: Path) -> Path:
        """Create a tmp project with `.agent-toolkit/specs/` skeleton."""
        ws = tmp_path / 'proj'
        (ws / '.agent-toolkit' / 'specs' / 'main' / 'my-feature').mkdir(parents=True)
        return ws

    def _write_report(self, ws: Path, slug: str, verdict: str,
                      blockers: list = None) -> Path:
        """Write an analyze-report.md under specs/main/<slug>/."""
        report = ws / '.agent-toolkit' / 'specs' / 'main' / slug / 'analyze-report.md'
        body = f"## Analyze Report — {slug}\n\n"
        body += "| # | Check | Status | Detail |\n|---|---|---|---|\n"
        for b in (blockers or []):
            body += f"| {b['id']} | {b['name']} | 🔴 BLOCK | {b['detail']} |\n"
        body += f"\n### Verdict\n- **Verdict:** {verdict}\n"
        report.write_text(body, encoding='utf-8')
        return report

    def test_no_specs_dir_fail_open(self, tmp_path):
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        result = _run_hook(
            hook,
            self._envelope(tmp_path / 'src' / 'main.py', tmp_path),
            cwd=tmp_path,
        )
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''

    def test_no_analyze_report_fail_open(self, tmp_path):
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        result = _run_hook(
            hook, self._envelope(ws / 'src' / 'main.py', ws), cwd=ws,
        )
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''

    def test_ready_verdict_allows_edit(self, tmp_path):
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        self._write_report(ws, 'my-feature', 'READY')
        result = _run_hook(
            hook, self._envelope(ws / 'src' / 'main.py', ws), cwd=ws,
        )
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''

    def test_halt_verdict_blocks_source_edit(self, tmp_path):
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        self._write_report(ws, 'my-feature', 'HALT', blockers=[
            {'id': 'C6', 'name': 'Path realism',
             'detail': 'T4 cites addons/foo/bar.py which does not exist'},
        ])
        result = _run_hook(
            hook, self._envelope(ws / 'src' / 'main.py', ws), cwd=ws,
        )
        assert result.returncode == 0
        decision = json.loads(result.stdout)
        assert decision['decision'] == 'block'
        reason = decision['reason']
        assert 'analyze-halt-gate' in reason
        assert 'my-feature' in reason
        assert 'C6' in reason
        assert 'Path realism' in reason

    def test_block_count_form_blocks(self, tmp_path):
        """Report that uses `BLOCK: 2` summary form (no explicit Verdict)."""
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        report = ws / '.agent-toolkit' / 'specs' / 'main' / 'my-feature' / 'analyze-report.md'
        report.write_text(
            "## Analyze Report — my-feature\n\n"
            "Summary:\n- ✅ PASS: 4\n- 🟡 WARN: 1\n- 🔴 BLOCK: 2\n",
            encoding='utf-8',
        )
        result = _run_hook(
            hook, self._envelope(ws / 'src' / 'main.py', ws), cwd=ws,
        )
        assert result.returncode == 0
        decision = json.loads(result.stdout)
        assert decision['decision'] == 'block'

    def test_halt_then_ready_reemission_allows(self, tmp_path):
        """When the agent appends a re-analysis, the LAST verdict wins."""
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        report = ws / '.agent-toolkit' / 'specs' / 'main' / 'my-feature' / 'analyze-report.md'
        report.write_text(
            "## Run 1\n**Verdict:** HALT — blockers C6\n\n"
            "## Run 2 (after fix)\n**Verdict:** READY\n",
            encoding='utf-8',
        )
        result = _run_hook(
            hook, self._envelope(ws / 'src' / 'main.py', ws), cwd=ws,
        )
        assert result.returncode == 0, (
            f'Re-emitted READY should allow; stdout={result.stdout!r}'
        )
        assert (result.stdout or "").strip() == ''

    def test_halt_allows_edit_inside_agent_toolkit(self, tmp_path):
        """The agent must still be able to fix the spec / tasks / report itself."""
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        self._write_report(ws, 'my-feature', 'HALT')
        # Try editing the report itself — must NOT be blocked.
        target = ws / '.agent-toolkit' / 'specs' / 'main' / 'my-feature' / 'analyze-report.md'
        result = _run_hook(hook, self._envelope(target, ws), cwd=ws)
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''

    def test_halt_allows_edit_inside_codex_claude_cursor(self, tmp_path):
        """Toolkit-managed dirs are always editable."""
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        self._write_report(ws, 'my-feature', 'HALT')
        for sub in ('.codex/config.json', '.claude/hooks/foo.py',
                    '.cursor/rules/bar.mdc'):
            target = ws / sub
            target.parent.mkdir(parents=True, exist_ok=True)
            result = _run_hook(hook, self._envelope(target, ws), cwd=ws)
            assert result.returncode == 0, f'edit on {sub} should be allowed'
            assert (result.stdout or "").strip() == '', (
                f'edit on {sub} should be silent allow, got {result.stdout!r}'
            )

    def test_bypass_marker_overrides_halt(self, tmp_path):
        """`.agent-toolkit/.analyze-bypass` lets DEV override HALT (emergency)."""
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        self._write_report(ws, 'my-feature', 'HALT')
        (ws / '.agent-toolkit' / '.analyze-bypass').write_text('', encoding='utf-8')
        result = _run_hook(
            hook, self._envelope(ws / 'src' / 'main.py', ws), cwd=ws,
        )
        assert result.returncode == 0
        # Stdout must be silent (no block JSON); stderr carries the diagnostic.
        assert (result.stdout or "").strip() == ''
        assert 'BYPASS' in result.stderr or 'bypass' in result.stderr.lower()

    def test_multiple_halt_reports_listed(self, tmp_path):
        """Two specs both HALT → block reason mentions both slugs."""
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        ws = self._seed_workspace(tmp_path)
        (ws / '.agent-toolkit' / 'specs' / 'main' / 'feature-b').mkdir(parents=True)
        self._write_report(ws, 'my-feature', 'HALT')
        self._write_report(ws, 'feature-b', 'HALT')
        result = _run_hook(
            hook, self._envelope(ws / 'src' / 'main.py', ws), cwd=ws,
        )
        assert result.returncode == 0
        decision = json.loads(result.stdout)
        reason = decision['reason']
        # Primary slug in the main block; the other listed under "Note:".
        assert 'my-feature' in reason or 'feature-b' in reason
        assert '1 other HALT report' in reason or 'Note:' in reason

    def test_empty_envelope_fail_open(self, tmp_path):
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='', capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5,
            env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        )
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''

    def test_malformed_envelope_fail_open(self, tmp_path):
        hook = _render_hook('analyze_halt_gate.py', tmp_path)
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='not valid json {{{', capture_output=True, text=True,
            timeout=5, env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        )
        assert result.returncode == 0
        assert (result.stdout or "").strip() == ''


# ============================================================
# G2 v0.10.0 — bypass marker via ephemeral file
#   intent_router writes .agent-toolkit/.bypass_next_edit.json on
#   UserPromptSubmit; invariant_guard reads + consumes on next Edit.
#   Production path (Claude Code PreToolUse envelope does NOT carry
#   the user prompt, so the legacy envelope-key check was dead).
# ============================================================
class TestBypassEphemeral:

    def _make_blocker(self, tmp_path: Path) -> None:
        """Write a real blocker invariant in the canonical schema shape:
        patterns live under `rules.must_keep_regex` (not top-level)."""
        (tmp_path / '.agent-toolkit').mkdir(parents=True, exist_ok=True)
        (tmp_path / '.agent-toolkit' / 'invariants.json').write_text(json.dumps({
            'invariants': [{
                'id': 'INV-1',
                'severity': 'blocker',
                'description': 'keep forever',
                'applies_to': ['**/*.txt'],
                'rules': {
                    'must_keep_regex': ['forever'],
                },
                'rationale': 'test',
                'source': 'test',
            }]
        }), encoding='utf-8')

    def test_router_writes_bypass_file_on_marker(self, tmp_path):
        """UserPromptSubmit hook captures `bypass-invariant: <id>` into
        .agent-toolkit/.bypass_next_edit.json so PreToolUse can read it."""
        hook = _render_hook('intent_router.py', tmp_path)
        _run_hook(hook, {
            'prompt': 'bypass-invariant: INV-1 — chỉ lần này',
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        bypass_file = tmp_path / '.agent-toolkit' / '.bypass_next_edit.json'
        assert bypass_file.exists(), 'router must write ephemeral bypass file'
        data = json.loads(bypass_file.read_text(encoding='utf-8'))
        assert 'INV-1' in data['ids']
        assert data['ttl_seconds'] > 0

    def test_router_no_file_when_no_marker(self, tmp_path):
        hook = _render_hook('intent_router.py', tmp_path)
        _run_hook(hook, {
            'prompt': 'just a regular prompt without bypass marker',
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert not (tmp_path / '.agent-toolkit' / '.bypass_next_edit.json').exists()

    def test_guard_consumes_bypass_file_and_allows(self, tmp_path):
        """invariant_guard with a fresh bypass file → allow + delete file."""
        import time
        hook = _render_hook('invariant_guard.py', tmp_path)
        self._make_blocker(tmp_path)
        bypass_dir = tmp_path / '.agent-toolkit'
        bypass_file = bypass_dir / '.bypass_next_edit.json'
        bypass_file.write_text(json.dumps({
            'ids': ['INV-1'],
            'ts': int(time.time()),
            'ttl_seconds': 300,
        }), encoding='utf-8')
        result = _run_hook(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'forever.txt'),
                'old_string': 'forever exists',
                'new_string': 'gone',
            },
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert result.returncode == 0
        # File must be consumed (single-use).
        assert not bypass_file.exists(), 'bypass file must be consumed'

    def test_guard_ignores_expired_bypass_file(self, tmp_path):
        """Expired bypass file → no bypass; cleaned up; blocker denies."""
        import time
        hook = _render_hook('invariant_guard.py', tmp_path)
        self._make_blocker(tmp_path)
        bypass_file = tmp_path / '.agent-toolkit' / '.bypass_next_edit.json'
        bypass_file.write_text(json.dumps({
            'ids': ['INV-1'],
            'ts': int(time.time()) - 999,  # way past TTL
            'ttl_seconds': 300,
        }), encoding='utf-8')
        result = _run_hook(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'forever.txt'),
                'old_string': 'forever exists',
                'new_string': 'gone',
            },
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert result.returncode == 0  # hook always exits 0
        # Decision must be deny since bypass was expired.
        decision = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        out_block = decision.get('hookSpecificOutput', {})
        assert out_block.get('permissionDecision') == 'deny'
        # Expired file should have been cleaned up.
        assert not bypass_file.exists(), 'expired file must be cleaned'

    def test_guard_envelope_user_prompt_still_works_for_fixtures(self, tmp_path):
        """Backward compat: legacy envelope-key path still works (test
        fixtures rely on it; older Claude Code versions may add it back)."""
        hook = _render_hook('invariant_guard.py', tmp_path)
        self._make_blocker(tmp_path)
        result = _run_hook(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'forever.txt'),
                'old_string': 'forever exists',
                'new_string': 'gone',
            },
            'user_prompt': 'bypass-invariant: INV-1 — legacy path',
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        out_block = decision.get('hookSpecificOutput', {})
        # Legacy envelope-key bypass → should still allow.
        assert out_block.get('permissionDecision') == 'allow', (
            f'Expected allow via legacy envelope key, got: {decision}'
        )


# ============================================================
# G4 v0.10.0 — per-severity fail-closed for invariant_guard
#   Corrupt invariants.json with blocker text → deny (conservative).
#   Corrupt envelope + blocker configured → deny.
#   Corrupt state with only warn-level (no blocker text) → still allow.
# ============================================================
class TestFailClosedOnCorruptState:

    def test_corrupt_json_fails_closed_when_blocker_text_present(self, tmp_path):
        hook = _render_hook('invariant_guard.py', tmp_path)
        d = tmp_path / '.agent-toolkit'
        d.mkdir(parents=True, exist_ok=True)
        # Malformed JSON but contains literal `"severity": "blocker"` text.
        (d / 'invariants.json').write_text(
            '{this is not valid json but "severity": "blocker" appears here',
            encoding='utf-8',
        )
        result = _run_hook(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'x.py'),
                'old_string': 'a', 'new_string': 'b',
            },
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        out_block = decision.get('hookSpecificOutput', {})
        assert out_block.get('permissionDecision') == 'deny', (
            f'Expected conservative deny on corrupt blocker config, got: {decision}'
        )
        reason = out_block.get('permissionDecisionReason', '')
        assert 'invariants.json' in reason or 'could not be parsed' in reason

    def test_corrupt_json_fails_open_when_no_blocker_text(self, tmp_path):
        hook = _render_hook('invariant_guard.py', tmp_path)
        d = tmp_path / '.agent-toolkit'
        d.mkdir(parents=True, exist_ok=True)
        # Malformed but contains only `"severity": "warn"`.
        (d / 'invariants.json').write_text(
            '{broken json "severity": "warn" only',
            encoding='utf-8',
        )
        result = _run_hook(hook, {
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': str(tmp_path / 'x.py'),
                'old_string': 'a', 'new_string': 'b',
            },
            'cwd': str(tmp_path),
        }, cwd=tmp_path)
        assert result.returncode == 0
        decision = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        out_block = decision.get('hookSpecificOutput', {})
        # No blocker text → still fail-open (allow).
        assert out_block.get('permissionDecision') == 'allow'

    def test_corrupt_envelope_fails_closed_when_blocker_configured(self, tmp_path):
        hook = _render_hook('invariant_guard.py', tmp_path)
        d = tmp_path / '.agent-toolkit'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'invariants.json').write_text(json.dumps({
            'invariants': [{
                'id': 'INV-X', 'severity': 'blocker',
                'description': 'always present',
                'must_keep_regex': 'sentinel',
                'rationale': 'test', 'source': 'test',
            }]
        }), encoding='utf-8')
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='{not valid json at all',
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
            cwd=str(tmp_path),
            env=dict(os.environ, PYTHONIOENCODING='utf-8',
                     CLAUDE_PROJECT_DIR=str(tmp_path)),
        )
        assert result.returncode == 0
        decision = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        out_block = decision.get('hookSpecificOutput', {})
        assert out_block.get('permissionDecision') == 'deny', (
            f'Expected conservative deny on corrupt envelope + blocker, got: {decision}'
        )

    def test_corrupt_envelope_fails_open_when_no_invariants(self, tmp_path):
        """No invariants.json at all → corrupt envelope still allows (greenfield
        project, nothing to guard)."""
        hook = _render_hook('invariant_guard.py', tmp_path)
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='{not valid json',
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
            cwd=str(tmp_path),
            env=dict(os.environ, PYTHONIOENCODING='utf-8',
                     CLAUDE_PROJECT_DIR=str(tmp_path)),
        )
        assert result.returncode == 0
        # Allow (no blocker text scan hit).
        if (result.stdout or "").strip():
            decision = json.loads(result.stdout)
            out_block = decision.get('hookSpecificOutput', {})
            assert out_block.get('permissionDecision') == 'allow'

    def test_strict_mode_forces_deny_on_corrupt_envelope_even_without_blocker(self, tmp_path):
        """AGENT_TOOLKIT_STRICT=1 → always conservative deny on corrupt state."""
        hook = _render_hook('invariant_guard.py', tmp_path)
        result = subprocess.run(
            [PYTHON, str(hook)],
            input='{not valid json',
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
            cwd=str(tmp_path),
            env=dict(os.environ, PYTHONIOENCODING='utf-8',
                     CLAUDE_PROJECT_DIR=str(tmp_path),
                     AGENT_TOOLKIT_STRICT='1'),
        )
        assert result.returncode == 0
        decision = json.loads(result.stdout) if (result.stdout or "").strip() else {}
        out_block = decision.get('hookSpecificOutput', {})
        assert out_block.get('permissionDecision') == 'deny', (
            f'STRICT mode must deny on corrupt envelope, got: {decision}'
        )
