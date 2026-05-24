# -*- coding: utf-8 -*-
"""Tests for implement_notes_gate Stop hook (eval i4).

Covers the 5 main contract points:
  - warn on done-claim without implement-noted file
  - no-op when assistant text has no done-claim
  - no-op when no spec exists for current branch
  - bypass marker `implement-notes: skip <reason>` honored
  - fail-open on malformed envelope / missing transcript
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
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "implement_notes_gate.py"
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
    return project


def _make_spec(project: Path, slug: str) -> Path:
    specs_dir = project / ".agent-toolkit" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    spec = specs_dir / f"{slug}.md"
    spec.write_text(
        "---\n"
        f"slug: {slug}\n"
        f"branch: {slug}\n"
        "feature_kind: orchestration\n"
        "acceptance_evals:\n"
        "  - id: e1-test\n"
        "    story: do something\n"
        "---\n\n# Spec\n",
        encoding="utf-8",
    )
    return spec


def _make_transcript(project: Path, assistant_text: str) -> Path:
    """Write a JSONL transcript with 1 user msg + 1 assistant msg."""
    t_path = project / ".claude" / "transcript.jsonl"
    t_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"role": "user", "content": "do work"}, ensure_ascii=False),
        json.dumps({
            "role": "assistant",
            "content": [{"type": "text", "text": assistant_text}],
        }, ensure_ascii=False),
    ]
    t_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return t_path


def _run_hook(envelope: dict, cwd: Path,
              timeout: int = 15) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope, ensure_ascii=False),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=str(cwd), env=env,
    )


class TestImplementNotesGate(unittest.TestCase):

    def test_warn_on_done_claim_without_file(self):
        """g4a — done claim + no implement-noted file → warn emitted."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            t = _make_transcript(project,
                "Sprint v0.6.2 hoàn tất. Implement done all 10 evals.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[implement-notes-gate]", proc.stdout)
            self.assertIn("feature-foo", proc.stdout)
            self.assertIn("implement-noted.md", proc.stdout)

    def test_no_op_when_no_done_claim(self):
        """No done claim → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            t = _make_transcript(project,
                "Đang phân tích spec; chưa implement.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_no_op_when_no_spec_for_branch(self):
        """Branch has no matching spec → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-unknown")
            t = _make_transcript(project, "Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_no_op_when_on_main_branch(self):
        """Trunk branch (main/master) is exempt → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="main")
            _make_spec(project, "main")
            t = _make_transcript(project, "Implement done all features.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_bypass_marker_honored(self):
        """`implement-notes: skip <reason>` in assistant text → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            t = _make_transcript(project,
                "Implement done; tuy nhiên đây chỉ là typo fix. "
                "implement-notes: skip typo-only-edit")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_no_op_when_file_already_exists(self):
        """Implement-noted file exists alongside spec → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            spec = _make_spec(project, "feature-foo")
            notes = spec.parent / "feature-foo.implement-noted.md"
            notes.write_text(
                "---\nspec: feature-foo\n---\n# implement notes\n",
                encoding="utf-8",
            )
            t = _make_transcript(project, "Sprint hoàn tất. Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_fail_open_on_empty_stdin(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            proc = subprocess.run(
                [PY, str(HOOK)], input="", capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=15, cwd=str(project),
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_fail_open_on_malformed_json(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            proc = subprocess.run(
                [PY, str(HOOK)], input="{not valid",
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=15, cwd=str(project),
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_fail_open_on_missing_transcript(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            envelope = {"cwd": str(project),
                        "transcript_path": str(project / "does-not-exist.jsonl")}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
