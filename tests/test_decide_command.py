"""G5 v0.11.0 — verify /decide slash command file ships with valid
frontmatter + references both ADR and invariant atomically.

The actual command is executed by Claude Code at runtime, not by pytest.
This test only catches "we forgot to ship the file" or "frontmatter
broken" regressions.
"""
from __future__ import annotations

import re
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DECIDE_MD = TOOLKIT_ROOT / 'templates' / 'claude' / 'commands' / 'decide.md'


class TestDecideCommand:

    def test_file_exists(self):
        assert DECIDE_MD.exists(), 'decide.md slash command must ship'

    def test_frontmatter_valid(self):
        text = DECIDE_MD.read_text(encoding='utf-8')
        # Must open with ---\n...---\n YAML frontmatter.
        assert text.startswith('---\n'), 'frontmatter must lead the file'
        end = text.find('\n---\n', 4)
        assert end > 0, 'frontmatter must close with `---`'
        fm = text[4:end]
        assert 'description:' in fm
        assert 'allowed-tools:' in fm
        assert 'argument-hint:' in fm

    def test_allowed_tools_includes_required(self):
        text = DECIDE_MD.read_text(encoding='utf-8')
        m = re.search(r'^allowed-tools:\s*(.+)$', text, re.MULTILINE)
        assert m is not None
        tools = m.group(1)
        # Atomic ADR + invariant write needs Read (existing state) +
        # Edit (append both files) + Bash (smoke-test the hook).
        for required in ('Read', 'Edit', 'Bash'):
            assert required in tools, f'/decide must allow {required}'

    def test_references_both_registries_atomically(self):
        """The doc must say both files are written in the same approval —
        that's the core promise that distinguishes /decide from running
        /adr-add then /inv-add separately."""
        text = DECIDE_MD.read_text(encoding='utf-8').lower()
        assert 'decision-log.md' in text
        assert 'invariants.json' in text
        # The "atomic" promise must be explicit somewhere.
        assert 'atomic' in text or 'one approval' in text or \
               'in the same turn' in text

    def test_references_cross_link_field(self):
        """Cross-link contract: invariant.related_adr ↔ ADR enforcement.
        If the doc loses this contract, drift creeps back in."""
        text = DECIDE_MD.read_text(encoding='utf-8')
        assert 'related_adr' in text, (
            '/decide must document the invariant.related_adr cross-link'
        )
        # ADR enforcement field must reference invariants.json by id.
        assert 'invariants.json#' in text, (
            '/decide must document the ADR.enforcement → invariants.json#<id> link'
        )

    def test_smoke_test_block_present(self):
        """The doc requires a smoke-test step that pipes a fake envelope
        through invariant_guard.py. If this is removed, /decide could
        register an invariant that doesn't actually enforce anything."""
        text = DECIDE_MD.read_text(encoding='utf-8')
        assert 'invariant_guard.py' in text
        assert 'smoke' in text.lower()

    def test_default_severity_is_warn_not_blocker(self):
        """HE policy: don't auto-blocker without explicit user opt-in.
        Same rule as /inv-add."""
        text = DECIDE_MD.read_text(encoding='utf-8')
        assert re.search(r'default.*warn', text, re.IGNORECASE), (
            'doc must say default severity is `warn` (not `blocker`)'
        )

    def test_references_bypass_syntax(self):
        """Closing the loop: user must know how to override one-off.
        G2 ephemeral file mechanism (v0.10.0)."""
        text = DECIDE_MD.read_text(encoding='utf-8')
        assert 'bypass-invariant' in text
