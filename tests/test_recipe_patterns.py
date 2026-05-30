# -*- coding: utf-8 -*-
"""Recipe pattern catalog tests (eval c7).

Verify django_triggers.json + rails_triggers.json (and any new
language) declare ≥8 patterns each with non-empty `match_regex` +
`template`. Public-project compliance check — community PRs should
not regress pattern count.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
PATTERNS_DIR = TOOLKIT_ROOT / "templates" / "codex" / "recipe_patterns"
MIN_PATTERNS_PER_STACK = 8


def _load(name: str) -> dict:
    path = PATTERNS_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


class TestRecipePatternCatalog(unittest.TestCase):

    def test_django_min_patterns(self):
        data = _load("django_triggers.json")
        patterns = data.get("patterns") or []
        self.assertGreaterEqual(
            len(patterns), MIN_PATTERNS_PER_STACK,
            f"Django expected ≥{MIN_PATTERNS_PER_STACK} patterns, got {len(patterns)}",
        )
        for entry in patterns:
            self.assertTrue(entry.get("id"), "pattern missing id: %r" % entry)
            self.assertTrue(entry.get("match_regex"),
                            "pattern missing match_regex: %s" % entry.get("id"))
            self.assertTrue(entry.get("template"),
                            "pattern missing template: %s" % entry.get("id"))
            # Each regex must compile (no syntax errors).
            try:
                re.compile(entry["match_regex"])
            except re.error as e:
                self.fail("invalid regex in %s: %s" % (entry["id"], e))

    def test_rails_min_patterns(self):
        data = _load("rails_triggers.json")
        patterns = data.get("patterns") or []
        self.assertGreaterEqual(
            len(patterns), MIN_PATTERNS_PER_STACK,
            f"Rails expected ≥{MIN_PATTERNS_PER_STACK} patterns, got {len(patterns)}",
        )
        for entry in patterns:
            self.assertTrue(entry.get("id"))
            self.assertTrue(entry.get("match_regex"))
            self.assertTrue(entry.get("template"))
            try:
                re.compile(entry["match_regex"])
            except re.error as e:
                self.fail("invalid regex in %s: %s" % (entry["id"], e))

    def test_no_duplicate_ids_across_files(self):
        """Pattern ids should be globally unique to avoid recipe-engine
        ambiguity when multiple stack files load simultaneously."""
        seen = {}
        for f in PATTERNS_DIR.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            for p in data.get("patterns") or []:
                pid = p.get("id")
                if pid in seen:
                    self.fail(f"duplicate pattern id `{pid}` in "
                              f"{f.name} and {seen[pid]}")
                seen[pid] = f.name


if __name__ == "__main__":
    unittest.main()
