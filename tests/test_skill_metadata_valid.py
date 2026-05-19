"""Lint every templates/**/SKILL.md frontmatter.

YAML frontmatter typos silently make the skill un-loadable in Claude Code
and Cursor — both surface the skill by `name:` from the header, not the
filename. This test catches:

- Missing frontmatter delimiters (`---` open + close).
- Missing required fields (`name`, `description`).
- `name` slug not matching parent folder (the runtime convention).
- `description` too short to be useful for intent routing (< 40 chars).
- `description` exceeding the 1024-char hard limit some clients impose.
- Duplicate `name:` across folders (would collide in the skill registry).
- Stray BOM or CRLF that breaks naive YAML readers.

Kept dependency-free — does NOT pull in pyyaml, since the toolkit
installer itself is stdlib-only. We parse the frontmatter block with a
simple regex; this is sufficient for the flat key-value shape used by
every shipped skill.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_GLOB = 'templates/cursor/skills/**/SKILL.md'

# Allowed keys in the YAML frontmatter. Any key outside this set is a typo.
ALLOWED_KEYS = {'name', 'description', 'license', 'model', 'allowed-tools'}
REQUIRED_KEYS = {'name', 'description'}

# Description must be intent-routable: too short and the LLM can't match
# the right skill; too long and clients truncate it.
MIN_DESC_LEN = 40
MAX_DESC_LEN = 1024

# Slug regex — matches the convention used by every shipped skill.
SLUG_RE = re.compile(r'^[a-z][a-z0-9-]*$')


def _collect_skill_files():
    paths = sorted(TOOLKIT_ROOT.glob(SKILLS_GLOB))
    # At least one skill must exist or the test setup is wrong.
    assert paths, f'no SKILL.md files found under {SKILLS_GLOB}'
    return paths


def _parse_frontmatter(text: str) -> dict:
    """Parse `---\\n key: value ... \\n---` into a dict.

    Returns the first frontmatter block only. Multi-line values are not
    supported (no shipped skill needs them). Raises ValueError on shape
    problems so the calling test can surface a clear failure message.
    """
    if not text.startswith('---'):
        raise ValueError('missing opening `---` delimiter on line 1')
    # Find the closing delimiter.
    rest = text[3:]
    end_idx = rest.find('\n---')
    if end_idx == -1:
        raise ValueError('missing closing `---` delimiter')
    block = rest[:end_idx].strip('\n')
    out = {}
    for lineno, raw in enumerate(block.splitlines(), start=2):
        line = raw.rstrip()
        if not line or line.startswith('#'):
            continue
        # Continuation of previous key (indented) — we don't expect this in
        # shipped skills; flag it so it stays disallowed.
        if line.startswith((' ', '\t')):
            raise ValueError(f'line {lineno}: indented continuation not supported')
        if ':' not in line:
            raise ValueError(f'line {lineno}: missing `:` separator')
        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip()
        if key in out:
            raise ValueError(f'line {lineno}: duplicate key `{key}`')
        out[key] = value
    return out


@pytest.mark.parametrize('skill_path', _collect_skill_files(),
                         ids=lambda p: p.relative_to(TOOLKIT_ROOT).as_posix())
def test_skill_frontmatter_parseable(skill_path: Path):
    """Every SKILL.md must have a parseable frontmatter block."""
    text = skill_path.read_text(encoding='utf-8')
    # Reject UTF-8 BOM — breaks naive readers.
    assert not text.startswith('﻿'), (
        f'{skill_path}: starts with UTF-8 BOM — strip it'
    )
    fm = _parse_frontmatter(text)
    assert fm, f'{skill_path}: frontmatter parsed as empty'


@pytest.mark.parametrize('skill_path', _collect_skill_files(),
                         ids=lambda p: p.relative_to(TOOLKIT_ROOT).as_posix())
def test_skill_required_keys_present(skill_path: Path):
    """`name` and `description` must both be present and non-empty."""
    fm = _parse_frontmatter(skill_path.read_text(encoding='utf-8'))
    for key in REQUIRED_KEYS:
        assert key in fm, f'{skill_path}: missing required key `{key}`'
        assert fm[key], f'{skill_path}: `{key}` is empty'


@pytest.mark.parametrize('skill_path', _collect_skill_files(),
                         ids=lambda p: p.relative_to(TOOLKIT_ROOT).as_posix())
def test_skill_no_unknown_keys(skill_path: Path):
    """All frontmatter keys must be in the allow-list (catches typos)."""
    fm = _parse_frontmatter(skill_path.read_text(encoding='utf-8'))
    unknown = set(fm.keys()) - ALLOWED_KEYS
    assert not unknown, (
        f'{skill_path}: unknown frontmatter keys: {sorted(unknown)}. '
        f'Allowed: {sorted(ALLOWED_KEYS)}'
    )


@pytest.mark.parametrize('skill_path', _collect_skill_files(),
                         ids=lambda p: p.relative_to(TOOLKIT_ROOT).as_posix())
def test_skill_name_matches_folder(skill_path: Path):
    """`name:` slug must match the parent folder name — runtime convention."""
    fm = _parse_frontmatter(skill_path.read_text(encoding='utf-8'))
    expected = skill_path.parent.name
    assert fm['name'] == expected, (
        f'{skill_path}: name=`{fm["name"]}` does not match folder=`{expected}`'
    )
    assert SLUG_RE.match(fm['name']), (
        f'{skill_path}: name=`{fm["name"]}` violates slug shape (lowercase, dashes only)'
    )


@pytest.mark.parametrize('skill_path', _collect_skill_files(),
                         ids=lambda p: p.relative_to(TOOLKIT_ROOT).as_posix())
def test_skill_description_length(skill_path: Path):
    """Description must be long enough to be routable, short enough to fit."""
    fm = _parse_frontmatter(skill_path.read_text(encoding='utf-8'))
    desc = fm['description']
    assert MIN_DESC_LEN <= len(desc) <= MAX_DESC_LEN, (
        f'{skill_path}: description length {len(desc)} outside '
        f'[{MIN_DESC_LEN}, {MAX_DESC_LEN}]'
    )


def test_skill_names_globally_unique():
    """No two SKILL.md files may declare the same `name:`."""
    by_name = defaultdict(list)
    for path in _collect_skill_files():
        fm = _parse_frontmatter(path.read_text(encoding='utf-8'))
        by_name[fm['name']].append(path)
    duplicates = {n: paths for n, paths in by_name.items() if len(paths) > 1}
    assert not duplicates, (
        'duplicate skill `name:` values: ' +
        '; '.join(
            f'{n} -> {[str(p.relative_to(TOOLKIT_ROOT)) for p in paths]}'
            for n, paths in duplicates.items()
        )
    )
