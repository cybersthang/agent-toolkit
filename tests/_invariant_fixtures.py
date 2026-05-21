"""G9 v0.11.0 — canonical invariant builders shared across hook tests.

Importable module (unlike conftest.py which pytest auto-loads but does
not expose to `from conftest import …`). conftest.py wraps these as
fixtures for tests that prefer DI.

Why this exists: see header in tests/conftest.py G9 block. tl;dr —
raw-dict invariants are easy to write wrong and silently bypass the
production hook. These builders enforce the canonical schema shape so
test fixtures can't drift.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional, Union


INVARIANT_REQUIRED_KEYS = {'id', 'severity', 'description', 'rationale', 'source'}
INVARIANT_KNOWN_RULE_KEYS = {'must_keep_regex', 'must_keep_call'}


def make_invariant(
    inv_id: str,
    *,
    severity: str = 'blocker',
    description: str = '',
    applies_to: Optional[Iterable[str]] = None,
    must_keep_regex: Optional[Union[str, Iterable[str]]] = None,
    must_keep_call: Optional[Union[str, Iterable[str]]] = None,
    rationale: str = 'test',
    source: str = 'test',
) -> dict:
    """Build one invariant dict matching the canonical schema. Patterns
    live under `rules`, never top-level.

    Raises ValueError on:
    - severity not in (blocker, warn)
    - no rule pattern supplied (otherwise nothing is enforced)
    """
    if severity not in ('blocker', 'warn'):
        raise ValueError(f'severity must be blocker|warn, got {severity!r}')
    rules: dict = {}
    if must_keep_regex is not None:
        if isinstance(must_keep_regex, str):
            must_keep_regex = [must_keep_regex]
        rules['must_keep_regex'] = list(must_keep_regex)
    if must_keep_call is not None:
        if isinstance(must_keep_call, str):
            must_keep_call = [must_keep_call]
        rules['must_keep_call'] = list(must_keep_call)
    if not rules:
        raise ValueError(
            'invariant must include at least one of must_keep_regex / '
            'must_keep_call — otherwise no enforcement is possible'
        )
    return {
        'id': inv_id,
        'severity': severity,
        'description': description or inv_id,
        'applies_to': list(applies_to) if applies_to else [],
        'rules': rules,
        'rationale': rationale,
        'source': source,
    }


def write_invariants(workspace: Path, *invariants: dict) -> Path:
    """Write `.agent-toolkit/invariants.json` into `workspace` containing
    the given invariant dicts (each built via `make_invariant`).

    Returns the path to the written file. Structure (`{"invariants": [...]}`)
    is what production code expects.
    """
    d = workspace / '.agent-toolkit'
    d.mkdir(parents=True, exist_ok=True)
    path = d / 'invariants.json'
    payload = {'invariants': list(invariants)}
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return path
