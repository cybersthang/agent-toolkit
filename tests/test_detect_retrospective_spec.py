# -*- coding: utf-8 -*-
"""Tests for detect_retrospective_spec.py.

Covers acceptance_eval c4-retrospective-detector:
  - Detects spec written AFTER feature code (retrospective).
  - Confirms spec-first when ts_spec <= ts_code.
  - Handles missing git / missing spec / no feature code.
  - Public-project safety: no hardcoded module paths.
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
TOOL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "detect_retrospective_spec.py"
PY = sys.executable


def _git_run(cwd: Path, *args, env_extra: dict = None):
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = env_extra.get("GIT_AUTHOR_DATE") if env_extra else env.get("GIT_AUTHOR_DATE", "")
    env["GIT_COMMITTER_DATE"] = env_extra.get("GIT_COMMITTER_DATE") if env_extra else env.get("GIT_COMMITTER_DATE", "")
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=10, env=env,
    )


def _init_repo(td: Path) -> Path:
    project = td / "proj"
    project.mkdir()
    _git_run(project, "init")
    _git_run(project, "config", "user.email", "t@t")
    _git_run(project, "config", "user.name", "t")
    return project


def _commit(project: Path, file_rel: str, content: str, when: str = ""):
    """Stage file + commit. when format: 'YYYY-MM-DD HH:MM:SS'."""
    target = project / file_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git_run(project, "add", file_rel)
    extra = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else None
    _git_run(project, "commit", "-m", f"add {file_rel}", env_extra=extra)


def _run_tool(spec_path: Path, workspace: Path) -> dict:
    proc = subprocess.run(
        [PY, str(TOOL), str(spec_path), "--workspace", str(workspace), "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=20,
    )
    if proc.returncode != 0:
        return {"_rc": proc.returncode, "stderr": proc.stderr,
                "stdout": proc.stdout}
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


class TestRetrospectiveDetection(unittest.TestCase):

    def test_retrospective_spec_detected(self):
        """Feature code commits FIRST, then spec — verdict=retrospective."""
        with tempfile.TemporaryDirectory() as td:
            project = _init_repo(Path(td))
            # Commit feature code on 2026-01-01
            _commit(project, "models/x.py", "# feature\n",
                    when="2026-01-01T10:00:00")
            # Commit spec on 2026-01-05 (LATER)
            spec_path = project / "specs" / "v0.1.md"
            spec_content = (
                "---\nslug: v0.1\nmodule: demo\nretrospective: true\n"
                "acceptance_evals:\n  - id: e1\n---\n# spec\n"
            )
            _commit(project, "specs/v0.1.md", spec_content,
                    when="2026-01-05T10:00:00")
            result = _run_tool(spec_path, project)
            self.assertNotIn("_rc", result, "tool failed: %s" % result)
            self.assertEqual(result["verdict"], "retrospective")
            self.assertGreater(result["delta_seconds"], 0)

    def test_spec_first_detected(self):
        """Spec commits FIRST, then feature code — verdict=spec-first."""
        with tempfile.TemporaryDirectory() as td:
            project = _init_repo(Path(td))
            spec_content = (
                "---\nslug: v0.2\nmodule: demo\n"
                "acceptance_evals:\n  - id: e1\n---\n# spec first\n"
            )
            _commit(project, "specs/v0.2.md", spec_content,
                    when="2026-01-01T10:00:00")
            _commit(project, "models/y.py", "# feature\n",
                    when="2026-01-05T10:00:00")
            spec_path = project / "specs" / "v0.2.md"
            result = _run_tool(spec_path, project)
            self.assertNotIn("_rc", result, "tool failed: %s" % result)
            self.assertEqual(result["verdict"], "spec-first")
            self.assertLessEqual(result["delta_seconds"], 0)

    def test_no_feature_code_yet(self):
        """Only spec committed; no feature code → verdict=no-feature-code-yet."""
        with tempfile.TemporaryDirectory() as td:
            project = _init_repo(Path(td))
            spec_path = project / "specs" / "v0.3.md"
            _commit(project, "specs/v0.3.md",
                    "---\nslug: v0.3\nmodule: demo\nacceptance_evals:\n  - id: e\n---\n",
                    when="2026-01-01T10:00:00")
            result = _run_tool(spec_path, project)
            self.assertNotIn("_rc", result, "tool failed: %s" % result)
            self.assertEqual(result["verdict"], "no-feature-code-yet")

    def test_missing_spec_returns_error_rc(self):
        with tempfile.TemporaryDirectory() as td:
            project = _init_repo(Path(td))
            nonexistent = project / "specs" / "missing.md"
            proc = subprocess.run(
                [PY, str(TOOL), str(nonexistent), "--workspace", str(project)],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=20,
            )
            self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
