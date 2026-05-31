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

# v0.34 T5 (F2.1): a sidecar must contain the 4 required sections to satisfy the
# gate (presence, not length). Minimal-but-complete fixtures for "valid" cases.
_VALID_MD_NOTES = (
    "---\nspec: feature-foo\n---\n# Implement notes\n\n"
    "## 1. Scope deviations\nNone\n\n"
    "## 2. In-transcript trade-offs\nNone\n\n"
    "## 3. Open follow-ups\nNone\n\n"
    "## 4. Confidence summary\nhigh\n"
)
_VALID_HTML_NOTES = (
    "<html><body>\n"
    "<h2>§1 Scope deviations</h2>\n"
    "<h2>§2 In-transcript trade-offs</h2>\n"
    "<h2>§3 Open follow-ups</h2>\n"
    "<h2>§4 Confidence summary</h2>\n"
    "</body></html>\n"
)


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
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_no_op_when_no_spec_for_branch(self):
        """Branch has no matching spec → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-unknown")
            t = _make_transcript(project, "Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_no_op_when_on_main_branch(self):
        """Trunk branch (main/master) is exempt → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="main")
            _make_spec(project, "main")
            t = _make_transcript(project, "Implement done all features.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

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
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_no_op_when_file_already_exists(self):
        """Implement-noted file exists alongside spec → silent."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            spec = _make_spec(project, "feature-foo")
            notes = spec.parent / "feature-foo.implement-noted.md"
            notes.write_text(_VALID_MD_NOTES, encoding="utf-8")
            t = _make_transcript(project, "Sprint hoàn tất. Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_fail_open_on_empty_stdin(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            proc = subprocess.run(
                [PY, str(HOOK)], input="", capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=15, cwd=str(project),
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

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
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_fail_open_on_missing_transcript(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            envelope = {"cwd": str(project),
                        "transcript_path": str(project / "does-not-exist.jsonl")}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")


# ============================================================
# v0.18 — output_format aware validator
# ============================================================
class TestOutputFormatHtmlBoth(unittest.TestCase):
    """v0.18: hook respects `output_format: html | both` in
    `.agent-toolkit/implement_notes.json` — checks for `.html` sidecar
    alongside (or instead of) `.md`."""

    def _write_config(self, project: Path, output_format: str) -> None:
        cfg = project / ".agent-toolkit" / "implement_notes.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({
            "auto_emit": True,
            "output_format": output_format,
            "enforce": "warn",
        }), encoding="utf-8")

    def test_output_format_html_only_checks_html(self):
        """`output_format: html` → hook expects .html, not .md."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            spec = _make_spec(project, "feature-foo")
            self._write_config(project, "html")
            # Create MD only (HTML missing) — hook should still warn.
            md_sidecar = spec.parent / f"{spec.stem}.implement-noted.md"
            md_sidecar.write_text("# placeholder", encoding="utf-8")
            t = _make_transcript(project, "Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn(".implement-noted.html", proc.stdout)

    def test_output_format_both_checks_both(self):
        """`output_format: both` → missing either file triggers warn."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            spec = _make_spec(project, "feature-foo")
            self._write_config(project, "both")
            # Create only MD; HTML missing.
            md_sidecar = spec.parent / f"{spec.stem}.implement-noted.md"
            md_sidecar.write_text("# placeholder", encoding="utf-8")
            t = _make_transcript(project, "Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            # warn surfaces missing HTML
            self.assertIn(".implement-noted.html", proc.stdout)

    def test_output_format_both_satisfied_when_all_present(self):
        """Both files present → no warn."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            spec = _make_spec(project, "feature-foo")
            self._write_config(project, "both")
            md_sidecar = spec.parent / f"{spec.stem}.implement-noted.md"
            html_sidecar = spec.parent / f"{spec.stem}.implement-noted.html"
            md_sidecar.write_text(_VALID_MD_NOTES, encoding="utf-8")
            html_sidecar.write_text(_VALID_HTML_NOTES, encoding="utf-8")
            t = _make_transcript(project, "Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "",
                             f"expected silent allow, got: {proc.stdout!r}")

    def test_output_format_md_legacy_default(self):
        """No config file → legacy MD-only check (pre-v0.18 behavior)."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init_repo(Path(td), branch="feature-foo")
            spec = _make_spec(project, "feature-foo")
            # No .agent-toolkit/implement_notes.json — default `md` only.
            md_sidecar = spec.parent / f"{spec.stem}.implement-noted.md"
            md_sidecar.write_text(_VALID_MD_NOTES, encoding="utf-8")
            # HTML not present, but legacy behavior shouldn't care.
            t = _make_transcript(project, "Implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run_hook(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "",
                             "legacy default should accept MD-only")


# ============================================================
# v0.34 T5 (F2.1) — content validation: empty / section-incomplete sidecar
# ============================================================
class TestSidecarContentValidation(unittest.TestCase):
    """A sidecar that EXISTS but is empty / section-incomplete is rejected like a
    missing one (presence of the 4 sections, not length)."""

    def _setup(self, td, md_content=None):
        project = _git_init_repo(Path(td), branch="feature-foo")
        spec = _make_spec(project, "feature-foo")
        md = spec.parent / "feature-foo.implement-noted.md"
        if md_content is not None:
            md.write_text(md_content, encoding="utf-8")
        t = _make_transcript(project, "Implement done.")
        return project, t, md

    def test_empty_sidecar_warns(self):
        with tempfile.TemporaryDirectory() as td:
            project, t, _ = self._setup(td, md_content="")
            proc = _run_hook({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[implement-notes-gate]", proc.stdout)

    def test_whitespace_only_sidecar_warns(self):
        with tempfile.TemporaryDirectory() as td:
            project, t, _ = self._setup(td, md_content="   \n\t\n")
            proc = _run_hook({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertIn("[implement-notes-gate]", proc.stdout)

    def test_section_missing_sidecar_warns(self):
        # 3 of 4 sections (no Confidence summary) → flagged + names the missing one.
        partial = (
            "# notes\n## 1. Scope deviations\nNone\n"
            "## 2. In-transcript trade-offs\nNone\n"
            "## 3. Open follow-ups\nNone\n"
        )
        with tempfile.TemporaryDirectory() as td:
            project, t, _ = self._setup(td, md_content=partial)
            proc = _run_hook({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertIn("[implement-notes-gate]", proc.stdout)
            self.assertIn("Confidence summary", proc.stdout)

    def test_complete_minimal_sidecar_silent(self):
        with tempfile.TemporaryDirectory() as td:
            project, t, _ = self._setup(td, md_content=_VALID_MD_NOTES)
            proc = _run_hook({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertEqual((proc.stdout or "").strip(), "",
                             f"expected silent, got: {proc.stdout!r}")

    def test_empty_sidecar_blocks_under_enforce(self):
        # F2.1 acceptance ev2: 0-byte sidecar + enforce:block → hard block.
        with tempfile.TemporaryDirectory() as td:
            project, t, _ = self._setup(td, md_content="")
            cfg = project / ".agent-toolkit" / "implement_notes.json"
            cfg.write_text(json.dumps({"enforce": "block"}), encoding="utf-8")
            proc = _run_hook({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertIn('"decision": "block"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
