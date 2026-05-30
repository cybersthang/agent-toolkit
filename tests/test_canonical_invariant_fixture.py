"""G9 v0.11.0 — tests for the canonical `make_invariant()` fixture.

The fixture exists to prevent the schema drift discovered during
v0.10.0 G2 work: `test_bypass_token_in_prompt_overrides` had been
"passing" for multiple versions while never exercising the bypass
path, because its raw-dict fixture put `must_keep_regex` at the wrong
nesting level → no violation → no bypass check → test misleading.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from _invariant_fixtures import make_invariant, write_invariants


class TestMakeInvariant:

    def test_canonical_shape_has_rules_block(self):
        inv = make_invariant('INV-1', must_keep_regex='@api\\.depends')
        # Production hook reads inv['rules']['must_keep_regex']; not
        # inv['must_keep_regex']. The shape must place patterns inside rules.
        assert 'rules' in inv
        assert inv['rules']['must_keep_regex'] == ['@api\\.depends']
        assert 'must_keep_regex' not in inv  # never at top level

    def test_must_keep_call_normalised_to_list(self):
        inv = make_invariant('INV-2', must_keep_call='foo')
        assert inv['rules']['must_keep_call'] == ['foo']

    def test_must_keep_regex_list_preserved(self):
        inv = make_invariant('INV-3', must_keep_regex=['a', 'b'])
        assert inv['rules']['must_keep_regex'] == ['a', 'b']

    def test_rejects_invariant_with_no_pattern(self):
        # Empty rules block means hook has nothing to enforce → reject at
        # build time, not silently at runtime.
        with pytest.raises(ValueError, match='at least one'):
            make_invariant('INV-X')

    def test_rejects_invalid_severity(self):
        with pytest.raises(ValueError, match='severity'):
            make_invariant('INV-Y', severity='critical', must_keep_regex='x')

    def test_required_keys_present(self):
        inv = make_invariant('INV-Z', must_keep_regex='x')
        for key in ('id', 'severity', 'description', 'rules', 'rationale', 'source'):
            assert key in inv, f'missing required key: {key}'

    def test_applies_to_optional(self):
        inv = make_invariant('INV-A', must_keep_regex='x')
        assert inv['applies_to'] == []

        inv2 = make_invariant('INV-B', must_keep_regex='x',
                              applies_to=['**/*.py'])
        assert inv2['applies_to'] == ['**/*.py']


class TestWriteInvariants:

    def test_writes_canonical_json_structure(self, tmp_path: Path):
        inv1 = make_invariant('INV-1', must_keep_regex='@api\\.depends')
        inv2 = make_invariant('INV-2', must_keep_call='dispatch')
        path = write_invariants(tmp_path, inv1, inv2)
        assert path == tmp_path / '.agent-toolkit' / 'invariants.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        # Top-level key must be `invariants` (what production hook reads).
        assert 'invariants' in data
        assert len(data['invariants']) == 2
        # Round-trip: re-parse one invariant, confirm rules nested correctly.
        first = data['invariants'][0]
        assert first['rules']['must_keep_regex'] == ['@api\\.depends']

    def test_blocker_text_scan_matches_canonical_output(self, tmp_path: Path):
        """Sanity check: a blocker invariant written via this fixture
        contains the exact text pattern that `_has_blocker_text_scan`
        (G4) regexes for. Inline regex avoids importing invariant_guard
        at pytest import-time (which would trigger wrap_utf8_stdio and
        conflict with pytest's stdio capture)."""
        import re
        SCAN_RE = re.compile(
            r'["\']severity["\']\s*:\s*["\']blocker["\']',
            re.IGNORECASE,
        )
        write_invariants(tmp_path, make_invariant('INV-1',
                                                  must_keep_regex='@api',
                                                  severity='blocker'))
        text = (tmp_path / '.agent-toolkit' / 'invariants.json').read_text(
            encoding='utf-8')
        assert SCAN_RE.search(text), (
            'canonical blocker invariant must contain literal "severity": "blocker"'
        )

        write_invariants(tmp_path, make_invariant('INV-2',
                                                  must_keep_regex='@api',
                                                  severity='warn'))
        text2 = (tmp_path / '.agent-toolkit' / 'invariants.json').read_text(
            encoding='utf-8')
        assert not SCAN_RE.search(text2), (
            'warn-only invariant must NOT trigger blocker text scan'
        )
