"""G7 v0.11.0 — recursion guard backup tests.

evidence_audit.py primary recursion break is `stop_hook_active=True`.
G7 adds a backup counter so the hook bails out after N blocks within
a rolling window even if that envelope field disappears.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / 'templates' / 'claude' / 'hooks'
PYTHON = sys.executable


def _render_evidence_audit(tmp_path: Path) -> Path:
    """Copy evidence_audit.py + its _audit/ package + _common.py into tmp."""
    import shutil
    src = HOOKS_DIR / 'evidence_audit.py'
    dst = tmp_path / 'evidence_audit.py'
    dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    for companion in ('_common.py', '_patterns.py'):
        comp_src = HOOKS_DIR / companion
        if comp_src.exists():
            (tmp_path / companion).write_text(
                comp_src.read_text(encoding='utf-8'), encoding='utf-8'
            )
    audit_src = HOOKS_DIR / '_audit'
    if audit_src.is_dir():
        audit_dst = tmp_path / '_audit'
        if audit_dst.exists():
            shutil.rmtree(audit_dst)
        shutil.copytree(audit_src, audit_dst)
    return dst


def _build_block_envelope(tmp_path: Path) -> dict:
    """Envelope that should trigger a block (unbacked claim)."""
    # Write a transcript with a claim but no tool calls.
    transcript = tmp_path / 'transcript.jsonl'
    msgs = [
        {'role': 'user', 'content': 'do something'},
        {'role': 'assistant', 'content': (
            'X' * 300 + ' Root cause is foo. Y is missing.'
        )},
    ]
    with transcript.open('w', encoding='utf-8') as fh:
        for m in msgs:
            fh.write(json.dumps(m) + '\n')
    return {
        'transcript_path': str(transcript),
        'cwd': str(tmp_path),
        'stop_hook_active': False,
    }


def _run_audit(hook: Path, envelope: dict, cwd: Path):
    return subprocess.run(
        [PYTHON, str(hook)],
        input=json.dumps(envelope),
        capture_output=True, text=True, timeout=10,
        cwd=str(cwd),
        env=dict(os.environ, PYTHONIOENCODING='utf-8'),
    )


class TestRecursionGuard:

    def test_first_block_emits_block_decision(self, tmp_path):
        """First block within window → emits standard block decision."""
        hook = _render_evidence_audit(tmp_path)
        envelope = _build_block_envelope(tmp_path)
        result = _run_audit(hook, envelope, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if result.stdout.strip() else {}
        # Standard block envelope shape from evidence_audit.
        assert out.get('decision') == 'block'

    def test_counter_state_file_written_on_block(self, tmp_path):
        """Block writes `.stop_audit_count.json` with count=1."""
        hook = _render_evidence_audit(tmp_path)
        envelope = _build_block_envelope(tmp_path)
        _run_audit(hook, envelope, tmp_path)
        state_path = tmp_path / '.agent-toolkit' / '.stop_audit_count.json'
        assert state_path.exists(), 'recursion state file must be written'
        data = json.loads(state_path.read_text(encoding='utf-8'))
        assert data['count'] == 1
        assert data['first_ts'] > 0

    def test_hard_cap_breaks_loop_after_threshold(self, tmp_path):
        """After 4 consecutive blocks (cap=3), 4th call must ALLOW with
        additionalContext warning instead of emitting block."""
        hook = _render_evidence_audit(tmp_path)
        envelope = _build_block_envelope(tmp_path)
        # Trigger 3 blocks (within cap).
        for i in range(3):
            result = _run_audit(hook, envelope, tmp_path)
            assert result.returncode == 0
        # 4th call should bail out (count > 3).
        result = _run_audit(hook, envelope, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if result.stdout.strip() else {}
        # Bail-out path emits hookSpecificOutput (not block decision).
        assert 'hookSpecificOutput' in out, (
            f'Expected hookSpecificOutput on bail-out, got: {out}'
        )
        ctx = out['hookSpecificOutput'].get('additionalContext', '')
        assert 'recursion hard-cap' in ctx or 'recursion_cap' in ctx
        # State file must be cleared after bail-out.
        state_path = tmp_path / '.agent-toolkit' / '.stop_audit_count.json'
        assert not state_path.exists(), (
            'state file must be cleared after hard-cap bail-out'
        )

    def test_allow_path_clears_counter(self, tmp_path):
        """If a block then an allow happens, the counter must clear so
        a future block-burst starts fresh."""
        hook = _render_evidence_audit(tmp_path)
        # First: block envelope.
        block_env = _build_block_envelope(tmp_path)
        _run_audit(hook, block_env, tmp_path)
        state_path = tmp_path / '.agent-toolkit' / '.stop_audit_count.json'
        assert state_path.exists()
        # Then: short response (skipped by audit → allow path).
        short_transcript = tmp_path / 'short.jsonl'
        short_transcript.write_text(json.dumps({
            'role': 'assistant', 'content': 'ok done'
        }) + '\n', encoding='utf-8')
        allow_env = {
            'transcript_path': str(short_transcript),
            'cwd': str(tmp_path),
            'stop_hook_active': False,
        }
        _run_audit(hook, allow_env, tmp_path)
        assert not state_path.exists(), (
            'allow path must clear the recursion state file'
        )

    def test_expired_window_resets_counter(self, tmp_path):
        """If first block was > 60s ago, next block starts fresh."""
        hook = _render_evidence_audit(tmp_path)
        # Manually plant a stale state file.
        state_dir = tmp_path / '.agent-toolkit'
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / '.stop_audit_count.json'
        state_path.write_text(json.dumps({
            'count': 5,
            'first_ts': int(time.time()) - 3600,  # 1h ago
            'last_ts': int(time.time()) - 3600,
        }), encoding='utf-8')
        # New block within fresh window → should reset to count=1, NOT
        # trigger hard-cap (count=5+1=6 would otherwise bail out).
        envelope = _build_block_envelope(tmp_path)
        result = _run_audit(hook, envelope, tmp_path)
        assert result.returncode == 0
        out = json.loads(result.stdout) if result.stdout.strip() else {}
        assert out.get('decision') == 'block', (
            f'expired window must reset; expected standard block, got: {out}'
        )
        # State file now has fresh count=1 (window was reset).
        data = json.loads(state_path.read_text(encoding='utf-8'))
        assert data['count'] == 1
