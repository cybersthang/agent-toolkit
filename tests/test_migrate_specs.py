# -*- coding: utf-8 -*-
"""Tests for migrate_specs_affected_modules.py — eval s10."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
TOOL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "migrate_specs_affected_modules.py"


def _load():
    spec = importlib.util.spec_from_file_location("_mig", str(TOOL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _init_git_repo(td: Path) -> Path:
    project = td / "proj"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True, timeout=10)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(project),
                   capture_output=True, timeout=5)
    return project


def _commit(project: Path, file_rel: str, content: str):
    p = project / file_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", file_rel], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "commit", "-m", f"add {file_rel}"],
                   cwd=str(project), capture_output=True, timeout=5)


class TestMigrateSpecs(unittest.TestCase):

    def setUp(self):
        self.mod = _load()

    def test_backfill_from_git_log(self):
        with tempfile.TemporaryDirectory() as td:
            project = _init_git_repo(Path(td))
            # Spec without affected_modules
            spec_body = (
                "---\nslug: feat-x\nmodule: demo\nstatus: implementing\n"
                "feature_kind: orchestration\n"
                "acceptance_evals:\n  - id: e1\n    story: x\n    grader: code\n"
                "    probe: {}\n    expected: {}\n    target_pass_rate: 1.0\n"
                "---\n# spec\n"
            )
            _commit(project, ".agent-toolkit/specs/feat-x.md", spec_body)
            # Companion files modified across commits
            _commit(project, "templates/codex/tools/x.py", "# tool\n")
            _commit(project, "tests/test_x.py", "# test\n")
            # Re-commit spec to bind it to those file commits via shared history
            subprocess.run(["git", "log", "--format=%H"], cwd=str(project),
                          capture_output=True, timeout=5)

            result = self.mod.migrate(project, apply=True, top_n=8)
            specs = [r for r in result["results"] if "feat-x" in r["spec"]]
            self.assertEqual(len(specs), 1)
            # Verify spec file now contains affected_modules
            spec_path = project / ".agent-toolkit/specs/feat-x.md"
            text = spec_path.read_text(encoding="utf-8")
            self.assertIn("affected_modules:", text)

    def test_idempotent_re_run_no_change(self):
        with tempfile.TemporaryDirectory() as td:
            project = _init_git_repo(Path(td))
            spec_body = (
                "---\nslug: feat-x\nmodule: demo\nstatus: implementing\n"
                "feature_kind: orchestration\n"
                "affected_modules:\n  - already/declared/\n"
                "acceptance_evals:\n  - id: e1\n    story: x\n    grader: code\n"
                "    probe: {}\n    expected: {}\n    target_pass_rate: 1.0\n"
                "---\n# spec\n"
            )
            _commit(project, ".agent-toolkit/specs/feat-x.md", spec_body)
            result = self.mod.migrate(project, apply=True, top_n=8)
            for r in result["results"]:
                if "feat-x" in r["spec"]:
                    self.assertEqual(r["status"], "already-has-affected-modules")

    def test_dry_run_does_not_modify(self):
        with tempfile.TemporaryDirectory() as td:
            project = _init_git_repo(Path(td))
            spec_body = (
                "---\nslug: feat-y\nmodule: demo\nstatus: implementing\n"
                "feature_kind: orchestration\n"
                "acceptance_evals:\n  - id: e1\n    story: x\n    grader: code\n"
                "    probe: {}\n    expected: {}\n    target_pass_rate: 1.0\n"
                "---\n# spec\n"
            )
            _commit(project, ".agent-toolkit/specs/feat-y.md", spec_body)
            _commit(project, "templates/x.py", "# tool\n")
            spec_path = project / ".agent-toolkit/specs/feat-y.md"
            text_before = spec_path.read_text(encoding="utf-8")
            result = self.mod.migrate(project, apply=False, top_n=8)
            text_after = spec_path.read_text(encoding="utf-8")
            self.assertEqual(text_before, text_after)
            # But dry-run output indicates would-migrate
            for r in result["results"]:
                if "feat-y" in r["spec"]:
                    self.assertIn("dry-run", r["status"])


if __name__ == "__main__":
    unittest.main()
