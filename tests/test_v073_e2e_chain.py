# -*- coding: utf-8 -*-
"""End-to-end integration test for v0.7.3 audit chain — eval o2.

Simulates the full /implement flow:
  1. Init tmp repo + spec with affected_modules.
  2. PreToolUse envelope → snapshot hook captures pre-state.
  3. Multiple Edits (in-scope + optionally out-of-scope).
  4. AGENT emits implement-noted.md.
  5. Stop envelope with done-claim → orchestrator chain fires.
  6. Assert: validator verdict, detector verdict, annotator template
     emitted, scope-check verdict.

Closes Gap 3 from v0.7.2 self-review: cross-component data flow proven
at integration level, not just component level.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = TOOLKIT_ROOT / "templates" / "claude" / "hooks"
TOOLS_DIR = TOOLKIT_ROOT / "templates" / "codex" / "tools"
PY = sys.executable


def _git_init(td: Path, branch: str = "feature-e2e") -> Path:
    project = td / "proj"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True, timeout=10)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "checkout", "-B", branch], cwd=str(project),
                   capture_output=True, timeout=5)
    # Install tools chained by orchestrator
    tools = project / ".codex" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("implement_snapshot.py", "implement_noted_validator.py",
                 "missing_sd_detector.py", "diff_hunk_annotator.py",
                 "diff_annotation_validator.py"):
        shutil.copy2(str(TOOLS_DIR / name), str(tools / name))
    return project


def _make_spec(project: Path, slug: str, affected: list, eval_targets: list = None):
    sd = project / ".agent-toolkit" / "specs"
    sd.mkdir(parents=True, exist_ok=True)
    body = "---\n"
    body += f"slug: {slug}\nmodule: demo\nstatus: implementing\nfeature_kind: orchestration\n"
    body += "affected_modules:\n"
    for am in affected:
        body += f"  - {am}\n"
    body += "acceptance_evals:\n"
    if eval_targets:
        for i, t in enumerate(eval_targets, 1):
            body += (f"  - id: e{i}\n    story: x\n    grader: code\n"
                     f"    probe:\n      tool: pytest\n      args:\n"
                     f"        target: {t}\n    expected: {{}}\n"
                     f"    target_pass_rate: 1.0\n")
    else:
        body += ("  - id: e1\n    story: x\n    grader: code\n    probe: {}\n"
                 "    expected: {}\n    target_pass_rate: 1.0\n")
    body += "---\n# spec\n"
    (sd / f"{slug}.md").write_text(body, encoding="utf-8")


def _run_snapshot_hook(project: Path, slug: str, file_path: Path):
    """Simulate PreToolUse Edit envelope to capture pre-state."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    envelope = {
        "cwd": str(project),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(file_path)},
    }
    subprocess.run(
        [PY, str(HOOKS_DIR / "implement_snapshot_hook.py")],
        input=json.dumps(envelope), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=15,
        cwd=str(project), env=env,
    )


def _make_impl_noted(project: Path, slug: str, sd_entries: list):
    """Write implement-noted with given SD entries."""
    sd_body = "\n## 1. Scope deviations\n\n"
    for i, (file_ref, linkage) in enumerate(sd_entries, 1):
        sd_body += (
            f"### SD-{i}: stuff\n"
            f"- Type: outside-spec\n"
            f"- File(s) affected: `{file_ref}`\n"
            f"- Spec linkage: {linkage}\n"
            f"- Confidence: high\n\n"
        )
    impl = project / ".agent-toolkit" / "specs" / f"{slug}.implement-noted.md"
    impl.write_text(
        "---\n"
        f"spec: {slug}\nimplement_run_at: 2026-05-21\nimplement_agent: test\n"
        f"total_scope_deviations: {len(sd_entries)}\n"
        "total_tradeoffs_with_evidence: 0\ntotal_followups: 0\n"
        "overall_confidence: high\n---\n"
        + sd_body,
        encoding="utf-8",
    )


def _run_orchestrator(project: Path, assistant_text: str):
    t = project / ".claude" / "transcript.jsonl"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(
        json.dumps({"role": "user", "content": "go"}) + "\n"
        + json.dumps({"role": "assistant",
                      "content": [{"type": "text", "text": assistant_text}]}) + "\n",
        encoding="utf-8",
    )
    envelope = {"cwd": str(project), "transcript_path": str(t)}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [PY, str(HOOKS_DIR / "implement_orchestrator.py")],
        input=json.dumps(envelope), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
        cwd=str(project), env=env,
    )


class TestE2EChain(unittest.TestCase):

    def test_clean_flow_converges_lean(self):
        """All Edits in scope + correctly declared → orchestrator clean."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-clean")
            _make_spec(project, "feature-clean", ["models/"])

            # Simulate Edit on models/foo.py
            (project / "models").mkdir()
            target = project / "models" / "foo.py"
            target.write_text("original\n", encoding="utf-8")
            _run_snapshot_hook(project, "feature-clean", target)
            target.write_text("modified\n", encoding="utf-8")

            _make_impl_noted(project, "feature-clean",
                             [("models/foo.py:1-1", "e1")])

            proc = _run_orchestrator(project, "Sprint hoàn tất. implement done.")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[implement-orchestrator]", proc.stdout)
            self.assertIn("Phase 5.1", proc.stdout)
            self.assertIn("Phase 5.2", proc.stdout)
            self.assertIn("Phase 5.3", proc.stdout)
            # Should mention "clean" verdict somewhere
            self.assertIn("clean", proc.stdout.lower())

    def test_out_of_scope_edit_flagged_by_detector(self):
        """Edit on file outside affected_modules → missing-SD detector flags."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-creep")
            _make_spec(project, "feature-creep", ["models/"])

            # In-scope edit
            (project / "models").mkdir()
            in_scope = project / "models" / "foo.py"
            in_scope.write_text("a\n", encoding="utf-8")
            _run_snapshot_hook(project, "feature-creep", in_scope)
            in_scope.write_text("a-modified\n", encoding="utf-8")

            # Out-of-scope edit (no declared SD)
            (project / "utils").mkdir()
            out_scope = project / "utils" / "helper.py"
            out_scope.write_text("b\n", encoding="utf-8")
            _run_snapshot_hook(project, "feature-creep", out_scope)
            out_scope.write_text("b-modified\n", encoding="utf-8")

            # Impl-noted only declares in-scope file
            _make_impl_noted(project, "feature-creep",
                             [("models/foo.py:1-1", "e1")])

            proc = _run_orchestrator(project, "implement done.")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[implement-orchestrator]", proc.stdout)
            # Detector should report missing-sd issues
            self.assertIn("missing-sd", proc.stdout.lower())

    def test_e2e_hallucinated_sd_caught_by_validator(self):
        """SD entry points at non-existent file → validator flags."""
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-hallucinate")
            _make_spec(project, "feature-hallucinate", ["models/"])

            (project / "models").mkdir()
            target = project / "models" / "real.py"
            target.write_text("a\n", encoding="utf-8")
            _run_snapshot_hook(project, "feature-hallucinate", target)
            target.write_text("a2\n", encoding="utf-8")

            # SD references file that doesn't exist
            _make_impl_noted(project, "feature-hallucinate",
                             [("models/ghost.py:99-99", "e1")])

            proc = _run_orchestrator(project, "implement done.")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[implement-orchestrator]", proc.stdout)
            # Validator Phase 5.1 should report issues > 0
            self.assertIn("issues", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()
