# -*- coding: utf-8 -*-
"""Tests for implement_orchestrator.py — eval o1."""
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
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "implement_orchestrator.py"
TOOLS_DIR = TOOLKIT_ROOT / "templates" / "codex" / "tools"
PY = sys.executable


def _git_init(td: Path, branch: str = "feature-foo") -> Path:
    project = td / "proj"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True, timeout=10)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(project),
                   capture_output=True, timeout=5)
    subprocess.run(["git", "checkout", "-B", branch], cwd=str(project),
                   capture_output=True, timeout=5)
    # Install tools that orchestrator chains
    tools = project / ".codex" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("implement_snapshot.py", "implement_noted_validator.py",
                 "missing_sd_detector.py", "diff_hunk_annotator.py",
                 "diff_annotation_validator.py"):
        shutil.copy2(str(TOOLS_DIR / name), str(tools / name))
    return project


def _make_spec(project: Path, slug: str):
    sd = project / ".agent-toolkit" / "specs"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / f"{slug}.md").write_text(
        "---\n"
        f"slug: {slug}\nmodule: demo\nstatus: implementing\nfeature_kind: orchestration\n"
        "affected_modules:\n  - models/\n"
        "acceptance_evals:\n"
        "  - id: e1\n    story: x\n    grader: code\n    probe: {}\n"
        "    expected: {}\n    target_pass_rate: 1.0\n"
        "---\n# spec\n",
        encoding="utf-8",
    )


def _make_impl_noted(project: Path, slug: str, sd_files: list = None):
    sd_files = sd_files or []
    sd_section = "\n## 1. Scope deviations\n\n"
    for i, f in enumerate(sd_files, 1):
        sd_section += (
            f"### SD-{i}: stuff\n"
            f"- Type: outside-spec\n"
            f"- File(s) affected: `{f}`\n"
            f"- Spec linkage: e1\n"
            f"- Confidence: high\n\n"
        )
    impl = project / ".agent-toolkit" / "specs" / f"{slug}.implement-noted.md"
    impl.write_text(
        "---\n"
        f"spec: {slug}\nimplement_run_at: 2026-05-21\nimplement_agent: test\n"
        f"total_scope_deviations: {len(sd_files)}\n"
        "total_tradeoffs_with_evidence: 0\ntotal_followups: 0\n"
        "overall_confidence: high\n---\n"
        + sd_section,
        encoding="utf-8",
    )


def _install_stub_detector(project: Path, verdict: str, modified_count: int,
                           missing=None, fabricated=None) -> None:
    """Overwrite the project's missing_sd_detector with a stub `detect()` returning
    a fixed verdict — lets us drive the orchestrator's T6 block decision without a
    real git snapshot."""
    missing = missing or []
    fabricated = fabricated or []
    stub = (
        "def detect(slug, workspace):\n"
        f"    return {{'verdict': {verdict!r}, 'modified_count': {modified_count!r},\n"
        f"            'missing_files': {missing!r}, 'missing_count': {len(missing)},\n"
        f"            'fabricated_sd_files': {fabricated!r}, 'fabricated_sd_count': {len(fabricated)},\n"
        f"            'covered_count': 0, 'implement_noted_exists': True}}\n"
    )
    (project / ".codex" / "tools" / "missing_sd_detector.py").write_text(
        stub, encoding="utf-8")


def _set_enforce(project: Path, hook: str, mode: str) -> None:
    cfg = project / ".agent-toolkit" / "enforce_mode.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"per_hook": {hook: mode}}), encoding="utf-8")


def _make_transcript(project: Path, assistant_text: str) -> Path:
    t = project / ".claude" / "transcript.jsonl"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(
        json.dumps({"role": "user", "content": "go"}) + "\n"
        + json.dumps({"role": "assistant",
                      "content": [{"type": "text", "text": assistant_text}]}) + "\n",
        encoding="utf-8",
    )
    return t


def _run(envelope, cwd, timeout=30):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [PY, str(HOOK)],
        input=json.dumps(envelope, ensure_ascii=False),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout, cwd=str(cwd), env=env,
    )


class TestImplementOrchestrator(unittest.TestCase):

    def test_orchestrator_fires_on_done_claim(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            _make_impl_noted(project, "feature-foo")
            t = _make_transcript(project, "Sprint hoàn tất. implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("[implement-orchestrator]", proc.stdout)
            self.assertIn("Phase 5.1", proc.stdout)

    def test_no_op_when_no_done_claim(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            _make_impl_noted(project, "feature-foo")
            t = _make_transcript(project, "Đang phân tích spec.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_no_op_when_spec_lacks_affected_modules(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-foo")
            sd = project / ".agent-toolkit" / "specs"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "feature-foo.md").write_text(
                "---\nslug: feature-foo\nmodule: demo\n"
                "status: implementing\nfeature_kind: orchestration\n"
                "acceptance_evals:\n  - id: e1\n    story: x\n    grader: code\n"
                "    probe: {}\n    expected: {}\n    target_pass_rate: 1.0\n"
                "---\n# spec\n",
                encoding="utf-8",
            )
            _make_impl_noted(project, "feature-foo")
            t = _make_transcript(project, "implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_no_op_when_impl_noted_missing(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            # No implement-noted
            t = _make_transcript(project, "implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_bypass_marker_honored(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            _make_impl_noted(project, "feature-foo")
            t = _make_transcript(project,
                "implement done. orchestrator-skip: hotfix-only")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc = _run(envelope, project)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual((proc.stdout or "").strip(), "")

    def test_idempotent_within_ttl(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            _make_impl_noted(project, "feature-foo")
            t = _make_transcript(project, "implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}
            proc1 = _run(envelope, project)
            self.assertEqual(proc1.returncode, 0)
            self.assertIn("[implement-orchestrator]", proc1.stdout)
            # Second invocation immediately — should skip due to cache
            proc2 = _run(envelope, project)
            self.assertEqual(proc2.returncode, 0)
            self.assertEqual((proc2.stdout or "").strip(), "")


class TestCacheMtimeInvalidation(unittest.TestCase):
    """P3 v0.8.0: cache invalidated when impl-noted mtime changes."""

    def test_cache_invalidated_by_impl_noted_edit(self):
        with tempfile.TemporaryDirectory() as td:
            project = _git_init(Path(td), branch="feature-foo")
            _make_spec(project, "feature-foo")
            _make_impl_noted(project, "feature-foo")
            t = _make_transcript(project, "implement done.")
            envelope = {"cwd": str(project), "transcript_path": str(t)}

            # First invocation — orchestrator fires, caches
            proc1 = _run(envelope, project)
            self.assertEqual(proc1.returncode, 0)
            self.assertIn("[implement-orchestrator]", proc1.stdout)

            # Second immediate — cache HIT (no output)
            proc2 = _run(envelope, project)
            self.assertEqual((proc2.stdout or "").strip(), "")

            # Edit impl-noted → mtime changes → cache should invalidate
            import time as _t
            _t.sleep(1.1)  # ensure mtime advances at second granularity
            impl_noted = project / ".agent-toolkit" / "specs" / "feature-foo.implement-noted.md"
            text = impl_noted.read_text(encoding="utf-8")
            impl_noted.write_text(text + "\n# iter 2\n", encoding="utf-8")

            # Third invocation — cache invalidated, orchestrator re-fires
            proc3 = _run(envelope, project)
            self.assertEqual(proc3.returncode, 0)
            self.assertIn("[implement-orchestrator]", proc3.stdout,
                          "Cache should invalidate after impl-noted edit")


class TestOrchestratorBlock(unittest.TestCase):
    """v0.34 T6 (F2.2): honor enforce_mode → block on a positive, snapshot-backed
    scope-integrity problem; R4 degrade to warn when the snapshot is absent
    (modified_count==0)."""

    def _base(self, td):
        project = _git_init(Path(td), branch="feature-foo")
        _make_spec(project, "feature-foo")
        _make_impl_noted(project, "feature-foo", sd_files=[])  # 0 SD declared
        t = _make_transcript(project, "implement done.")
        return project, t

    def test_block_on_missing_sd_under_enforce(self):
        # ev2b: 0-SD declared + N modified (snapshot-backed) + enforce block → BLOCK.
        with tempfile.TemporaryDirectory() as td:
            project, t = self._base(td)
            _install_stub_detector(project, "missing-sd", 3,
                                   missing=["models/a.py", "models/b.py", "models/c.py"])
            _set_enforce(project, "implement_orchestrator", "block")
            proc = _run({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertEqual(proc.returncode, 0)
            self.assertIn('"decision": "block"', proc.stdout)

    def test_no_block_missing_sd_default_warn(self):
        # Same finding but DEFAULT (warn) install → advisory only, never blocks.
        with tempfile.TemporaryDirectory() as td:
            project, t = self._base(td)
            _install_stub_detector(project, "missing-sd", 3, missing=["models/a.py"])
            proc = _run({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn('"decision": "block"', proc.stdout)
            self.assertIn("[implement-orchestrator]", proc.stdout)

    def test_r4_no_block_when_snapshot_absent(self):
        # R4: fabricated-sd verdict with modified_count==0 = no snapshot data →
        # MUST degrade to warn (the verdict is a false positive there), even under enforce.
        with tempfile.TemporaryDirectory() as td:
            project, t = self._base(td)
            _install_stub_detector(project, "fabricated-sd", 0,
                                   fabricated=["models/ghost.py"])
            _set_enforce(project, "implement_orchestrator", "block")
            proc = _run({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn('"decision": "block"', proc.stdout)

    def test_block_not_cached_refires_on_restop(self):
        # A block must NOT be cached away — re-Stop within TTL (same impl-noted)
        # must re-block, else the agent evades it by simply stopping again.
        with tempfile.TemporaryDirectory() as td:
            project, t = self._base(td)
            _install_stub_detector(project, "missing-sd", 2,
                                   missing=["models/a.py", "models/b.py"])
            _set_enforce(project, "implement_orchestrator", "block")
            proc1 = _run({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertIn('"decision": "block"', proc1.stdout)
            proc2 = _run({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertIn('"decision": "block"', proc2.stdout,
                          "block must re-fire on re-Stop, not be cached away")

    def test_block_mode_bypasses_stale_clean_cache(self):
        # review round-1 HIGH: turn-1 clean (cached) then turn-2 dirty WITHOUT an
        # impl-noted edit must still block under block mode (cache read is skipped).
        with tempfile.TemporaryDirectory() as td:
            project, t = self._base(td)
            _set_enforce(project, "implement_orchestrator", "block")
            # Turn 1: detector clean → no block, writes a clean cache entry.
            _install_stub_detector(project, "clean", 2)
            proc1 = _run({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertNotIn('"decision": "block"', proc1.stdout)
            # Turn 2 (same impl-noted mtime, within TTL): source now mismatches →
            # detector returns missing-sd. The stale CLEAN cache must NOT suppress it.
            _install_stub_detector(project, "missing-sd", 2,
                                   missing=["models/a.py", "models/b.py"])
            proc2 = _run({"cwd": str(project), "transcript_path": str(t)}, project)
            self.assertIn('"decision": "block"', proc2.stdout,
                          "stale clean cache must not suppress a block under block mode")


if __name__ == "__main__":
    unittest.main()
