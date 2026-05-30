# -*- coding: utf-8 -*-
"""Tests for implement_snapshot_hook.py — eval s3."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "implement_snapshot_hook.py"
SNAPSHOT_TOOL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "implement_snapshot.py"
PY = sys.executable


def _git_init_repo(td: Path, branch: str = "feature-foo") -> Path:
    project = td / "proj"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True, timeout=10)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "checkout", "-B", branch], cwd=str(project),
                   capture_output=True, timeout=5)
    # Install snapshot tool inside project at expected path
    tools_dir = project / ".codex" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(str(SNAPSHOT_TOOL), str(tools_dir / "implement_snapshot.py"))
    return project


def _make_spec_with_affected(project: Path, slug: str):
    sd = project / ".agent-toolkit" / "specs"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / f"{slug}.md").write_text(
        "---\n"
        f"slug: {slug}\nmodule: demo\nstatus: implementing\nfeature_kind: orchestration\n"
        "affected_modules:\n"
        "  - models/\n"
        "acceptance_evals:\n"
        "  - id: e1\n    story: x\n    grader: code\n    probe: {}\n    expected: {}\n    target_pass_rate: 1.0\n"
        "---\n# spec\n",
        encoding="utf-8",
    )


def _run_hook(envelope, cwd, timeout=10):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, cwd=str(cwd), env=env,
    )


class TestSnapshotHook(unittest.TestCase):

    def test_snapshot_on_first_feature_file_edit(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            _make_spec_with_affected(project, "feature-foo")
            (project / "models").mkdir(parents=True, exist_ok=True)
            target = project / "models" / "x.py"
            target.write_text("orig\n", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            manifest = project / ".agent-toolkit" / ".implement_snapshots" / "feature-foo" / "_manifest.json"
            self.assertTrue(manifest.exists())
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertIn("models/x.py", data["files"])

    def test_no_snapshot_when_no_spec(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-bar")
            (project / "models").mkdir(parents=True, exist_ok=True)
            target = project / "models" / "x.py"
            target.write_text("orig\n", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            manifest = project / ".agent-toolkit" / ".implement_snapshots" / "feature-bar"
            self.assertFalse(manifest.exists())

    def test_no_snapshot_on_main_branch(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="main")
            _make_spec_with_affected(project, "main")
            (project / "models").mkdir(parents=True, exist_ok=True)
            target = project / "models" / "x.py"
            target.write_text("orig\n", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            manifest = project / ".agent-toolkit" / ".implement_snapshots" / "main"
            self.assertFalse(manifest.exists())

    def test_no_snapshot_on_test_file(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-test")
            _make_spec_with_affected(project, "feature-test")
            (project / "tests").mkdir(parents=True, exist_ok=True)
            target = project / "tests" / "test_x.py"
            target.write_text("orig\n", encoding="utf-8")
            envelope = {
                "cwd": str(project),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            }
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            manifest = project / ".agent-toolkit" / ".implement_snapshots" / "feature-test"
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
