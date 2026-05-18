"""Shared utilities for `.claude/hooks/*.py`.

Centralizes patterns that were duplicated across 8 hooks before the
2026-05-18 refactor:

- UTF-8 stdin/stdout wrapping (Windows safety).
- Atomic JSON write (temp + os.replace) — fixes TOCTOU race between
  parallel PostToolUse hooks each updating their own state cache.
- Workspace-relative glob matching with `**` support — fnmatch alone
  doesn't handle recursive wildcards correctly.
- Workspace-root discovery — walk up from `cwd` looking for
  `.agent-toolkit/specs`.
- MCP prefix discovery — fall back to scanning `.mcp.json` when the
  static config in `.agent-toolkit/verification.json` is a generic
  placeholder. Lets the toolkit drop project-specific defaults.

The hooks all start with the snippet below (NOT a function, since `sys`
needs to be wrapped at module init time before stdin is read):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from _common import wrap_utf8_stdio, atomic_write_json, match_glob, ...
    wrap_utf8_stdio()

Toolkit-invariant: this module ships from agent-toolkit; project-specific
data lives in `.agent-toolkit/*.json` and `.codex/canonical_decisions.json`.
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def wrap_utf8_stdio() -> None:
    """Wrap stdin/stdout as UTF-8 so Vietnamese / non-Latin text survives
    on Windows (default cp1252) and broken locales."""
    if hasattr(sys.stdin, "buffer"):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8",
                                     errors="replace")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")


def atomic_write_json(path: Path, data: Any) -> bool:
    """Atomic JSON write via temp file + os.replace.

    Concurrent PostToolUse hooks (3 fire in parallel) each maintain their
    own state cache. Without atomic write, `path.write_text` can interleave
    between read and write, corrupting the JSON file. `os.replace` is
    atomic on POSIX and Windows (≥ Vista). Worst case: last writer wins;
    file is never corrupted.

    Returns True on success, False on any IO error (fail-open).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Use NamedTemporaryFile in same dir so os.replace stays on same FS.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False,
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp",
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, str(path))
        return True
    except OSError:
        # Clean up temp file if rename failed.
        try:
            os.unlink(tmp_path)  # type: ignore[name-defined]
        except (OSError, NameError):
            pass
        return False


def match_glob(
    file_path: str,
    globs: Iterable[str],
    workspace: Path,
    empty_returns: bool = True,
) -> bool:
    """True if `file_path` matches any glob in `globs`.

    Handles both workspace-relative and absolute paths. Empty/missing
    globs default to "applies to all" (`empty_returns=True`) — set to
    False for callers that want "no globs = don't match".

    Adds lenient `**` matching since `fnmatch.fnmatch` only supports
    shell-style wildcards.
    """
    globs = list(globs or [])
    if not globs:
        return empty_returns
    try:
        rel = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel = file_path.replace("\\", "/")
    abs_path = file_path.replace("\\", "/")
    for pattern in globs:
        pat = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(abs_path, pat):
            return True
        if "**" in pat:
            head = pat.split("**", 1)[0].rstrip("/")
            tail = pat.split("**", 1)[1].lstrip("/")
            if (not head or rel.startswith(head)) and (
                not tail or rel.endswith(tail.lstrip("*").lstrip("/"))
            ):
                return True
    return False


def find_workspace_root(start: Path) -> Optional[Path]:
    """Walk up from `start` looking for a directory containing
    `.agent-toolkit/specs` (the canonical toolkit marker). Returns the
    first such directory, or None if not found."""
    cursor = start.resolve()
    while True:
        if (cursor / ".agent-toolkit" / "specs").is_dir():
            return cursor
        if cursor.parent == cursor:
            return None
        cursor = cursor.parent


def discover_mcp_prefix(
    workspace: Path,
    config_value: Optional[str] = None,
    exclude_servers: Iterable[str] = ("playwright",),
) -> str:
    """Discover the MCP tool-name prefix for the current project.

    Order of preference:
    1. `config_value` if it's a concrete prefix (not a placeholder /
       generic default).
    2. First MCP server declared in `.mcp.json` (excluding generic ones
       like `playwright` that ship cross-project).
    3. Fall back to `mcp__` (matches any MCP tool — broadest).

    Returns the prefix string ending with `__`.
    """
    # 1. Trust explicit config if it doesn't look like a placeholder.
    if config_value:
        cfg = config_value.strip()
        # Placeholder shapes we should not trust.
        placeholders = ("<", "{{", "${", "mcp__<", "PROJECT-STACK")
        if cfg.endswith("__") and not any(p in cfg for p in placeholders):
            return cfg

    # 2. Scan `.mcp.json` for the first stdio server name.
    mcp_path = workspace / ".mcp.json"
    if mcp_path.exists():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers") if isinstance(data, dict) else None
            if isinstance(servers, dict):
                for name in servers:
                    if name in exclude_servers:
                        continue
                    if isinstance(name, str) and name.strip():
                        return f"mcp__{name}__"
        except (OSError, json.JSONDecodeError):
            pass

    # 3. Last resort: broad prefix.
    return "mcp__"


def emit_post_tool_context(text: str) -> None:
    """PostToolUse hook stdout envelope. Exits 0 after print."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def emit_stop_context(text: str) -> None:
    """Stop hook stdout envelope (non-blocking warning)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def emit_stop_block(reason: str) -> None:
    """Stop hook block envelope. Exits 0 after print."""
    print(json.dumps({"decision": "block", "reason": reason},
                     ensure_ascii=False))
    sys.exit(0)


def read_jsonl_transcript(path: Path) -> List[Dict[str, Any]]:
    """Parse a JSONL transcript file. Lines that fail JSON parse are
    silently skipped (Claude Code occasionally writes partial lines)."""
    out: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def split_current_turn(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return messages from the most-recent user prompt to the end.
    If no user message found, returns all messages."""
    last_user = -1
    for idx in range(len(messages) - 1, -1, -1):
        m = messages[idx]
        if m.get("type") == "user" or m.get("role") == "user":
            last_user = idx
            break
    return messages[last_user:] if last_user >= 0 else messages
