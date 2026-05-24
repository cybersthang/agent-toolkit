# -*- coding: utf-8 -*-
"""Runtime smoke tests for spec_first_guard PreToolUse hook (v0.7.0).

Covers the 7 acceptance_evals (g1-g7) declared in
`specs/v0.7.0-spec-first-guard.md`:

  g1 — warn on feature-edit without spec
  g2 — no-op on main/master/trunk branch
  g3 — no-op on test file edit
  g4 — no warn if spec has acceptance_evals
  g5 — bypass marker honored
  g6 — config-driven feature_scope_globs
  g7 — fail-open on every error path
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "spec_first_guard.py"
PY = sys.executable


def _make_git_repo(td: Path, branch: str = "feature-x") -> Path:
    """Init a git repo at <td>/proj with given branch name."""
    project = td / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "--initial-branch=" + branch],
                   cwd=str(project), capture_output=True, timeout=10)
    # Some git versions don't support --initial-branch; create+switch.
    subprocess.run(["git", "config", "user.email", "test@test"],
                   cwd=str(project), capture_output=True, timeout=5)
    subprocess.run(["git", "config", "user.name", "test"],
                   cwd=str(project), capture_output=True, timeout=5)
    subprocess.run(["git", "checkout", "-B", branch],
                   cwd=str(project), capture_output=True, timeout=5)
    return project


def _run_hook(envelope: dict, cwd: Path,
              timeout: int = 10) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope, ensure_ascii=False),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=str(cwd), env=env,
    )


class TestWarnOnFeatureEdit(unittest.TestCase):
    """g1 — warns on feature edit without spec on non-trunk branch."""

    def test_warn_emitted(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-foo")
            (project / "models").mkdir()
            target = project / "models" / "thing.py"
            target.write_text("# nope", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[spec-first-guard]", proc.stderr)
            self.assertIn("warn:", proc.stderr)
            self.assertIn("feature-foo", proc.stderr)


class TestNoOpOnTrunkBranch(unittest.TestCase):
    """g2 — silent on main/master/trunk."""

    def test_main_branch_no_warn(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="main")
            (project / "models").mkdir()
            target = project / "models" / "thing.py"
            target.write_text("# pass", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[spec-first-guard]", proc.stderr)

    def test_master_branch_no_warn(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="master")
            (project / "models").mkdir()
            target = project / "models" / "thing.py"
            target.write_text("# pass", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[spec-first-guard]", proc.stderr)


class TestNoOpOnTestEdit(unittest.TestCase):
    """g3 — test file edit doesn't trigger."""

    def test_test_file_no_warn(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-test")
            (project / "tests").mkdir()
            target = project / "tests" / "test_foo.py"
            target.write_text("# test file", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[spec-first-guard]", proc.stderr)


class TestSpecPresentNoWarn(unittest.TestCase):
    """g4 — spec with acceptance_evals → no warn."""

    def test_spec_with_evals_silences_hook(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-good")
            (project / ".agent-toolkit" / "specs").mkdir(parents=True)
            spec = project / ".agent-toolkit" / "specs" / "feature-good.md"
            spec.write_text(
                "---\n"
                "slug: feature-good\n"
                "branch: feature-good\n"
                "acceptance_evals:\n"
                "  - id: e1-something\n"
                "    story: do something\n"
                "  - id: e2-other\n"
                "    story: do other\n"
                "---\n\n# Spec\n",
                encoding="utf-8",
            )
            (project / "models").mkdir()
            target = project / "models" / "thing.py"
            target.write_text("# good", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[spec-first-guard]", proc.stderr)


class TestBypassMarker(unittest.TestCase):
    """g5 — bypass token in any envelope field skips hook."""

    def test_bypass_marker_in_tool_input(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="hotfix-typo")
            (project / "models").mkdir()
            target = project / "models" / "thing.py"
            target.write_text("# typo", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(target),
                    "old_string": "spec-first-guard: skip typo-only edit",
                    "new_string": "fixed",
                },
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[spec-first-guard]", proc.stderr)


class TestConfigDrivenGlobs(unittest.TestCase):
    """g6 — coverage_config.json override is honored."""

    def test_custom_feature_globs_respected(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-django")
            (project / ".agent-toolkit").mkdir(exist_ok=True)
            (project / ".agent-toolkit" / "coverage_config.json").write_text(
                json.dumps({
                    "feature_scope_globs": ["**/django_only/*.py"],
                }),
                encoding="utf-8",
            )
            # Edit a file MATCHING the custom glob (not the default).
            (project / "django_only").mkdir()
            target = project / "django_only" / "x.py"
            target.write_text("# in scope per custom", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[spec-first-guard]", proc.stderr)

    def test_file_outside_custom_globs_silent(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-django")
            (project / ".agent-toolkit").mkdir(exist_ok=True)
            (project / ".agent-toolkit" / "coverage_config.json").write_text(
                json.dumps({
                    "feature_scope_globs": ["**/django_only/*.py"],
                }),
                encoding="utf-8",
            )
            # Edit `models/x.py` which would match DEFAULT but is NOT in
            # custom globs — should be silent.
            (project / "models").mkdir()
            target = project / "models" / "x.py"
            target.write_text("# out of scope per custom", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn("[spec-first-guard]", proc.stderr)


class TestFailOpen(unittest.TestCase):
    """g7 — every error path returns exit 0 silent."""

    def test_corrupt_coverage_config(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-x")
            (project / ".agent-toolkit").mkdir(exist_ok=True)
            (project / ".agent-toolkit" / "coverage_config.json").write_text(
                "{not valid json", encoding="utf-8",
            )
            (project / "models").mkdir()
            target = project / "models" / "x.py"
            target.write_text("# pass", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            # Should NOT crash; warn or silent both acceptable but rc=0.
            self.assertEqual(proc.returncode, 0)

    def test_empty_stdin_silent(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-x")
            proc = subprocess.run(
                [PY, str(HOOK)],
                input="",
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=10, cwd=str(project),
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stderr or "").strip(), "")

    def test_malformed_json_silent(self):
        with tempfile.TemporaryDirectory() as td:
            project = _make_git_repo(Path(td), branch="feature-x")
            proc = subprocess.run(
                [PY, str(HOOK)],
                input="{not valid",
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=10, cwd=str(project),
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stderr or "").strip(), "")


if __name__ == "__main__":
    unittest.main()
