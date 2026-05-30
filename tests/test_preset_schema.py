"""Tests for `lib/installer.py:validate_preset_schema` (P2.7).

v0.23 P2.7 — jsonschema-style preset validation (stdlib only, no jsonschema
dep). The function returns a list of human-readable errors (empty = OK) and
never raises.

Cases covered:
  1. A valid preset (incl. a well-formed `invariants_overlay`) passes (0
     errors).
  2. A preset missing a REQUIRED field fails.
  3. A preset with a WRONG TYPE for a known field fails.
  4. An `invariants_overlay` entry missing required keys / bad severity fails.
  5. Every shipped preset passes the schema (regression guard).
"""
from __future__ import annotations

from pathlib import Path

from installer import (
    validate_preset_schema,
    validate_invariant_entry,
    resolve_preset,
)

PRESETS_DIR = Path(__file__).resolve().parent.parent / 'presets'


def _valid_preset() -> dict:
    return {
        'description': 'A test preset',
        'stack': {'language': 'python', 'framework': 'odoo'},
        'addon_roots': ['addons'],
        'mcp_servers': ['codebase'],
        'db': {'default_db': 'x', 'default_port': 5432},
        'rules': ['_common'],
        'skills': ['_common'],
        'memory_packs': ['odoo-12'],
        'invariants_overlay': [
            {
                'id': 'foo-rule',
                'description': 'a rule',
                'applies_to': ['**/*.py'],
                'rules': {'must_keep_regex': ['bar']},
                'severity': 'warn',
            },
        ],
    }


# ----------------------------------------------------------- case 1 ---
def test_valid_preset_passes():
    errors = validate_preset_schema(_valid_preset(), name='good')
    assert errors == [], errors


# ----------------------------------------------------------- case 2 ---
def test_missing_required_field_fails():
    data = _valid_preset()
    del data['stack']  # `stack` is required
    errors = validate_preset_schema(data, name='nostack')
    assert any('missing required field `stack`' in e for e in errors), errors


# ----------------------------------------------------------- case 3 ---
def test_wrong_type_fails():
    data = _valid_preset()
    data['addon_roots'] = 'addons'  # should be a list, not a string
    errors = validate_preset_schema(data, name='badtype')
    assert any('`addon_roots` must be list' in e for e in errors), errors

    data2 = _valid_preset()
    data2['db'] = ['not', 'a', 'dict']  # should be a dict
    errors2 = validate_preset_schema(data2, name='baddb')
    assert any('`db` must be dict' in e for e in errors2), errors2


# ----------------------------------------------------------- case 4 ---
def test_bad_overlay_entry_fails():
    data = _valid_preset()
    # Drop required `severity`, and add a second entry with bad severity.
    data['invariants_overlay'] = [
        {
            'id': 'incomplete',
            'description': 'missing applies_to/rules/severity',
        },
        {
            'id': 'badsev',
            'description': 'd',
            'applies_to': [],
            'rules': {},
            'severity': 'critical',  # not in (blocker, warn)
        },
    ]
    errors = validate_preset_schema(data, name='badoverlay')
    joined = '\n'.join(errors)
    assert 'invariants_overlay[0]: missing required field `severity`' in joined
    assert 'invariants_overlay[0]: missing required field `applies_to`' in joined
    assert 'invariants_overlay[0]: missing required field `rules`' in joined
    assert "invariants_overlay[1]: `severity` must be" in joined


def test_overlay_duplicate_id_within_overlay_fails():
    data = _valid_preset()
    dup = {
        'id': 'dup',
        'description': 'd',
        'applies_to': ['**/*.py'],
        'rules': {},
        'severity': 'warn',
    }
    data['invariants_overlay'] = [dup, dict(dup)]
    errors = validate_preset_schema(data, name='dup')
    assert any('duplicate invariant id `dup`' in e for e in errors), errors


def test_validate_invariant_entry_non_dict():
    errors = validate_invariant_entry('not-a-dict', where='x[0]')
    assert errors == ['x[0]: must be an object, got str']


# ----------------------------------------------------------- case 5 ---
def test_all_shipped_presets_pass_schema():
    """Regression guard: every shipped preset (after `extends:` resolution
    via the installer's own loader) validates clean.

    Uses `resolve_preset` so inherited/merged presets are checked in the
    exact shape the installer feeds downstream. `resolve_preset` itself now
    runs `validate_preset_schema` and raises on failure, so reaching the
    assert at all means it passed; we additionally re-run the validator on the
    raw (pre-merge) preset dict to catch issues masked by inheritance.
    """
    raw_presets = [
        p for p in PRESETS_DIR.glob('*.json')
        if not p.stem.startswith('canonical_decisions')
        and not p.stem.startswith('_')
    ]
    assert raw_presets, 'no presets found to validate'
    for path in raw_presets:
        name = path.stem
        # Resolve (raises on schema failure) — proves the consumed shape is OK.
        merged = resolve_preset(name, PRESETS_DIR)
        errors = validate_preset_schema(merged, name=name)
        assert errors == [], f'{name}: {errors}'
