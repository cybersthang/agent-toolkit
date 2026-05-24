#!/usr/bin/env python
"""PreToolUse hook — soft-warn when a `def <name>` being written already
exists in the workspace (function-duplication probe).

Goal: nudge AI to grep before writing, so the same logic doesn't get
re-implemented under a different name. NEVER blocks — just emits a
warn block with `path:line` citations of existing matches.

Scope:
  - Python `.py` files only (regex-based grep)
  - Skips test files (`tests/**`, `test_*.py`) — tests can dup intentionally
  - Skips `_private` functions (low reuse value)
  - Caps citations at 3 (avoid spam on generic names like `get` / `init`)

Fails open: any error → exit 0 silent.
Honors `AGENT_TOOLKIT_DISABLE=1`.

v0.12.0 — closes "reuse hàm có sẵn" gap (HE Dim 11 modularity).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import wrap_utf8_stdio, run_main_safe, emit_fire_event  # noqa: E402

wrap_utf8_stdio()


DEF_PATTERN = re.compile(r"^def ([A-Za-z][A-Za-z0-9_]*)\b", re.MULTILINE)
CLASS_PATTERN = re.compile(r"^class ([A-Z][A-Za-z0-9_]*)\b", re.MULTILINE)
MAX_CITATIONS_PER_NAME = 3
MAX_NAMES_REPORTED = 5


def _exit_allow() -> None:
    sys.exit(0)


def _is_test_path(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    if any(p in ("tests", "test", "__tests__") for p in parts):
        return True
    last = parts[-1]
    return last.startswith("test_") or last.endswith("_test.py")


def _extract_new_definitions(content: str) -> List[Tuple[str, str]]:
    """Return list of (kind, name) for non-private top-level def/class in content."""
    found: List[Tuple[str, str]] = []
    for m in DEF_PATTERN.finditer(content):
        name = m.group(1)
        if not name.startswith("_"):
            found.append(("def", name))
    for m in CLASS_PATTERN.finditer(content):
        name = m.group(1)
        if not name.startswith("_"):
            found.append(("class", name))
    return found


def _grep_workspace(workspace: Path, kind: str, name: str,
                    exclude: Path) -> List[Tuple[str, int]]:
    """Return list of (relpath, line_no) where ^def <name> / ^class <name>
    appears in workspace .py files (excluding the file being written).

    Caps at MAX_CITATIONS_PER_NAME. Uses simple line scan — fast enough for
    workspaces < 5k files.
    """
    citations: List[Tuple[str, int]] = []
    pattern = re.compile(rf"^{kind} {re.escape(name)}\b")
    excluded_resolved: Optional[Path]
    try:
        excluded_resolved = exclude.resolve()
    except OSError:
        excluded_resolved = None
    # Stack-agnostic default skip set. Framework-specific dirs (e.g.
    # `.odoo_data`, `.django_cache`) should be added by the project to
    # `.agent-toolkit/reuse_probe.json`'s `extra_skip_dirs` field — kept
    # out of this hardcoded set so toolkit core stays stack-neutral.
    skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__",
                 ".cache", ".pytest_cache", "build", "dist"}
    _config_path = workspace / ".agent-toolkit" / "reuse_probe.json"
    if _config_path.exists():
        try:
            _cfg = json.loads(_config_path.read_text(encoding="utf-8-sig"))
            extra = _cfg.get("extra_skip_dirs") or []
            if isinstance(extra, list):
                skip_dirs.update(str(d) for d in extra)
        except (json.JSONDecodeError, OSError):
            pass
    for py_file in workspace.rglob("*.py"):
        if any(part in skip_dirs for part in py_file.parts):
            continue
        try:
            if excluded_resolved is not None and py_file.resolve() == excluded_resolved:
                continue
        except OSError:
            pass
        try:
            with py_file.open("r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if pattern.match(line):
                        try:
                            rel = str(py_file.relative_to(workspace)).replace("\\", "/")
                        except ValueError:
                            rel = str(py_file)
                        citations.append((rel, i))
                        if len(citations) >= MAX_CITATIONS_PER_NAME:
                            return citations
                        break  # one match per file is enough
        except OSError:
            continue
    return citations


def _extract_target_path_and_content(envelope: dict) -> Tuple[Optional[str], str]:
    """Return (file_path, new_content_added) for Write/Edit/MultiEdit envelopes.

    For Edit: returns the new_string portion (additions only).
    For Write: returns full content.
    For MultiEdit: concatenates all new_string portions.
    """
    tool_name = envelope.get("tool_name") or ""
    tool_input = envelope.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if tool_name == "Write":
        return file_path, tool_input.get("content") or ""
    if tool_name == "Edit":
        return file_path, tool_input.get("new_string") or ""
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits") or []
        parts = []
        for e in edits:
            if isinstance(e, dict):
                parts.append(e.get("new_string") or "")
        return file_path, "\n".join(parts)
    return file_path, ""


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_allow()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_allow()
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_allow()

    file_path_str, new_content = _extract_target_path_and_content(envelope)
    if not file_path_str or not new_content:
        _exit_allow()
    file_path = Path(file_path_str)
    if file_path.suffix != ".py":
        _exit_allow()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    # Skip test files — tests duplicate intentionally for isolation.
    try:
        rel_target = str(file_path.resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel_target = str(file_path).replace("\\", "/")
    if _is_test_path(rel_target):
        _exit_allow()

    new_defs = _extract_new_definitions(new_content)
    if not new_defs:
        _exit_allow()

    # For Edit, the new_string may carry definitions that already exist in the
    # SAME file (e.g. user is moving/refactoring). Skip names that appear in
    # the existing file content too.
    same_file_existing: set = set()
    if file_path.exists():
        try:
            existing_src = file_path.read_text(encoding="utf-8", errors="replace")
            for m in DEF_PATTERN.finditer(existing_src):
                same_file_existing.add(("def", m.group(1)))
            for m in CLASS_PATTERN.finditer(existing_src):
                same_file_existing.add(("class", m.group(1)))
        except OSError:
            pass
    new_defs_filtered = [(k, n) for (k, n) in new_defs if (k, n) not in same_file_existing]
    if not new_defs_filtered:
        _exit_allow()

    findings: List[Tuple[str, str, List[Tuple[str, int]]]] = []
    for kind, name in new_defs_filtered[:MAX_NAMES_REPORTED]:
        hits = _grep_workspace(workspace, kind, name, file_path)
        if hits:
            findings.append((kind, name, hits))

    if not findings:
        try:
            emit_fire_event("reuse_probe.py", verdict="allow")
        except Exception:
            pass
        _exit_allow()

    try:
        emit_fire_event("reuse_probe.py", verdict="warn",
                        detail=f"{len(findings)} dup candidate(s)")
    except Exception:
        pass

    lines = [
        "[reuse-probe] Found existing implementations with matching names:",
        "",
    ]
    for kind, name, hits in findings:
        lines.append(f"  `{kind} {name}` — already defined at:")
        for relpath, line_no in hits:
            lines.append(f"    - {relpath}:{line_no}")
    lines.extend([
        "",
        "Before adding the new definition, decide ONE of:",
        "  (a) **Reuse** — call the existing function instead.",
        "  (b) **Extend** — add a parameter to the existing function.",
        "  (c) **Rewrite** — explain in your response why the existing is wrong.",
        "",
        "If this name collision is intentional (e.g. per-module helper with a",
        "common name like `parse` / `init`), proceed and ignore this warning.",
        "Skill `reuse-first-then-write` describes the 3-step probe.",
    ])
    message = "\n".join(lines)

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
