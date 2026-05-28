"""Tests for `lib/installer.py:merge_invariants` + `merge_invariants_file`.

NEW-2 — `setup.py update --merge-invariants` flag implementation.

Cases covered:
  1. Project file absent (or empty `invariants` list) → all template
     invariants merged.
  2. Project has 2 invariants, one ID overlaps a template entry → only
     non-overlapping template ids are added; project entry untouched.
  3. Project already has all template ids (no-op: 0 added, all skipped).

Each case also exercises the file-level wrapper to confirm atomic write
materializes the merged dict on disk with correct shape (metadata fields
preserved, `invariants` list deduped).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from installer import merge_invariants, merge_invariants_file, load_preset_overlay


# --------------------------------------------------------- fixtures ---
def _tmpl_payload() -> dict:
    """A 5-invariant template payload mirroring v0.22+ shipped defaults.

    IDs intentionally match the production template stems so the test
    documents real behavior; values are stripped-down to keep the test
    self-contained (we exercise merge logic, not invariant semantics).
    """
    return {
        '_doc': 'template doc',
        '_schema': {'id': 'kebab-case unique slug'},
        '_workflow': ['1. Step one', '2. Step two'],
        'version': 2,
        'invariants': [
            {'id': 'no-bare-python-shebang', 'severity': 'warn'},
            {'id': 'credentials-via-mcp-local-env', 'severity': 'warn'},
            {'id': 'odoo-multi-company-with-company-on-create',
             'severity': 'warn'},
            {'id': 'odoo-tests-need-test-base-class', 'severity': 'warn'},
            {'id': 'odoo-sudo-must-have-comment', 'severity': 'warn'},
        ],
    }


@pytest.fixture
def template_payload() -> dict:
    return _tmpl_payload()


@pytest.fixture
def template_file(tmp_path: Path) -> Path:
    p = tmp_path / 'tmpl_invariants.json'
    p.write_text(json.dumps(_tmpl_payload()), encoding='utf-8')
    return p


# --------------------------------------------------------- pure-merge ---
def test_merge_invariants_empty_project_adds_all(template_payload):
    """Case 1: project empty → all 5 template invariants merged."""
    project = {
        '_doc': 'project-curated doc',  # project metadata preserved
        '_schema': {'id': 'project schema'},
        '_workflow': ['project step'],
        'version': 2,
        'invariants': [],
    }
    merged, added, skipped = merge_invariants(project, template_payload)

    assert len(added) == 5
    assert skipped == []
    assert {inv['id'] for inv in merged['invariants']} == {
        'no-bare-python-shebang',
        'credentials-via-mcp-local-env',
        'odoo-multi-company-with-company-on-create',
        'odoo-tests-need-test-base-class',
        'odoo-sudo-must-have-comment',
    }
    # Project metadata must survive — template fields do NOT overwrite.
    assert merged['_doc'] == 'project-curated doc'
    assert merged['_schema'] == {'id': 'project schema'}
    assert merged['_workflow'] == ['project step']
    assert merged['version'] == 2


def test_merge_invariants_partial_overlap_skips_existing_id(template_payload):
    """Case 2: project has 2 entries (one overlapping) → +4 added, 1 skip.

    Project owns `no-bare-python-shebang` with severity=blocker (a
    customization). After merge, the project entry must remain at
    severity=blocker (NOT silently downgraded to template's `warn`),
    and the 4 non-overlapping template ids must be appended.
    """
    project_custom = {
        'id': 'no-bare-python-shebang',
        'severity': 'blocker',   # project promoted to blocker
        'rationale': 'project-specific reason',
    }
    project_only = {
        'id': 'project-private-rule',
        'severity': 'warn',
    }
    project = {
        '_doc': 'project doc',
        'version': 2,
        'invariants': [project_custom, project_only],
    }
    merged, added, skipped = merge_invariants(project, template_payload)

    assert sorted(added) == sorted([
        'credentials-via-mcp-local-env',
        'odoo-multi-company-with-company-on-create',
        'odoo-tests-need-test-base-class',
        'odoo-sudo-must-have-comment',
    ])
    assert skipped == ['no-bare-python-shebang']

    # Project's blocker promotion + private rule both preserved.
    by_id = {inv['id']: inv for inv in merged['invariants']}
    assert by_id['no-bare-python-shebang']['severity'] == 'blocker'
    assert (by_id['no-bare-python-shebang']['rationale']
            == 'project-specific reason')
    assert by_id['project-private-rule']['severity'] == 'warn'
    # All 4 template-new entries are appended.
    assert 'credentials-via-mcp-local-env' in by_id
    # Order: existing entries first, then template-new (stable append).
    ids_in_order = [inv['id'] for inv in merged['invariants']]
    assert ids_in_order[:2] == ['no-bare-python-shebang',
                                'project-private-rule']


def test_merge_invariants_idempotent_when_all_ids_present(template_payload):
    """Case 3: project already has all 5 template ids → 0 added, no-op.

    Confirms the flag is safe to re-run repeatedly — running it a second
    time after a previous merge has zero effect on the project file.
    """
    project = {
        '_doc': 'project doc',
        'version': 2,
        'invariants': [{'id': inv['id'], 'severity': 'blocker'}
                       for inv in template_payload['invariants']],
    }
    merged, added, skipped = merge_invariants(project, template_payload)

    assert added == []
    assert len(skipped) == 5
    # Project state untouched — still 5 entries, all still `blocker`.
    assert len(merged['invariants']) == 5
    assert all(inv['severity'] == 'blocker' for inv in merged['invariants'])


# --------------------------------------------------------- file-level ---
def test_merge_invariants_file_seeds_when_project_missing(
    tmp_path: Path, template_file: Path
):
    """File wrapper: project file doesn't exist → template copied verbatim.

    Edge case: a user wiping `.agent-toolkit/invariants.json` then running
    `--merge-invariants` should re-seed from the template (instead of
    erroring out or writing an empty stub).
    """
    project_path = tmp_path / 'missing' / 'invariants.json'
    assert not project_path.exists()

    added, skipped = merge_invariants_file(project_path, template_file)

    assert len(added) == 5
    assert skipped == []
    assert project_path.exists()
    data = json.loads(project_path.read_text(encoding='utf-8'))
    assert len(data['invariants']) == 5
    # Template metadata seeded onto a previously-missing file.
    assert data['_doc'] == 'template doc'
    assert data['version'] == 2


def test_merge_invariants_file_atomic_write(
    tmp_path: Path, template_file: Path
):
    """File wrapper: merging an existing file produces a valid JSON output.

    Sanity check that atomic write + indent=2 + trailing newline survive
    round-trip parsing — guards against silent corruption.
    """
    project_path = tmp_path / 'invariants.json'
    project_path.write_text(json.dumps({
        '_doc': 'project doc',
        'version': 2,
        'invariants': [{'id': 'no-bare-python-shebang', 'severity': 'blocker'}],
    }), encoding='utf-8')

    added, skipped = merge_invariants_file(project_path, template_file)

    assert len(added) == 4
    assert skipped == ['no-bare-python-shebang']

    raw = project_path.read_text(encoding='utf-8')
    assert raw.endswith('\n')
    data = json.loads(raw)
    assert len(data['invariants']) == 5
    by_id = {inv['id']: inv for inv in data['invariants']}
    # Project's blocker promotion preserved on disk.
    assert by_id['no-bare-python-shebang']['severity'] == 'blocker'


# --------------------------------------------------- R4 overlay merge ---
# v0.23 R4-consumer
def _overlay_payload() -> list:
    """Two preset-overlay invariants: one NEW id + one that collides with a
    template default id (so we can prove project/template wins over overlay)."""
    return [
        {
            'id': 'odoo13-no-api-one',  # genuinely new
            'description': 'Odoo 13 removed @api.one.',
            'applies_to': ['**/models/**/*.py'],
            'rules': {'must_keep_regex': ['ensure_one']},
            'severity': 'warn',
        },
        {
            'id': 'no-bare-python-shebang',  # collides with template default
            'description': 'overlay attempt to redefine a template id',
            'applies_to': ['scripts/**/*.py'],
            'rules': {'must_keep_regex': ['sys.executable']},
            'severity': 'blocker',  # overlay tries blocker; must be IGNORED
        },
    ]


def test_merge_invariants_file_with_preset_overlay(
    tmp_path: Path, template_file: Path
):
    """R4: project + template + preset overlay merge → all three folded,
    dedup correct, project/template win over overlay on id collision.

    Project owns `no-bare-python-shebang` (severity=blocker custom). Template
    ships 5 defaults. Overlay ships 1 NEW id + 1 colliding id. Expected:
      - project entry stays (its blocker, not overlay's),
      - 4 non-overlapping template ids added,
      - 1 new overlay id (`odoo13-no-api-one`) added,
      - overlay's colliding id skipped (project already owns it).
    """
    project_path = tmp_path / 'invariants.json'
    project_path.write_text(json.dumps({
        '_doc': 'project doc',
        'version': 2,
        'invariants': [
            {'id': 'no-bare-python-shebang', 'severity': 'blocker',
             'rationale': 'project owns this'},
        ],
    }), encoding='utf-8')

    added, skipped = merge_invariants_file(
        project_path, template_file,
        overlay_invariants=_overlay_payload(),
    )

    # 4 template-new + 1 overlay-new = 5 added.
    assert 'odoo13-no-api-one' in added
    assert len(added) == 5
    # Template's own no-bare-python-shebang skipped (project owns it) AND the
    # overlay's colliding entry skipped → 2 skips of the same id.
    assert skipped.count('no-bare-python-shebang') == 2

    data = json.loads(project_path.read_text(encoding='utf-8'))
    by_id = {inv['id']: inv for inv in data['invariants']}
    # 5 template ids + 1 new overlay id = 6 unique entries.
    assert len(data['invariants']) == 6
    assert 'odoo13-no-api-one' in by_id
    # Project's custom entry wins — overlay's blocker redefinition is ignored;
    # the project's own (also-blocker, but with its rationale) survives intact.
    assert by_id['no-bare-python-shebang']['rationale'] == 'project owns this'
    # The new overlay invariant landed verbatim.
    assert by_id['odoo13-no-api-one']['severity'] == 'warn'


def test_merge_invariants_file_empty_overlay_is_template_only(
    tmp_path: Path, template_file: Path
):
    """Edge: overlay=None / [] → behaves exactly like the template-only path
    (backward compatible)."""
    project_path = tmp_path / 'invariants.json'
    added_none, skipped_none = merge_invariants_file(
        project_path, template_file, overlay_invariants=None)
    assert len(added_none) == 5
    assert skipped_none == []

    project_path2 = tmp_path / 'invariants2.json'
    added_empty, skipped_empty = merge_invariants_file(
        project_path2, template_file, overlay_invariants=[])
    assert len(added_empty) == 5
    assert skipped_empty == []


def test_load_preset_overlay_from_shipped_preset():
    """R4: `load_preset_overlay` resolves a real shipped preset and returns
    its `invariants_overlay` array.

    odoo-13 ships exactly one overlay entry (`odoo13-no-api-one`). odoo-12
    (the base) ships none → empty list.
    """
    presets_dir = Path(__file__).resolve().parent.parent / 'presets'

    o13 = load_preset_overlay('odoo-13', presets_dir)
    assert isinstance(o13, list)
    ids = {e['id'] for e in o13}
    assert 'odoo13-no-api-one' in ids

    o12 = load_preset_overlay('odoo-12', presets_dir)
    assert o12 == []
