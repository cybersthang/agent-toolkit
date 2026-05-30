# -*- coding: utf-8 -*-
"""Tests for implement_noted_validator.py — eval s4."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
TOOL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "implement_noted_validator.py"


def _load():
    spec = importlib.util.spec_from_file_location("_iv", str(TOOL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_spec(workspace, slug, eval_ids):
    sd = workspace / ".agent-toolkit" / "specs"
    sd.mkdir(parents=True, exist_ok=True)
    spec = sd / f"{slug}.md"
    body = "---\n"
    body += f"slug: {slug}\nmodule: demo\nstatus: implementing\nfeature_kind: orchestration\n"
    body += "acceptance_evals:\n"
    for eid in eval_ids:
        body += f"  - id: {eid}\n    story: x\n    grader: code\n    probe: {{}}\n    expected: {{}}\n    target_pass_rate: 1.0\n"
    body += "---\n# spec\n"
    spec.write_text(body, encoding="utf-8")
    return spec


def _make_impl_noted(workspace, slug, body):
    sd = workspace / ".agent-toolkit" / "specs"
    sd.mkdir(parents=True, exist_ok=True)
    p = sd / f"{slug}.implement-noted.md"
    p.write_text(body, encoding="utf-8")
    return p


class TestImplementNotedValidator(unittest.TestCase):

    def setUp(self):
        self.mod = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_sd_file_missing_flagged(self):
        _make_spec(self.workspace, "feat", ["e1-thing"])
        body = (
            "---\nspec: feat\ntotal_scope_deviations: 1\n"
            "total_tradeoffs_with_evidence: 0\ntotal_followups: 0\n---\n"
            "\n## 1. Scope deviations\n"
            "- **SD-1**: stuff\n"
            "  - Type: outside-spec\n"
            "  - File(s) affected: `nonexistent/file.py:1-5`\n"
            "  - Spec linkage: none\n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        self.assertEqual(result["verdict"], "issues")
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertIn("sd-file-missing", kinds)

    def test_sd_spec_linkage_unknown_flagged(self):
        _make_spec(self.workspace, "feat", ["e1-real-id"])
        (self.workspace / "models").mkdir()
        (self.workspace / "models" / "thing.py").write_text("a\nb\nc\n", encoding="utf-8")
        body = (
            "---\nspec: feat\n---\n"
            "\n## 1. Scope deviations\n"
            "- **SD-1**: stuff\n"
            "  - File(s) affected: `models/thing.py:1-3`\n"
            "  - Spec linkage: e99-nonexistent-id\n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertIn("sd-spec-linkage-unknown", kinds)

    def test_t_no_transcript_cite_flagged(self):
        _make_spec(self.workspace, "feat", ["e1"])
        body = (
            "---\nspec: feat\n---\n"
            "\n## 2. In-transcript trade-offs\n"
            "- **T-1**: decision\n"
            "  - Transcript evidence: \n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertIn("t-transcript-evidence-missing", kinds)

    def test_f_priority_invalid_flagged(self):
        _make_spec(self.workspace, "feat", ["e1"])
        body = (
            "---\nspec: feat\n---\n"
            "\n## 3. Open follow-ups\n"
            "- **F-1**: stuff\n"
            "  - Priority: bogus\n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertIn("f-priority-invalid", kinds)

    def test_clean_artifact(self):
        _make_spec(self.workspace, "feat", ["e1-good"])
        (self.workspace / "models").mkdir()
        (self.workspace / "models" / "thing.py").write_text("x\ny\nz\n", encoding="utf-8")
        body = (
            "---\nschema_version: 1\nspec: feat\ntotal_scope_deviations: 1\n"
            "total_tradeoffs_with_evidence: 0\ntotal_followups: 0\n---\n"
            "\n## 1. Scope deviations\n"
            "- **SD-1**: stuff\n"
            "  - File(s) affected: `models/thing.py:1-3`\n"
            "  - Spec linkage: e1-good\n"
            "  - Confidence: high\n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        self.assertEqual(result["verdict"], "clean", "issues: %s" % result.get("issues"))

    def test_frontmatter_count_mismatch_flagged(self):
        _make_spec(self.workspace, "feat", ["e1"])
        body = (
            "---\nspec: feat\ntotal_scope_deviations: 5\n---\n"
            "\n## 1. Scope deviations\n"
            "- **SD-1**: stuff\n"
            "  - Spec linkage: none\n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertIn("frontmatter-count-mismatch", kinds)


class TestSchemaVersionEnforce(unittest.TestCase):
    """Phase G v0.9.0: schema_version field enforcement."""

    def setUp(self):
        self.mod = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        _make_spec(self.workspace, "feat", ["e1"])

    def test_missing_schema_version_flagged(self):
        body = (
            "---\nspec: feat\n---\n"
            "\n## 1. Scope deviations\n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertIn("schema-version-missing", kinds)

    def test_schema_version_1_passes(self):
        body = (
            "---\nschema_version: 1\nspec: feat\n---\n"
            "\n## 1. Scope deviations\n"
        )
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace)
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertNotIn("schema-version-missing", kinds)
        self.assertNotIn("schema-version-unsupported", kinds)

    def test_no_schema_check_flag_disables(self):
        body = "---\nspec: feat\n---\n\n## 1. Scope deviations\n"
        impl = _make_impl_noted(self.workspace, "feat", body)
        result = self.mod.validate(impl, self.workspace,
                                   enforce_schema_version=False)
        kinds = [iss["kind"] for iss in result["issues"]]
        self.assertNotIn("schema-version-missing", kinds)


if __name__ == "__main__":
    unittest.main()
