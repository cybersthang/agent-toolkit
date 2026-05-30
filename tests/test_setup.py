"""Unit tests for setup.py — frontmatter parsing, content-diff detection,
template/copy decisioning, MEMORY.md regeneration."""
from __future__ import annotations

import sys
from pathlib import Path


# Provide stub `installer` import path same as setup.py does.
TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_ROOT / 'lib'))
sys.path.insert(0, str(TOOLKIT_ROOT))

import setup  # noqa: E402  — module-level import of setup.py


# --------------------------------------------------------- _parse_frontmatter ---
def test_parse_frontmatter_extracts_top_level_keys():
    text = '---\nname: foo\ndescription: short\n---\nbody\n'
    fm = setup._parse_frontmatter(text)
    assert fm == {'name': 'foo', 'description': 'short'}


def test_parse_frontmatter_strips_quotes():
    text = '---\nname: "quoted name"\ndescription: \'single quoted\'\n---\n'
    fm = setup._parse_frontmatter(text)
    assert fm['name'] == 'quoted name'
    assert fm['description'] == 'single quoted'


def test_parse_frontmatter_ignores_nested_keys():
    text = '---\nname: foo\nmetadata:\n  type: feedback\n  origin: x\n---\n'
    fm = setup._parse_frontmatter(text)
    assert fm == {'name': 'foo'}  # nested `type:` skipped (whitespace prefix)


def test_parse_frontmatter_returns_empty_when_no_frontmatter():
    assert setup._parse_frontmatter('# heading\nbody') == {}


def test_parse_frontmatter_returns_empty_when_unterminated():
    assert setup._parse_frontmatter('---\nname: foo\nbody, no closing fence') == {}


# --------------------------------------------------------- regenerate_memory_index ---
def test_regenerate_memory_index_adds_missing_entries(tmp_path):
    # Create 2 memory files + a MEMORY.md missing one of them.
    (tmp_path / 'a.md').write_text(
        '---\nname: a\ndescription: A desc\n---\nbody\n', encoding='utf-8',
    )
    (tmp_path / 'b.md').write_text(
        '---\nname: b\ndescription: B desc\n---\nbody\n', encoding='utf-8',
    )
    (tmp_path / 'MEMORY.md').write_text(
        '- [A](a.md) — A desc\n', encoding='utf-8',
    )
    setup.regenerate_memory_index(tmp_path)
    index = (tmp_path / 'MEMORY.md').read_text(encoding='utf-8')
    assert '(a.md)' in index
    assert '(b.md)' in index
    assert 'B desc' in index


def test_regenerate_memory_index_skips_already_indexed(tmp_path):
    (tmp_path / 'a.md').write_text(
        '---\nname: a\ndescription: A desc\n---\n', encoding='utf-8',
    )
    (tmp_path / 'MEMORY.md').write_text(
        '- [Custom Title](a.md) — already indexed\n', encoding='utf-8',
    )
    setup.regenerate_memory_index(tmp_path)
    index = (tmp_path / 'MEMORY.md').read_text(encoding='utf-8')
    # Custom title preserved — no duplicate entry.
    assert 'Custom Title' in index
    assert index.count('(a.md)') == 1


def test_regenerate_memory_index_skips_files_without_description(tmp_path):
    (tmp_path / 'meta.md').write_text(
        '---\nname: meta-only\n---\nno description\n', encoding='utf-8',
    )
    (tmp_path / 'MEMORY.md').write_text('', encoding='utf-8')
    setup.regenerate_memory_index(tmp_path)
    index = (tmp_path / 'MEMORY.md').read_text(encoding='utf-8')
    assert '(meta.md)' not in index


# --------------------------------------------------------- _looks_templated ---
def test_looks_templated_detects_placeholder(tmp_path):
    p = tmp_path / 'tpl.md'
    p.write_text('Hello {{PROJECT_NAME}}!', encoding='utf-8')
    assert setup._looks_templated(p) is True


def test_looks_templated_returns_false_for_plain_file(tmp_path):
    p = tmp_path / 'plain.md'
    p.write_text('No placeholders here.', encoding='utf-8')
    assert setup._looks_templated(p) is False


def test_looks_templated_scans_full_file_not_just_8kb(tmp_path):
    """H2 regression — placeholder past byte 8192 must still be detected."""
    p = tmp_path / 'big.md'
    body = 'A' * 10_000 + '\n{{LATE_PLACEHOLDER}}\n'
    p.write_text(body, encoding='utf-8')
    assert setup._looks_templated(p) is True


# --------------------------------------------------------- _content_will_change ---
def test_content_will_change_true_when_dst_missing(tmp_path):
    src = tmp_path / 'src.txt'
    src.write_text('hello', encoding='utf-8')
    dst = tmp_path / 'dst.txt'
    assert setup._content_will_change(src, dst, 'COPY', {}) is True


def test_content_will_change_false_when_copy_identical(tmp_path):
    src = tmp_path / 'src.txt'
    src.write_text('hello', encoding='utf-8')
    dst = tmp_path / 'dst.txt'
    dst.write_text('hello', encoding='utf-8')
    assert setup._content_will_change(src, dst, 'COPY', {}) is False


def test_content_will_change_true_when_copy_differs(tmp_path):
    src = tmp_path / 'src.txt'
    src.write_text('hello', encoding='utf-8')
    dst = tmp_path / 'dst.txt'
    dst.write_text('world', encoding='utf-8')
    assert setup._content_will_change(src, dst, 'COPY', {}) is True


def test_content_will_change_template_compares_rendered(tmp_path):
    src = tmp_path / 'tpl.txt'
    src.write_text('Name: {{NAME}}', encoding='utf-8')
    dst = tmp_path / 'dst.txt'
    dst.write_text('Name: Alice', encoding='utf-8')
    assert setup._content_will_change(src, dst, 'TEMPLATE', {'NAME': 'Alice'}) is False
    assert setup._content_will_change(src, dst, 'TEMPLATE', {'NAME': 'Bob'}) is True


def test_content_will_change_skip_exists_returns_false(tmp_path):
    src = tmp_path / 's.txt'
    src.write_text('x', encoding='utf-8')
    dst = tmp_path / 'd.txt'
    assert setup._content_will_change(src, dst, 'SKIP_EXISTS', {}) is False


# --------------------------------------------------------- seed_mcp_local_env (v0.27 B3) ---

def _setup_seed_fixture(tmp_path, *, gitignored=True, example_present=True):
    """Build the minimal layout `seed_mcp_local_env(target)` expects."""
    codex = tmp_path / '.codex'
    codex.mkdir()
    if example_present:
        (codex / 'mcp.local.env.example').write_text(
            'KEY=replace-me\n', encoding='utf-8')
    if gitignored:
        (tmp_path / '.gitignore').write_text(
            '.codex/mcp.local.env\n', encoding='utf-8')
    return tmp_path


def test_seed_mcp_local_env_creates_from_example_when_gitignored(tmp_path):
    target = _setup_seed_fixture(tmp_path)
    setup.seed_mcp_local_env(target)
    real = target / '.codex' / 'mcp.local.env'
    assert real.exists()
    assert real.read_text(encoding='utf-8') == 'KEY=replace-me\n'


def test_seed_mcp_local_env_preserves_existing_user_creds(tmp_path):
    target = _setup_seed_fixture(tmp_path)
    real = target / '.codex' / 'mcp.local.env'
    real.write_text('KEY=my-real-prod-cred\n', encoding='utf-8')
    setup.seed_mcp_local_env(target)
    # Must NOT overwrite real creds.
    assert real.read_text(encoding='utf-8') == 'KEY=my-real-prod-cred\n'


def test_seed_mcp_local_env_refuses_when_not_gitignored(tmp_path):
    """Cred-leak protection: never seed an env file in a tree that isn't
    gitignoring it."""
    target = _setup_seed_fixture(tmp_path, gitignored=False)
    setup.seed_mcp_local_env(target)
    assert not (target / '.codex' / 'mcp.local.env').exists()


def test_seed_mcp_local_env_silent_when_example_missing(tmp_path):
    target = _setup_seed_fixture(tmp_path, example_present=False)
    # Should not raise, should not create the env file.
    setup.seed_mcp_local_env(target)
    assert not (target / '.codex' / 'mcp.local.env').exists()
