# -*- coding: utf-8 -*-
"""Tests for diff_hunk_annotator.py + diff_annotation_validator.py — eval s7."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
ANNOTATOR = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "diff_hunk_annotator.py"
VALIDATOR = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "diff_annotation_validator.py"
SNAPSHOT = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "implement_snapshot.py"


def _load(path):
    spec = importlib.util.spec_from_file_location("_mod", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup_project_with_snapshot(td, slug="feat"):
    project = Path(td) / "proj"
    project.mkdir()
    (project / ".codex" / "tools").mkdir(parents=True)
    shutil.copy2(str(SNAPSHOT), str(project / ".codex" / "tools" / "implement_snapshot.py"))
    # Create file
    (project / "models").mkdir()
    target = project / "models" / "foo.py"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    # Snapshot
    snap = _load(project / ".codex" / "tools" / "implement_snapshot.py")
    snap.snapshot_create(slug, ["models/foo.py"], project)
    # Modify
    target.write_text("line1\nNEW LINE\nline3\n", encoding="utf-8")
    return project


def _setup_spec(project, slug, eval_ids):
    sd = project / ".agent-toolkit" / "specs"
    sd.mkdir(parents=True, exist_ok=True)
    body = "---\n"
    body += f"slug: {slug}\nmodule: demo\nstatus: implementing\nfeature_kind: orchestration\n"
    body += "acceptance_evals:\n"
    for eid in eval_ids:
        body += f"  - id: {eid}\n    story: x\n    grader: code\n    probe: {{}}\n    expected: {{}}\n    target_pass_rate: 1.0\n"
    body += "---\n# spec\n"
    (sd / f"{slug}.md").write_text(body, encoding="utf-8")


class TestDiffHunkAnnotator(unittest.TestCase):

    def test_hunks_extracted_from_modified_file(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            ann = _load(ANNOTATOR)
            template = ann.build_annotation_template("feat", project)
            self.assertEqual(template["slug"], "feat")
            hunks = template["hunks"]
            self.assertGreater(len(hunks), 0)
            self.assertEqual(hunks[0]["file"], "models/foo.py")

    def test_markdown_render_has_tag_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            ann = _load(ANNOTATOR)
            template = ann.build_annotation_template("feat", project)
            md = ann.render_markdown_template(template)
            self.assertIn("## hunk", md)
            self.assertIn("tag:", md)
            self.assertIn("FILL", md)


class TestDiffAnnotationValidator(unittest.TestCase):

    def test_untagged_hunk_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            _setup_spec(project, "feat", ["e1-something"])
            ann = _load(ANNOTATOR)
            template = ann.build_annotation_template("feat", project)
            md = ann.render_markdown_template(template)
            ann_path = project / ".agent-toolkit" / "specs" / "feat.diff-annotations.md"
            ann_path.write_text(md, encoding="utf-8")
            val = _load(VALIDATOR)
            result = val.validate(ann_path, project)
            self.assertEqual(result["verdict"], "issues")
            self.assertGreater(result["untagged_or_invalid"], 0)

    def test_tagged_with_valid_eval_id_passes(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            _setup_spec(project, "feat", ["e1-something"])
            ann_path = project / ".agent-toolkit" / "specs" / "feat.diff-annotations.md"
            ann_path.write_text(
                "---\nslug: feat\n---\n\n"
                "## hunk `models/foo.py:h1`\n\n"
                "- type: modify\n"
                "- lines: 2-2\n"
                "- tag: e1-something\n\n"
                "```diff\n+NEW LINE\n```\n",
                encoding="utf-8",
            )
            val = _load(VALIDATOR)
            result = val.validate(ann_path, project)
            self.assertEqual(result["verdict"], "clean", "issues: %s" % result.get("issues"))

    def test_bypass_marker_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            _setup_spec(project, "feat", ["e1-only"])
            ann_path = project / ".agent-toolkit" / "specs" / "feat.diff-annotations.md"
            ann_path.write_text(
                "---\nslug: feat\n---\n\n"
                "## hunk `models/foo.py:h1`\n\n"
                "- type: modify\n"
                "- lines: 2-2\n"
                "- tag: untagged-hunk-allowed: typo-fix\n\n"
                "```diff\n+NEW LINE\n```\n",
                encoding="utf-8",
            )
            val = _load(VALIDATOR)
            result = val.validate(ann_path, project)
            self.assertEqual(result["verdict"], "clean")

    def test_unknown_tag_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            _setup_spec(project, "feat", ["e1-known"])
            ann_path = project / ".agent-toolkit" / "specs" / "feat.diff-annotations.md"
            ann_path.write_text(
                "---\nslug: feat\n---\n\n"
                "## hunk `models/foo.py:h1`\n\n"
                "- type: modify\n"
                "- lines: 2-2\n"
                "- tag: e999-fabricated\n\n"
                "```diff\n+NEW\n```\n",
                encoding="utf-8",
            )
            val = _load(VALIDATOR)
            result = val.validate(ann_path, project)
            kinds = [iss["kind"] for iss in result.get("issues") or []]
            self.assertIn("tag-unknown-reference", kinds)


class TestAutoTag(unittest.TestCase):
    """v0.7.3 — annotator auto-tag inference from spec eval targets +
    impl-noted SD file refs."""

    def test_auto_tag_matches_eval_target(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            # Spec with eval target pointing at modified file
            sd = project / ".agent-toolkit" / "specs"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "feat.md").write_text(
                "---\nslug: feat\nmodule: demo\nstatus: implementing\n"
                "feature_kind: orchestration\n"
                "acceptance_evals:\n"
                "  - id: e1-thing\n    story: x\n    grader: code\n"
                "    probe:\n      tool: pytest\n      args:\n"
                "        target: models/foo.py\n"
                "    expected: {}\n    target_pass_rate: 1.0\n"
                "---\n# spec\n",
                encoding="utf-8",
            )
            ann = _load(ANNOTATOR)
            template = ann.build_annotation_template("feat", project)
            self.assertGreater(template["auto_tagged"], 0)
            hunks_with_tag = [h for h in template["hunks"]
                              if h.get("auto_tag") == "e1-thing"]
            self.assertGreater(len(hunks_with_tag), 0)

    def test_auto_tag_matches_sd_file_ref(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            sd = project / ".agent-toolkit" / "specs"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "feat.md").write_text(
                "---\nslug: feat\nmodule: demo\nstatus: implementing\n"
                "feature_kind: orchestration\n"
                "acceptance_evals:\n"
                "  - id: e1\n    story: x\n    grader: code\n    probe: {}\n"
                "    expected: {}\n    target_pass_rate: 1.0\n"
                "---\n# spec\n",
                encoding="utf-8",
            )
            (sd / "feat.implement-noted.md").write_text(
                "---\nspec: feat\n---\n\n"
                "## 1. Scope deviations\n\n"
                "### SD-1: stuff\n"
                "- File(s) affected: `models/foo.py:1-3`\n"
                "- Spec linkage: e1\n",
                encoding="utf-8",
            )
            ann = _load(ANNOTATOR)
            template = ann.build_annotation_template("feat", project)
            hunks_with_sd = [h for h in template["hunks"]
                              if h.get("auto_tag") == "SD-1"]
            self.assertGreater(len(hunks_with_sd), 0)

    def test_residual_hunk_gets_placeholder(self):
        """File NOT in eval targets or SD refs → no auto_tag."""
        with tempfile.TemporaryDirectory() as td:
            project = _setup_project_with_snapshot(td, "feat")
            sd = project / ".agent-toolkit" / "specs"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "feat.md").write_text(
                "---\nslug: feat\nmodule: demo\nstatus: implementing\n"
                "feature_kind: orchestration\n"
                "acceptance_evals:\n"
                "  - id: e1-elsewhere\n    story: x\n    grader: code\n"
                "    probe:\n      tool: pytest\n      args:\n"
                "        target: tests/test_unrelated.py\n"
                "    expected: {}\n    target_pass_rate: 1.0\n"
                "---\n# spec\n",
                encoding="utf-8",
            )
            ann = _load(ANNOTATOR)
            template = ann.build_annotation_template("feat", project)
            md = ann.render_markdown_template(template)
            self.assertIn("FILL", md)
            # auto_tagged count is 0 because eval target doesn't match modified file
            self.assertEqual(template["auto_tagged"], 0)


if __name__ == "__main__":
    unittest.main()
