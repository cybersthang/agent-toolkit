#!/usr/bin/env python
"""implement_snapshot — pre-implement state capture for Layer 5 scope audit.

Why this tool exists:
  AGENT does NOT commit (ADR-002 hard-stop). So "diff vs pre-implement
  state" can't use git operations. Instead we keep a snapshot directory
  under `.agent-toolkit/.implement_snapshots/<slug>/` that mirrors the
  pre-Edit content of every feature-scope file touched during a
  `/implement <slug>` session.

Primitives:
  - snapshot_create(slug, files, workspace): on first Edit of feature-
    scope file, copy original content into snapshot dir + manifest.
  - snapshot_restore(slug, file_rel, workspace): restore single file from
    snapshot (used by /verify failure recovery, NOT by AGENT alone).
  - snapshot_diff_filelist(slug, workspace): return list of files that
    have been modified since snapshot (i.e. AGENT-touched paths).
  - snapshot_cleanup(slug, workspace): remove snapshot after /verify pass
    OR after TTL (default 7 days).

Public-project safe:
  - No hardcoded stack/project names.
  - Tool fail-open: every error path returns False/empty instead of
    raising. Layer 5 sees missing snapshot → skip scope check (warn).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


SNAPSHOT_REL = ".agent-toolkit/.implement_snapshots"
DEFAULT_TTL_DAYS = 7


def _snapshot_dir(workspace: Path, slug: str) -> Path:
    return workspace / SNAPSHOT_REL / slug


def _manifest_path(workspace: Path, slug: str) -> Path:
    return _snapshot_dir(workspace, slug) / "_manifest.json"


def _load_manifest(workspace: Path, slug: str) -> Dict[str, Any]:
    p = _manifest_path(workspace, slug)
    if not p.exists():
        return {"slug": slug, "created_at": int(time.time()), "files": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"slug": slug, "created_at": int(time.time()), "files": {}}


def _save_manifest(workspace: Path, slug: str, manifest: Dict[str, Any]) -> None:
    try:
        p = _manifest_path(workspace, slug)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _hash_file(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def snapshot_create(slug: str, files: List[str], workspace: Path) -> bool:
    """Snapshot each file in `files` (workspace-relative paths) into the
    slug's snapshot dir. Idempotent: a file already snapshotted is
    skipped (preserves earliest-captured state).

    Returns True if at least one new file was captured."""
    if not slug or not files:
        return False
    sd = _snapshot_dir(workspace, slug)
    try:
        sd.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    manifest = _load_manifest(workspace, slug)
    captured = manifest.setdefault("files", {})
    captured_now = False

    for rel in files:
        rel_norm = rel.replace("\\", "/")
        src = workspace / rel
        if rel_norm in captured:
            continue  # already snapshotted — preserve earliest
        try:
            if not src.exists():
                # File created by AGENT after /implement start → mark
                # "net-new" so scope check knows.
                captured[rel_norm] = {
                    "type": "net-new",
                    "captured_at": int(time.time()),
                }
                captured_now = True
                continue
            if not src.is_file():
                continue
            dst = sd / rel_norm
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            captured[rel_norm] = {
                "type": "pre-edit",
                "hash": _hash_file(src),
                "size": src.stat().st_size,
                "captured_at": int(time.time()),
            }
            captured_now = True
        except OSError:
            continue

    if captured_now:
        _save_manifest(workspace, slug, manifest)
    return captured_now


def snapshot_diff_filelist(slug: str, workspace: Path) -> List[str]:
    """Return list of workspace-relative file paths that differ from
    snapshot (hash mismatch) OR were marked net-new. Empty list when
    snapshot missing (treat as "no scope check applicable")."""
    manifest = _load_manifest(workspace, slug)
    files_map = manifest.get("files") or {}
    if not files_map:
        return []
    out: List[str] = []
    for rel, entry in files_map.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "net-new":
            current = workspace / rel
            if current.exists():
                out.append(rel)
            continue
        # pre-edit type — compare current hash with snapshot
        current = workspace / rel
        if not current.exists():
            out.append(rel)  # deleted
            continue
        cur_hash = _hash_file(current)
        if cur_hash and cur_hash != entry.get("hash"):
            out.append(rel)
    # Also detect NEW files that aren't in manifest but exist now and
    # could plausibly be AGENT-created. Caveat: any non-snapshot file
    # is invisible to this primitive — caller must declare scope via
    # snapshot_create (typically done via PreToolUse hook).
    return out


def snapshot_restore(slug: str, file_rel: str, workspace: Path) -> bool:
    """Restore a single file from snapshot. Returns True on success.

    For "net-new" entries (no pre-state), restore = delete the current
    file. Caller MUST verify post-restore consistency via tests."""
    manifest = _load_manifest(workspace, slug)
    files_map = manifest.get("files") or {}
    entry = files_map.get(file_rel.replace("\\", "/"))
    if not entry:
        return False
    sd = _snapshot_dir(workspace, slug)
    src = sd / file_rel
    dst = workspace / file_rel
    try:
        if entry.get("type") == "net-new":
            if dst.exists():
                dst.unlink()
            return True
        if not src.exists():
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return True
    except OSError:
        return False


def snapshot_cleanup(slug: str, workspace: Path, force: bool = False) -> bool:
    """Remove snapshot dir for `slug`. Honors TTL unless force=True."""
    sd = _snapshot_dir(workspace, slug)
    if not sd.exists():
        return True
    if not force:
        manifest = _load_manifest(workspace, slug)
        created = int(manifest.get("created_at") or 0)
        age_days = (time.time() - created) / 86400 if created else 999
        if age_days < DEFAULT_TTL_DAYS:
            return False
    try:
        shutil.rmtree(str(sd))
        return True
    except OSError:
        return False


def main(argv: List[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="implement-snapshot primitives")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("--slug", required=True)
    p_create.add_argument("--workspace", default=".")
    p_create.add_argument("--file", action="append", default=[])

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--slug", required=True)
    p_diff.add_argument("--workspace", default=".")

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("--slug", required=True)
    p_restore.add_argument("--file", required=True)
    p_restore.add_argument("--workspace", default=".")

    p_cleanup = sub.add_parser("cleanup")
    p_cleanup.add_argument("--slug", required=True)
    p_cleanup.add_argument("--workspace", default=".")
    p_cleanup.add_argument("--force", action="store_true")

    ns = ap.parse_args(argv[1:])
    workspace = Path(ns.workspace).resolve()

    if ns.cmd == "create":
        ok = snapshot_create(ns.slug, ns.file, workspace)
        print(json.dumps({"ok": ok, "files_captured": len(ns.file)},
                         ensure_ascii=False))
        return 0
    if ns.cmd == "diff":
        diffs = snapshot_diff_filelist(ns.slug, workspace)
        print(json.dumps({"modified_files": diffs}, ensure_ascii=False, indent=2))
        return 0
    if ns.cmd == "restore":
        ok = snapshot_restore(ns.slug, ns.file, workspace)
        print(json.dumps({"ok": ok}, ensure_ascii=False))
        return 0 if ok else 1
    if ns.cmd == "cleanup":
        ok = snapshot_cleanup(ns.slug, workspace, force=ns.force)
        print(json.dumps({"removed": ok}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
