# -*- coding: utf-8 -*-
"""Tests for missing_sd_detector.py — eval s5."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
TOOL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "missing_sd_detector.py"
SNAPSHOT = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "implement_snapshot.py"


def _load_detector():
    spec = importlib.util.spec_from_file_location("_msd", str(TOOL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup_workspace(td):
    project = Path(td) / "proj"
    project.mkdir()
    (project / ".codex" / "tools").mkdir(parents=True)
    shutil.copy2(str(SNAPSHOT), str(project / ".codex" / "tools" / "implement_snapshot.py"))
    return project


def _make_spec(project, slug, affected_modules, eval_targets=None):
    sd = project / ".agent-toolkit" / "specs"
    sd.mkdir(parents=True, exist_ok=True)
    body = "---\n"
    body += f"slug: {slug}\nmodule: demo\nstatus: implementing\nfeature_kind: orchestration\n"
    body += "affected_modules:\n"
    for am in affected_modules:
        body += f"  - {am}\n"
    body += "acceptance_evals:\n"
    if eval_targets:
        for i, t in enumerate(eval_targets, 1):
            body += f"  - id: e{i}\n    story: x\n    grader: code\n"
            body += "    probe:\n"
            body += "      tool: pytest\n"
            body += f"      args:\n        target: {t}\n"
            body += "    expected: {}\n    target_pass_rate: 1.0\n"
    else:
        body += "  - id: e1\n    story: x\n    grader: code\n    probe: {}\n    expected: {}\n    target_pass_rate: 1.0\n"
    body += "---\n# spec\n"
    (sd / f"{slug}.md").write_text(body, encoding="utf-8")


def _snapshot_files(project, slug, files):
    """Build snapshot manifest pretending these files were modified."""
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "_snap", str(project / ".codex" / "tools" / "implement_snapshot.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    # Create empty pre-state then write current with changed content
    for rel in files:
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pre\n", encoding="utf-8")
    m.snapshot_create(slug, files, project)
    # Modify after snapshot
    for rel in files:
        (project / rel).write_text("post\n", encoding="utf-8")


class TestMissingSdDetector(unittest.TestCase):

    def setUp(self):
        self.mod = _load_detector()

    def test_edit_in_affected_modules_covered(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_workspace(td)
            _make_spec(project, "feat", ["models/"])
            _snapshot_files(project, "feat", ["models/x.py"])
            result = self.mod.detect("feat", project)
            self.assertEqual(result["verdict"], "clean")
            self.assertEqual(result["missing_count"], 0)

    def test_edit_outside_affected_modules_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_workspace(td)
            _make_spec(project, "feat", ["models/"])
            _snapshot_files(project, "feat",
                            ["models/x.py", "random/y.py"])
            result = self.mod.detect("feat", project)
            self.assertEqual(result["verdict"], "missing-sd")
            self.assertIn("random/y.py", result["missing_files"])
            self.assertNotIn("models/x.py", result["missing_files"])

    def test_eval_target_match_covers(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_workspace(td)
            _make_spec(project, "feat", ["unused/"],
                       eval_targets=["tests/test_foo.py"])
            _snapshot_files(project, "feat", ["tests/test_foo.py"])
            result = self.mod.detect("feat", project)
            self.assertEqual(result["verdict"], "clean")

    def test_bypass_marker_covers(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_workspace(td)
            _make_spec(project, "feat", ["models/"])
            _snapshot_files(project, "feat", ["random/y.py"])
            # Create implement-noted with bypass marker
            impl = project / ".agent-toolkit" / "specs" / "feat.implement-noted.md"
            impl.write_text(
                "---\nspec: feat\n---\n# notes\n\n"
                "scope-creep-allowed: random/y.py one-line-typo-fix\n",
                encoding="utf-8",
            )
            result = self.mod.detect("feat", project)
            self.assertEqual(result["verdict"], "clean")

    def test_missing_spec_returns_error(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_workspace(td)
            result = self.mod.detect("nonexistent", project)
            self.assertIn("error", result)


class TestFabricatedSdDetection(unittest.TestCase):
    """P4 v0.8.0: SD-N referencing a file NOT actually modified per
    snapshot = fabricated SD. Detector flags 'fabricated-sd' verdict."""

    def setUp(self):
        self.mod = _load_detector()

    def test_sd_referencing_unmodified_file_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_workspace(td)
            _make_spec(project, "feat", ["models/"])
            # Modify ONE file via snapshot
            _snapshot_files(project, "feat", ["models/real.py"])

            # Impl-noted declares SD pointing at a DIFFERENT file
            # (not in modified list) — hallucinated
            impl = project / ".agent-toolkit" / "specs" / "feat.implement-noted.md"
            impl.write_text(
                "---\nspec: feat\n---\n# notes\n\n"
                "## 1. Scope deviations\n\n"
                "### SD-1: stuff\n"
                "- File(s) affected: `models/fabricated.py:1-3`\n"
                "- Spec linkage: none\n",
                encoding="utf-8",
            )
            result = self.mod.detect("feat", project)
            self.assertIn(result["verdict"],
                          ("fabricated-sd", "missing-and-fabricated"))
            self.assertGreater(result["fabricated_sd_count"], 0)
            self.assertIn("models/fabricated.py", result["fabricated_sd_files"])

    def test_clean_when_sd_matches_modified(self):
        with tempfile.TemporaryDirectory() as td:
            project = _setup_workspace(td)
            _make_spec(project, "feat", ["models/"])
            _snapshot_files(project, "feat", ["models/real.py"])

            # Impl-noted SD references the actually-modified file
            impl = project / ".agent-toolkit" / "specs" / "feat.implement-noted.md"
            impl.write_text(
                "---\nspec: feat\n---\n# notes\n\n"
                "## 1. Scope deviations\n\n"
                "### SD-1: stuff\n"
                "- File(s) affected: `models/real.py:1-3`\n"
                "- Spec linkage: none\n",
                encoding="utf-8",
            )
            result = self.mod.detect("feat", project)
            self.assertEqual(result["fabricated_sd_count"], 0)
            self.assertEqual(result["verdict"], "clean")


if __name__ == "__main__":
    unittest.main()
