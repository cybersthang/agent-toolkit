"""Unit tests for `templates/codex/lint_verify_report.py`.

Two enforcement layers covered:
1. `acceptance_evals` coverage — every id in spec frontmatter must be cited
   in the report (exit 1 on miss).
2. **Real-Data Proof section** — when spec frontmatter has
   `feature_kind: classification`, the report MUST include a
   `## Real-Data Proof` section header (exit 4 on miss). This closes the
   M1 medium gap where Step 1.8 of verify-feature/SKILL.md was honor-system
   only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
LINT_SCRIPT = TOOLKIT_ROOT / 'templates' / 'codex' / 'lint_verify_report.py'
PYTHON = sys.executable


def _seed_spec(workspace: Path, slug: str, evals: list = None,
               feature_kind: str = None) -> Path:
    """Write a minimal spec.md under workspace/.agent-toolkit/specs/main/<slug>/."""
    spec_dir = workspace / '.agent-toolkit' / 'specs' / 'main' / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / f'{slug}.md'
    lines = ['---', f'name: {slug}']
    if feature_kind:
        lines.append(f'feature_kind: {feature_kind}')
    if evals:
        lines.append('acceptance_evals:')
        for e in evals:
            lines.append(f'  - id: {e}')
            lines.append('    story: "<auto>"')
            lines.append('    grader: data')
            lines.append('    layer: raw_db')
            lines.append('    expected:')
            lines.append('      assertion: "PASS"')
    lines += ['---', '', '# Spec body']
    spec_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return spec_path


def _run_lint(workspace: Path, slug: str, report_text: str):
    """Spawn lint_verify_report.py, pipe report on stdin (UTF-8 bytes).

    Pipe as bytes — Windows default cp1252 encoder mangles `✅` / Vietnamese
    when subprocess uses text=True. We force-encode here and decode the
    captured output back as UTF-8 to keep the test cross-platform.
    """
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    proc = subprocess.run(
        [PYTHON, str(LINT_SCRIPT), slug, '--workspace', str(workspace)],
        input=report_text.encode('utf-8'),
        capture_output=True, timeout=10, env=env,
    )
    # Re-wrap stdout/stderr as UTF-8 strings on the result object so
    # existing assertions (`result.stderr`, `result.stdout`) keep working.
    return type('Result', (), {
        'returncode': proc.returncode,
        'stdout': proc.stdout.decode('utf-8', errors='replace'),
        'stderr': proc.stderr.decode('utf-8', errors='replace'),
    })()


# ============================================================
# Existing enforcement: eval coverage (regression-protect)
# ============================================================
class TestEvalCoverage:

    def test_no_evals_returns_exit_3(self, tmp_path):
        _seed_spec(tmp_path, 'nofeat')
        result = _run_lint(tmp_path, 'nofeat', report_text='## Verify Report\nNothing.')
        assert result.returncode == 3
        assert 'lint skipped' in result.stderr.lower()

    def test_all_evals_covered_passes(self, tmp_path):
        _seed_spec(tmp_path, 'feat-a', evals=['us1-flag', 'us2-count'])
        report = (
            '## Verify Report — feat-a\n'
            '| eval | result |\n'
            '| us1-flag | ✅ PASS |\n'
            '| us2-count | ✅ PASS |\n'
        )
        result = _run_lint(tmp_path, 'feat-a', report_text=report)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert 'PASS' in result.stdout

    def test_missing_eval_returns_exit_1(self, tmp_path):
        _seed_spec(tmp_path, 'feat-b', evals=['us1-flag', 'us2-count'])
        report = (
            '## Verify Report — feat-b\n'
            '| eval | result |\n'
            '| us1-flag | ✅ PASS |\n'
            # us2-count missing
        )
        result = _run_lint(tmp_path, 'feat-b', report_text=report)
        assert result.returncode == 1
        assert 'us2-count' in result.stderr
        assert 'MISSING' in result.stderr

    def test_missing_spec_returns_exit_2(self, tmp_path):
        # No spec created — should hit the spec-not-found path.
        result = _run_lint(tmp_path, 'ghost-slug', report_text='## report\n')
        assert result.returncode == 2
        assert 'spec not found' in result.stderr.lower()


# ============================================================
# NEW: Real-Data Proof enforcement for feature_kind: classification
# ============================================================
class TestRealDataProofEnforcement:
    """Spec with `feature_kind: classification` → report MUST include
    `## Real-Data Proof` section. Exit 4 on miss.
    """

    def test_classifier_spec_without_section_returns_exit_4(self, tmp_path):
        _seed_spec(tmp_path, 'cls-feat', evals=['us1-tag'],
                   feature_kind='classification')
        # Report covers the eval but does NOT include a Real-Data Proof section.
        report = (
            '## Verify Report — cls-feat\n'
            '| eval | result |\n'
            '| us1-tag | ✅ PASS |\n'
        )
        result = _run_lint(tmp_path, 'cls-feat', report_text=report)
        assert result.returncode == 4, (
            f'Expected exit 4 for missing Real-Data Proof, '
            f'got {result.returncode}\nstderr: {result.stderr}'
        )
        assert 'Real-Data Proof' in result.stderr
        assert 'classification' in result.stderr
        # Fix hint must mention the worked example for the agent to follow.
        assert 'real-data-proof' in result.stderr.lower() or \
               'Step 4' in result.stderr

    def test_classifier_spec_with_canonical_heading_passes(self, tmp_path):
        _seed_spec(tmp_path, 'cls-ok', evals=['us1-tag'],
                   feature_kind='classification')
        report = (
            '## Verify Report — cls-ok\n'
            '| eval | result |\n'
            '| us1-tag | ✅ PASS |\n'
            '\n## Real-Data Proof — cls-ok\n'
            'Data source: real DB · rows: 100\n'
            'Distribution: BLOCK=40, ASYNC=60\n'
            'Falsification: ...\n'
        )
        result = _run_lint(tmp_path, 'cls-ok', report_text=report)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert 'Real-Data Proof section present' in result.stdout

    @pytest.mark.parametrize('heading', [
        '## Real-Data Proof Report',
        '### Real Data Proof',      # space variant
        '## REAL-DATA PROOF',       # case-insensitive
        '**Real-Data Proof Report**',  # bold form (no heading)
        '#### real-data proof',     # lowercase + h4
    ])
    def test_classifier_spec_accepts_tolerant_heading_variants(self, tmp_path, heading):
        slug = f'cls-{abs(hash(heading)) % 9999}'
        _seed_spec(tmp_path, slug, evals=['us1-tag'],
                   feature_kind='classification')
        report = (
            f'## Verify Report — {slug}\n'
            f'| us1-tag | ✅ PASS |\n'
            f'\n{heading}\n'
            f'Data source: ...\n'
        )
        result = _run_lint(tmp_path, slug, report_text=report)
        assert result.returncode == 0, (
            f'heading variant {heading!r} should be accepted; '
            f'got exit {result.returncode}\nstderr: {result.stderr}'
        )

    def test_non_classifier_spec_does_not_require_section(self, tmp_path):
        """Specs without `feature_kind: classification` should NOT require
        Real-Data Proof — the enforcement is targeted, not universal."""
        _seed_spec(tmp_path, 'regular-feat', evals=['us1-flag'])
        # No feature_kind set; no Real-Data Proof section — should still PASS.
        report = (
            '## Verify Report — regular-feat\n'
            '| us1-flag | ✅ PASS |\n'
        )
        result = _run_lint(tmp_path, 'regular-feat', report_text=report)
        assert result.returncode == 0, (result.stdout, result.stderr)

    def test_classifier_spec_with_other_feature_kind_skips(self, tmp_path):
        """`feature_kind: behavioral` or other values should not trigger the
        check — only `classification` does."""
        _seed_spec(tmp_path, 'beh-feat', evals=['us1-flag'],
                   feature_kind='behavioral')
        report = '## Verify Report\n| us1-flag | ✅ PASS |\n'
        result = _run_lint(tmp_path, 'beh-feat', report_text=report)
        assert result.returncode == 0

    def test_classifier_spec_missing_eval_takes_priority_over_real_data_proof(self, tmp_path):
        """When BOTH issues present, eval-coverage error (exit 1) wins over
        Real-Data Proof error (exit 4) — agent fixes one issue per re-emit."""
        _seed_spec(tmp_path, 'cls-both', evals=['us1-tag', 'us2-tag'],
                   feature_kind='classification')
        report = (
            '## Verify Report\n'
            '| us1-tag | ✅ PASS |\n'
            # us2-tag missing; no Real-Data Proof either
        )
        result = _run_lint(tmp_path, 'cls-both', report_text=report)
        # Either order is acceptable in principle, but the script as written
        # checks eval coverage FIRST → expect exit 1.
        assert result.returncode == 1, (
            f'Eval-coverage check should fire before Real-Data Proof check; '
            f'got exit {result.returncode}'
        )
