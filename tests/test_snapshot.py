"""Snapshot test (Tier 4): run `init --dry-run` for each preset into a
tmp project and assert the planned file set is stable across runs.

This catches accidental template additions/removals that aren't covered
by unit tests of individual functions.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


@pytest.mark.parametrize('preset', ['generic', 'odoo-12', 'odoo-17'])
def test_dry_run_emits_stable_file_count(tmp_path, preset):
    """Each preset's dry-run plan should produce a deterministic file count.

    If this breaks, it usually means a template was added/removed in
    `templates/` without bumping the expected count — intentional or not,
    deserves a deliberate snapshot update.
    """
    import os
    target = tmp_path / 'proj'
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    result = subprocess.run(
        [PYTHON, str(TOOLKIT_ROOT / 'setup.py'), 'init', str(target),
         '--preset', preset, '--yes', '--dry-run'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, env=env,
    )
    output = result.stdout + result.stderr
    # Plan entries in the new format: `  NEW       <relpath>` or
    # `  MODIFY    <relpath>`. Old format `  [MODE] <relpath>` is gone.
    plan_lines = [
        ln for ln in output.splitlines()
        if ln.lstrip().startswith(('NEW ', 'MODIFY ', '[TEMPLATE]', '[COPY]'))
    ]
    assert len(plan_lines) > 10, (
        f'{preset}: only {len(plan_lines)} plan items\n--- output ---\n{output}'
    )

    # Stable lower bound per preset — set just below current actual counts so
    # an accidental large removal trips the test. Bump consciously when you
    # add templates; the assert message tells you the new number.
    # Actual counts at v0.5.0: generic=107, odoo-12=149, odoo-17=149.
    # v0.29.0: generic=205, odoo-12=302, odoo-17=303 (after the +28 Odoo
    # 13-16 references below — all version refs ship to every odoo install).
    minimums = {'generic': 100, 'odoo-12': 290, 'odoo-17': 290}
    assert len(plan_lines) >= minimums[preset], (
        f'{preset}: {len(plan_lines)} files planned, '
        f'expected >= {minimums[preset]}'
    )
    # Upper bound catches accidental duplication / template fan-out bug.
    # 1.5× the current actual is loose enough for legitimate growth but
    # would catch e.g. an `os.walk` doubling the plan.
    # Bumped at v0.8.0: HOOK_CHAIN.md + DEV_LIVE_EXERCISE.md added.
    # Bumped at v0.18.0: +implement_notes.json default config + implement-noted.example.html template.
    # Bumped at v0.19.0: +gap_completeness_gate.py hook + v0.19 spec.
    # Bumped at v0.23.0: +scope_completeness_gate.py hook + scope-manifest
    # skill + scope_gate.example.json config (R9).
    # Bumped at v0.27.0: +enforce_mode.strict.example.json + 8 new Odoo
    # skills (studio/payment/account-move/mail-v2/install-scripts/l10n/
    # upgrade/owl-17-refactor) added under templates/cursor/skills/odoo/.
    # Bumped at v0.29.0: +28 Odoo 13-16 skill reference files (7 types ×
    # 4 versions) under templates/cursor/skills/odoo/*/references/ — every
    # odoo install ships all version refs (the skill picks per __manifest__).
    maximums = {'generic': 210, 'odoo-12': 340, 'odoo-17': 340}
    assert len(plan_lines) <= maximums[preset], (
        f'{preset}: {len(plan_lines)} files planned, '
        f'unexpectedly above ceiling {maximums[preset]} '
        f'— accidental duplication?'
    )


def test_resolve_preset_for_each_shipped_preset_succeeds():
    """Each shipped preset must validate cleanly under resolve_preset."""
    sys.path.insert(0, str(TOOLKIT_ROOT / 'lib'))
    from installer import resolve_preset
    presets_dir = TOOLKIT_ROOT / 'presets'
    for preset_file in presets_dir.glob('*.json'):
        # Skip per-preset canonical-decisions registry variants.
        if preset_file.stem.startswith('canonical_decisions'):
            continue
        # If this raises, the test fails and points at the broken preset.
        data = resolve_preset(preset_file.stem, presets_dir)
        assert 'description' in data
        assert 'stack' in data
