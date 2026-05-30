"""Transcript parsing: JSONL load, turn-split, tool_use/tool_result
extraction, TodoWrite state walk."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def read_transcript(path: Path) -> List[Dict[str, Any]]:
    """Read JSONL transcript. Returns parsed messages in order. utf-8-sig
    tolerates BOM written by PowerShell Out-File -Encoding utf8."""
    out: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8-sig") as fh:
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


def _is_real_user_prompt(msg: Dict[str, Any]) -> bool:
    """A user message counts as a real prompt boundary only when its content
    is NOT entirely tool_result blocks. Intermediate tool_result messages
    (harness echoes) must not truncate the turn."""
    role = msg.get("role") or msg.get("type")
    if role != "user":
        return False
    content = (msg.get("message") or {}).get("content") or msg.get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            btype = b.get("type")
            if btype == "tool_result":
                continue
            if btype == "text" and (b.get("text") or "").strip():
                return True
            if btype and btype != "tool_result":
                return True
        return False
    return True


def split_current_turn(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return messages from the most-recent REAL user prompt to the end."""
    last_real = -1
    for idx in range(len(messages) - 1, -1, -1):
        if _is_real_user_prompt(messages[idx]):
            last_real = idx
            break
    if last_real < 0:
        return messages
    return messages[last_real:]


def extract_text_and_tools(turn: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Concatenate assistant text and collect tool_use entries from the turn."""
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role == "assistant":
            content = (msg.get("message") or {}).get("content") or msg.get("content")
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text") or "")
                    elif btype == "tool_use":
                        tool_calls.append(block)
    return ("\n".join(text_parts), tool_calls)


def extract_tool_results(turn: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Walk turn, build tool_use_id -> tool_result block map."""
    out: Dict[str, Dict[str, Any]] = {}
    for msg in turn:
        role = msg.get("role") or msg.get("type")
        if role != "user":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                tid = block.get("tool_use_id") or ""
                if tid:
                    out[tid] = block
    return out


def latest_todos_state(all_messages: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Walk FULL transcript backward; return latest TodoWrite `todos` array.
    Returns None if no TodoWrite ever called."""
    for msg in reversed(all_messages):
        role = msg.get("role") or msg.get("type")
        if role != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "TodoWrite":
                todos = (block.get("input") or {}).get("todos")
                if isinstance(todos, list):
                    return todos
    return None
