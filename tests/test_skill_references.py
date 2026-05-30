"""Every `references/*.md` a SKILL.md routes to must exist on disk.

Guards against dangling reference links: `make rebuild` stayed GREEN while 21
referenced files were missing because nothing asserted the targets exist.
Parametrized per SKILL.md so a failure names the exact skill + missing files.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = TOOLKIT_ROOT / "templates" / "cursor" / "skills"
# Capture an optional path prefix before `references/` so cross-skill links
# (`_common/code-review/references/security-checklist.md`,
# `real-data-proof/references/block-async-worked-example.md`) are matched whole.
REF_RE = re.compile(r"[A-Za-z0-9._/-]*references/[A-Za-z0-9._-]+\.md")


def _skill_files():
    return sorted(SKILLS_ROOT.rglob("SKILL.md"))


def test_skill_md_discovered():
    assert _skill_files(), f"no SKILL.md found under {SKILLS_ROOT}"


@pytest.mark.parametrize(
    "skill_md", _skill_files(),
    ids=lambda p: str(p.relative_to(SKILLS_ROOT).parent),
)
def test_no_dangling_references(skill_md: Path):
    text = skill_md.read_text(encoding="utf-8")
    # A ref may be written relative to the citing skill dir, its category
    # parent (e.g. `real-data-proof/...` from inside `_common/`), or the
    # skills root (`_common/code-review/...`). Resolve against all.
    bases = [skill_md.parent, skill_md.parent.parent, SKILLS_ROOT, TOOLKIT_ROOT]
    missing = [
        ref for ref in sorted(set(REF_RE.findall(text)))
        if not any((base / ref).exists() for base in bases)
    ]
    assert not missing, (
        f"{skill_md.relative_to(TOOLKIT_ROOT)} routes to missing reference "
        f"file(s): {missing}"
    )
