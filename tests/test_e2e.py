"""End-to-end install tests — exercise the full cmd_init → cmd_update
pipeline on a real filesystem so cross-cutting behaviour (atomic write,
backup, MEMORY.md regen, mcp config emit, gitignore append, project
config persistence) is covered as one workflow, not just helpers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
SETUP_PY = TOOLKIT_ROOT / 'setup.py'
PYTHON = sys.executable


def _run_setup(args: list, expect_exit: int = 0, timeout: int = 60):
    """Spawn setup.py with the given args; assert exit code and return result."""
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    result = subprocess.run(
        [PYTHON, str(SETUP_PY)] + args,
        capture_output=True, text=True, timeout=timeout, env=env,
    )
    if result.returncode != expect_exit:
        raise AssertionError(
            f'setup.py {args} exited {result.returncode} (expected {expect_exit})\n'
            f'--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}'
        )
    return result


# ============================================================
# Fresh install — `init`
# ============================================================
class TestFreshInstall:

    def test_init_generic_preset_produces_expected_skeleton(self, tmp_path):
        target = tmp_path / 'proj'
        _run_setup(['init', str(target), '--preset', 'generic', '--yes'])
        # Core files should exist after init.
        assert (target / 'AGENTS.md').exists()
        assert (target / 'CLAUDE.md').exists()
        assert (target / 'agent-toolkit.config.json').exists()
        assert (target / '.mcp.json').exists()
        assert (target / '.cursor' / 'mcp.json').exists()
        assert (target / '.gitignore').exists()

    def test_init_persists_config_with_schema_version(self, tmp_path):
        target = tmp_path / 'proj'
        _run_setup(['init', str(target), '--preset', 'generic', '--yes'])
        cfg = json.loads((target / 'agent-toolkit.config.json').read_text(encoding='utf-8'))
        assert cfg['preset'] == 'generic'
        assert cfg['_schema_version'] == 1
        assert cfg['_managed_by'] == 'agent-toolkit'

    def test_init_dry_run_writes_nothing(self, tmp_path):
        target = tmp_path / 'proj'
        _run_setup(['init', str(target), '--preset', 'generic', '--yes', '--dry-run'])
        # Dry-run creates the parent target dir but no agent-toolkit files inside.
        assert not (target / 'agent-toolkit.config.json').exists()
        assert not (target / 'AGENTS.md').exists()

    def test_init_mcp_json_has_servers_from_preset(self, tmp_path):
        target = tmp_path / 'proj'
        _run_setup(['init', str(target), '--preset', 'generic', '--yes'])
        mcp_payload = json.loads((target / '.mcp.json').read_text(encoding='utf-8'))
        assert 'mcpServers' in mcp_payload
        # `generic` preset ships at least the codebase MCP server.
        assert 'codebase' in mcp_payload['mcpServers']

    def test_init_gitignore_contains_secrets_path(self, tmp_path):
        target = tmp_path / 'proj'
        _run_setup(['init', str(target), '--preset', 'generic', '--yes'])
        gi = (target / '.gitignore').read_text(encoding='utf-8')
        assert '.codex/mcp.local.env' in gi
        assert '.mcp.json' in gi


# ============================================================
# Update flow — dry-run + apply + backup
# ============================================================
class TestUpdateFlow:

    def _fresh_install(self, target: Path):
        _run_setup(['init', str(target), '--preset', 'generic', '--yes'])

    def test_update_dry_run_is_default(self, tmp_path):
        target = tmp_path / 'proj'
        self._fresh_install(target)
        # Modify AGENTS.md so update sees a diff.
        agents = target / 'AGENTS.md'
        agents.write_text('LOCAL EDIT — must not be overwritten without --apply',
                          encoding='utf-8')
        result = _run_setup(['update', str(target)])
        assert 'DRY-RUN' in result.stdout
        # Local edit survives because we didn't pass --apply.
        assert 'LOCAL EDIT' in agents.read_text(encoding='utf-8')

    def test_update_apply_overwrites_and_creates_backup(self, tmp_path):
        target = tmp_path / 'proj'
        self._fresh_install(target)
        agents = target / 'AGENTS.md'
        agents.write_text('LOCAL EDIT', encoding='utf-8')
        _run_setup(['update', str(target), '--apply'])
        # AGENTS.md should be re-templated (no longer contains "LOCAL EDIT").
        assert 'LOCAL EDIT' not in agents.read_text(encoding='utf-8')
        # A backup of the local edit must exist.
        backups = list(target.glob('AGENTS.md.bak.*'))
        assert len(backups) == 1
        assert 'LOCAL EDIT' in backups[0].read_text(encoding='utf-8')

    def test_update_apply_no_backup_flag_skips_backup(self, tmp_path):
        target = tmp_path / 'proj'
        self._fresh_install(target)
        (target / 'AGENTS.md').write_text('LOCAL', encoding='utf-8')
        _run_setup(['update', str(target), '--apply', '--no-backup'])
        # No backup file created.
        backups = list(target.glob('AGENTS.md.bak.*'))
        assert backups == []

    def test_update_unchanged_files_emit_unchanged_in_dry_run(self, tmp_path):
        target = tmp_path / 'proj'
        self._fresh_install(target)
        result = _run_setup(['update', str(target)])
        # Right after install, everything is in sync → "unchanged" count > 0.
        assert 'unchanged' in result.stdout
        # No files modified (0 modified):
        assert '0 modified' in result.stdout


# ============================================================
# Cross-cutting regressions
# ============================================================
class TestCrossCuttingRegressions:

    def test_unicode_glyph_in_output_does_not_crash(self, tmp_path):
        """B2 regression — installer prints ✓ and must not crash on any
        platform's default console encoding. We force cp1252 via env var
        and assert the run completes (PYTHONIOENCODING gets us out)."""
        target = tmp_path / 'proj'
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        # The toolkit reconfigures stdout to UTF-8 at process start, so
        # PYTHONIOENCODING=cp1252 should NOT crash any more.
        env['PYTHONIOENCODING'] = 'cp1252'
        result = subprocess.run(
            [PYTHON, str(SETUP_PY), 'init', str(target),
             '--preset', 'generic', '--yes'],
            capture_output=True, text=True, timeout=60, env=env,
        )
        # Should succeed because setup.py:38-46 forces stdout to UTF-8.
        assert result.returncode == 0, (
            f'B2 regression: encoding crash returned\n'
            f'--- stderr ---\n{result.stderr}'
        )

    def test_preset_typo_fails_fast_with_did_you_mean(self, tmp_path):
        """Schema validation must catch typos at preset-load time, not
        downstream during apply. Use `odo-17` (1-char-off from `odoo-17`)
        so difflib's 0.6 cutoff finds the suggestion deterministically.
        Note: odoo-13/14/15/16/18/19/20 are now real presets, so they
        can no longer serve as typo targets."""
        target = tmp_path / 'proj'
        result = subprocess.run(
            [PYTHON, str(SETUP_PY), 'init', str(target),
             '--preset', 'odo-17', '--yes'],  # close typo (missing 'o')
            capture_output=True, text=True, timeout=30,
            env=dict(os.environ, PYTHONIOENCODING='utf-8'),
        )
        assert result.returncode != 0  # exits with error
        out = result.stdout + result.stderr
        assert 'did you mean' in out.lower(), (
            f'expected "did you mean" hint in output, got:\n{out}'
        )

    def test_version_flag_prints_semver(self):
        result = _run_setup(['--version'])
        # argparse --version prints "agent-toolkit X.Y.Z\n"
        assert 'agent-toolkit' in result.stdout
        # Version is semver-shaped.
        import re
        assert re.search(r'\d+\.\d+\.\d+', result.stdout)
