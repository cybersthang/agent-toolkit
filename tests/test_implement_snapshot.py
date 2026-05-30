# -*- coding: utf-8 -*-
"""Tests for implement_snapshot.py — pre-implement state capture.

Covers eval s2-snapshot-create-restore from spec
v0.7.2-comprehensive-scope-audit.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
TOOL = TOOLKIT_ROOT / "templates" / "codex" / "tools" / "implement_snapshot.py"


def _load():
    spec = importlib.util.spec_from_file_location("_isnap", str(TOOL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSnapshotCreateRestore(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        # Seed a file
        (self.workspace / "models").mkdir()
        self.target = self.workspace / "models" / "foo.py"
        self.target.write_text("original content\n", encoding="utf-8")

    def test_snapshot_create_captures_pre_state(self):
        ok = self.mod.snapshot_create("test-slug",
                                       ["models/foo.py"], self.workspace)
        self.assertTrue(ok)
        manifest = self.mod._load_manifest(self.workspace, "test-slug")
        self.assertIn("models/foo.py", manifest["files"])
        entry = manifest["files"]["models/foo.py"]
        self.assertEqual(entry["type"], "pre-edit")
        self.assertTrue(entry.get("hash"))

    def test_snapshot_create_idempotent_preserves_earliest(self):
        self.mod.snapshot_create("slug", ["models/foo.py"], self.workspace)
        # Modify file then snapshot again
        self.target.write_text("modified content\n", encoding="utf-8")
        self.mod.snapshot_create("slug", ["models/foo.py"], self.workspace)
        snap_path = self.workspace / ".agent-toolkit/.implement_snapshots/slug/models/foo.py"
        content = snap_path.read_text(encoding="utf-8")
        # Original content preserved
        self.assertEqual(content, "original content\n")

    def test_snapshot_create_net_new_file(self):
        # File doesn't exist yet
        ok = self.mod.snapshot_create("slug", ["models/new.py"], self.workspace)
        self.assertTrue(ok)
        manifest = self.mod._load_manifest(self.workspace, "slug")
        entry = manifest["files"]["models/new.py"]
        self.assertEqual(entry["type"], "net-new")

    def test_snapshot_diff_filelist_detects_modification(self):
        self.mod.snapshot_create("slug", ["models/foo.py"], self.workspace)
        self.target.write_text("changed!\n", encoding="utf-8")
        diffs = self.mod.snapshot_diff_filelist("slug", self.workspace)
        self.assertIn("models/foo.py", diffs)

    def test_snapshot_diff_filelist_clean_when_unchanged(self):
        self.mod.snapshot_create("slug", ["models/foo.py"], self.workspace)
        diffs = self.mod.snapshot_diff_filelist("slug", self.workspace)
        self.assertEqual(diffs, [])

    def test_snapshot_restore_returns_to_baseline(self):
        self.mod.snapshot_create("slug", ["models/foo.py"], self.workspace)
        self.target.write_text("messy\n", encoding="utf-8")
        ok = self.mod.snapshot_restore("slug", "models/foo.py", self.workspace)
        self.assertTrue(ok)
        self.assertEqual(self.target.read_text(encoding="utf-8"),
                         "original content\n")

    def test_snapshot_cleanup_force(self):
        self.mod.snapshot_create("slug", ["models/foo.py"], self.workspace)
        sd = self.workspace / ".agent-toolkit/.implement_snapshots/slug"
        self.assertTrue(sd.exists())
        ok = self.mod.snapshot_cleanup("slug", self.workspace, force=True)
        self.assertTrue(ok)
        self.assertFalse(sd.exists())


if __name__ == "__main__":
    unittest.main()
