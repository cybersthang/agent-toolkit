#!/usr/bin/env python
"""Stop hook — detect overly-complex Python code added in current turn.

Uses stdlib `ast` (no new dep) to scan each `.py` file edited this turn.
Emits a soft warn (additionalContext) when any heuristic exceeds threshold:
  - Nested loop depth >= max_loop_nest (default 3)
  - Nested if/elif depth >= max_if_nest (default 4)
  - Function body LOC >= max_function_loc (default 60)
  - Single function cyclomatic-ish branch count >= max_branches (default 12)

NEVER blocks. Observability only. Map to Karpathy §2 "Simplicity First".

Config: `<workspace>/.agent-toolkit/complexity_budget.json` (optional;
defaults shown above).

Trigger heuristic: parse current-turn transcript for tool_use blocks
(Edit/Write/MultiEdit) targeting `.py` files. Skip test files.

Honors `AGENT_TOOLKIT_DISABLE=1`. Fails open silently.

v0.12.0 — closes "complexity thấp nhất" gap (HE Dim 5 modularity / Dim 11).
"""
from __future__ import annotations

import ast
import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, split_current_turn,
    run_main_safe, emit_fire_event,
)

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/complexity_budget.json"
_DEFAULT_CFG = {
    "enabled": True,
    "max_loop_nest": 3,
    "max_if_nest": 4,
    "max_function_loc": 60,
    "max_branches": 12,
    "exempt_globs": ["tests/**", "**/test_*.py", "**/*_test.py",
                     "**/migrations/**"],
}
LOOP_NODES = (ast.For, ast.While, ast.AsyncFor)
IF_NODES = (ast.If,)
BRANCH_NODES = (ast.If, ast.For, ast.While, ast.AsyncFor,
                ast.Try, ast.With, ast.AsyncWith,
                ast.BoolOp, ast.IfExp)


def _exit_allow() -> None:
    sys.exit(0)


def _load_cfg(workspace: Path) -> Dict[str, Any]:
    p = workspace / CONFIG_REL
    cfg = dict(_DEFAULT_CFG)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                cfg.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _is_exempt(rel: str, exempt_globs: List[str]) -> bool:
    rel = rel.replace("\\", "/")
    for pat in exempt_globs:
        if fnmatch.fnmatch(rel, pat):
            return True
    return False


def _max_nest_depth(node: ast.AST, target_types: tuple) -> int:
    """DFS — return deepest chain of target_types ancestors in this subtree."""
    best = [0]

    def walk(n: ast.AST, depth: int) -> None:
        cur = depth
        if isinstance(n, target_types):
            cur = depth + 1
            best[0] = max(best[0], cur)
        for child in ast.iter_child_nodes(n):
            walk(child, cur)
    walk(node, 0)
    return best[0]


def _count_branches(node: ast.AST) -> int:
    count = 0
    for sub in ast.walk(node):
        if isinstance(sub, BRANCH_NODES):
            count += 1
    return count


def _function_body_loc(node: ast.AST) -> int:
    """Approximate LOC = end_lineno - lineno + 1. Falls back to body length."""
    end = getattr(node, "end_lineno", None)
    start = getattr(node, "lineno", None)
    if end and start:
        return max(0, end - start + 1)
    body = getattr(node, "body", []) or []
    return len(body)


def _analyse_file(file_path: Path, cfg: Dict[str, Any]) -> List[str]:
    """Return list of warning strings for one .py file."""
    if not file_path.exists():
        return []
    try:
        src = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    warns: List[str] = []
    max_loop = int(cfg["max_loop_nest"])
    max_if = int(cfg["max_if_nest"])
    max_fn_loc = int(cfg["max_function_loc"])
    max_branches = int(cfg["max_branches"])

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            line = node.lineno
            loop_depth = _max_nest_depth(node, LOOP_NODES)
            if_depth = _max_nest_depth(node, IF_NODES)
            body_loc = _function_body_loc(node)
            branches = _count_branches(node)
            if loop_depth >= max_loop:
                warns.append(
                    f"  - {name}() at line {line}: loop nest = {loop_depth} "
                    f"(threshold {max_loop})"
                )
            if if_depth >= max_if:
                warns.append(
                    f"  - {name}() at line {line}: if/elif nest = {if_depth} "
                    f"(threshold {max_if})"
                )
            if body_loc >= max_fn_loc:
                warns.append(
                    f"  - {name}() at line {line}: function body = {body_loc} LOC "
                    f"(threshold {max_fn_loc})"
                )
            if branches >= max_branches:
                warns.append(
                    f"  - {name}() at line {line}: branch count = {branches} "
                    f"(threshold {max_branches})"
                )
    return warns


def _extract_edited_py_files(turn: List[Dict[str, Any]],
                             workspace: Path) -> Set[Path]:
    files: Set[Path] = set()
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name = b.get("name") or ""
            if name not in ("Edit", "Write", "MultiEdit"):
                continue
            input_ = b.get("input") or {}
            fp = input_.get("file_path")
            if not fp:
                continue
            p = Path(fp)
            if p.suffix == ".py":
                files.add(p)
    return files


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
    if envelope.get("stop_hook_active"):
        _exit_allow()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()
    cfg = _load_cfg(workspace)
    if not cfg.get("enabled", True):
        _exit_allow()

    transcript_path = envelope.get("transcript_path")
    if not transcript_path:
        _exit_allow()
    tpath = Path(transcript_path)
    if not tpath.exists():
        _exit_allow()

    messages = read_jsonl_transcript(tpath)
    if not messages:
        _exit_allow()
    turn = split_current_turn(messages)
    py_files = _extract_edited_py_files(turn, workspace)
    if not py_files:
        _exit_allow()

    exempt = cfg.get("exempt_globs") or []
    findings: List[Tuple[str, List[str]]] = []
    for p in py_files:
        try:
            rel = str(p.resolve().relative_to(workspace)).replace("\\", "/")
        except (ValueError, OSError):
            rel = str(p).replace("\\", "/")
        if _is_exempt(rel, exempt):
            continue
        warns = _analyse_file(p, cfg)
        if warns:
            findings.append((rel, warns))

    if not findings:
        try:
            emit_fire_event("complexity_sentinel.py", verdict="allow")
        except Exception:
            pass
        _exit_allow()

    try:
        emit_fire_event("complexity_sentinel.py", verdict="warn",
                        detail=f"{len(findings)} file(s)")
    except Exception:
        pass

    lines = ["[complexity-sentinel] Complexity hotspots in turn edits:", ""]
    for rel, warns in findings:
        lines.append(f"  **{rel}**")
        for w in warns:
            lines.append(w)
        lines.append("")
    lines.extend([
        "Karpathy §2: 'Minimum code that solves the problem. Nothing speculative.'",
        "If a hotspot is intentional (algorithmic necessity, hot path), add",
        "a one-line comment explaining the trade-off so future review skips it.",
    ])
    message = "\n".join(lines)

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
