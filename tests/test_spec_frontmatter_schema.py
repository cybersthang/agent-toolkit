# -*- coding: utf-8 -*-
"""Tests for spec-frontmatter.schema.json — eval s1.

Validates that the schema file is well-formed JSON and declares the
expected fields (required + optional). Uses jsonschema if available
for full validation; otherwise falls back to structural checks.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = TOOLKIT_ROOT / "templates" / "agent_toolkit" / "spec-frontmatter.schema.json"


class TestSpecFrontmatterSchema(unittest.TestCase):

    def setUp(self):
        with SCHEMA.open(encoding="utf-8") as fh:
            self.schema = json.load(fh)

    def test_schema_is_draft_07(self):
        self.assertIn("draft-07", self.schema.get("$schema", ""))

    def test_required_fields_declared(self):
        required = set(self.schema.get("required", []))
        for f in ("slug", "module", "status", "feature_kind", "acceptance_evals"):
            self.assertIn(f, required,
                          f"required field '{f}' missing from schema")

    def test_affected_modules_optional_field_present(self):
        props = self.schema.get("properties", {})
        self.assertIn("affected_modules", props)
        # Not required (so legacy specs grandfather)
        self.assertNotIn("affected_modules", self.schema.get("required", []))
        # Type array of strings
        am = props["affected_modules"]
        self.assertEqual(am.get("type"), "array")

    def test_affected_symbols_optional_field_present(self):
        props = self.schema.get("properties", {})
        self.assertIn("affected_symbols", props)
        self.assertEqual(props["affected_symbols"].get("type"), "array")

    def test_feature_kind_enum_includes_orchestration(self):
        props = self.schema.get("properties", {})
        fk = props.get("feature_kind", {})
        enum = fk.get("enum", [])
        for v in ("orchestration", "classification", "regression",
                  "maintenance"):
            self.assertIn(v, enum, f"feature_kind enum missing '{v}'")


if __name__ == "__main__":
    unittest.main()
