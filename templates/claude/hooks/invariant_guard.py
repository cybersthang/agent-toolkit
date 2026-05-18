#!/usr/bin/env python
"""PreToolUse hook — block Edit/Write/MultiEdit that violates project invariants.

Reads `.agent-toolkit/invariants.json` relative to the workspace.

For each invariant whose `applies_to` glob(s) match the edit target:

- Edit / MultiEdit: if `old_string` contained a `must_keep_regex` match and
  `new_string` does not, the edit removes a required pattern → violation.
- Write: if the new full-file content does not match every `must_keep_regex`
  required for that path, the rewrite drops a required pattern → violation.

Severity:
- `blocker` → permissionDecision=deny, edit is rejected with reason.
- `warn`    → permissionDecision=allow, but a reminder is injected so the
              agent sees the warning in its next turn.

Fails open: any unexpected error allows the edit through. Better to
under-block than to permanently jam the workflow.

Toolkit invariant: this file ships as-is from agent-toolkit. The runtime
file the agent reads is `<workspace>/.agent-toolkit/invariants.json` —
edit invariants there, not here.
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


# Claude Code pipes UTF-8 JSON. Wrap stdin/stdout to handle non-Latin
# (Vietnamese) prompts and identifiers safely.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


INVARIANTS_REL = ".agent-toolkit/invariants.json"
SUPPORTED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _emit(decision: str, reason: str = "") -> None:
    """Write the Claude Code PreToolUse JSON envelope and exit 0."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
        }
    }
    if reason:
        payload["hookSpecificOutput"]["permissionDecisionReason"] = reason
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _allow() -> None:
    _emit("allow")


def _load_invariants(workspace: Path) -> List[Dict[str, Any]]:
    path = workspace / INVARIANTS_REL
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return []
    invariants = data.get("invariants") or []
    return [inv for inv in invariants if isinstance(inv, dict)]


def _matches_path(file_path: str, globs: Iterable[str], workspace: Path) -> bool:
    """True if file_path matches any glob. Handles both absolute and
    workspace-relative patterns. Empty/missing globs means "applies to all"."""
    globs = list(globs or [])
    if not globs:
        return True
    try:
        rel = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel = file_path.replace("\\", "/")
    abs_path = file_path.replace("\\", "/")
    for pattern in globs:
        pat = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(abs_path, pat):
            return True
        # Match recursive ** patterns more leniently — fnmatch only does shell-style.
        if "**" in pat:
            head = pat.split("**", 1)[0].rstrip("/")
            tail = pat.split("**", 1)[1].lstrip("/")
            if (not head or rel.startswith(head)) and (not tail or rel.endswith(tail.lstrip("*").lstrip("/"))):
                return True
    return False


def _compile_patterns(rules: Dict[str, Any]) -> List[Tuple[str, re.Pattern]]:
    """Build (label, compiled_regex) list. Combines must_keep_regex (raw
    regex) and must_keep_call (function/attribute name → call-site regex)."""
    out: List[Tuple[str, re.Pattern]] = []
    for raw in rules.get("must_keep_regex") or []:
        try:
            out.append((raw, re.compile(raw, re.IGNORECASE | re.MULTILINE)))
        except re.error:
            continue
    for name in rules.get("must_keep_call") or []:
        if not isinstance(name, str) or not name.strip():
            continue
        # Match `name(` or `.name(` — broad enough to catch method/attr calls.
        pattern = r"(?:\b|\.)" + re.escape(name.strip()) + r"\s*\("
        try:
            out.append((f"call:{name}", re.compile(pattern, re.MULTILINE)))
        except re.error:
            continue
    return out


def _check_edit_pair(old_string: str, new_string: str, patterns: List[Tuple[str, re.Pattern]]) -> List[str]:
    """Return labels of patterns that existed in old but disappeared in new."""
    removed: List[str] = []
    for label, regex in patterns:
        if regex.search(old_string) and not regex.search(new_string):
            removed.append(label)
    return removed


def _check_write(content: str, patterns: List[Tuple[str, re.Pattern]]) -> List[str]:
    """For Write: every required pattern must exist somewhere in the new file."""
    missing: List[str] = []
    for label, regex in patterns:
        if not regex.search(content):
            missing.append(label)
    return missing


def _collect_violations(
    tool_name: str,
    tool_input: Dict[str, Any],
    invariants: List[Dict[str, Any]],
    workspace: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (blocker_violations, warn_violations) — each entry is
    {"invariant_id", "description", "removed_patterns", "rationale"}."""
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return [], []

    blockers: List[Dict[str, Any]] = []
    warns: List[Dict[str, Any]] = []

    for inv in invariants:
        applies = inv.get("applies_to") or []
        if not _matches_path(file_path, applies, workspace):
            continue
        rules = inv.get("rules") or {}
        patterns = _compile_patterns(rules)
        if not patterns:
            continue

        removed: List[str] = []
        if tool_name in ("Edit", "NotebookEdit"):
            old_s = tool_input.get("old_string") or ""
            new_s = tool_input.get("new_string") or ""
            removed = _check_edit_pair(old_s, new_s, patterns)
        elif tool_name == "MultiEdit":
            for edit in tool_input.get("edits") or []:
                old_s = edit.get("old_string") or ""
                new_s = edit.get("new_string") or ""
                removed.extend(_check_edit_pair(old_s, new_s, patterns))
        elif tool_name == "Write":
            content = tool_input.get("content") or ""
            # For Write we only care if the FINAL file lacks the pattern.
            # If file didn't exist before, "missing" is still a violation.
            removed = _check_write(content, patterns)

        if not removed:
            continue
        entry = {
            "invariant_id": inv.get("id") or "<no-id>",
            "description": inv.get("description") or "",
            "rationale": inv.get("rationale") or "",
            "removed_patterns": removed,
            "source": f"{INVARIANTS_REL}#{inv.get('id', '?')}",
        }
        if (inv.get("severity") or "warn").lower() == "blocker":
            blockers.append(entry)
        else:
            warns.append(entry)

    return blockers, warns


def _format_reason(blockers: List[Dict[str, Any]], warns: List[Dict[str, Any]]) -> str:
    lines = ["[invariant-guard] Edit vi phạm invariant đã thoả thuận."]
    if blockers:
        lines.append("\nBLOCKER (deny):")
        for b in blockers:
            lines.append(
                f"  - {b['invariant_id']}: {b['description']}\n"
                f"      Patterns mất: {', '.join(b['removed_patterns'])}\n"
                f"      Lý do invariant: {b['rationale']}\n"
                f"      Sửa: giữ nguyên patterns trên, hoặc đổi invariant trước "
                f"qua /adr-add + /inv-add. Source: {b['source']}"
            )
    if warns:
        lines.append("\nWARN (allow, nhưng cảnh báo):")
        for w in warns:
            lines.append(
                f"  - {w['invariant_id']}: patterns yếu đi: {', '.join(w['removed_patterns'])}"
            )
    lines.append(
        "\nGhi đè 1 lần: thêm `bypass-invariant: <id>` vào prompt người dùng "
        "tiếp theo + nêu lý do, rồi user chạy lại edit. Đổi invariant lâu dài: "
        "/inv-add với severity mới hoặc /adr-add ghi nhận quyết định mới."
    )
    return "\n".join(lines)


def _bypass_requested(envelope: Dict[str, Any], blocker_ids: List[str]) -> bool:
    """Look for `bypass-invariant: <id>` in the recent user prompt (passed via
    envelope, when available) so the user can intentionally override."""
    prompt = ""
    for key in ("user_prompt", "prompt", "last_user_message"):
        if envelope.get(key):
            prompt = str(envelope[key])
            break
    if not prompt:
        return False
    matches = re.findall(r"bypass-invariant\s*:\s*([A-Za-z0-9_\-,\s]+)", prompt, re.IGNORECASE)
    if not matches:
        return False
    requested: List[str] = []
    for chunk in matches:
        requested.extend(item.strip() for item in chunk.replace(",", " ").split())
    return any(bid in requested or "all" in requested for bid in blocker_ids)


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _allow()

    raw = sys.stdin.read()
    if not raw.strip():
        _allow()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _allow()

    tool_name = envelope.get("tool_name") or ""
    if tool_name not in SUPPORTED_TOOLS:
        _allow()

    tool_input = envelope.get("tool_input") or {}
    workspace_str = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(workspace_str).resolve()

    invariants = _load_invariants(workspace)
    if not invariants:
        _allow()

    blockers, warns = _collect_violations(tool_name, tool_input, invariants, workspace)

    if not blockers and not warns:
        _allow()

    if blockers and _bypass_requested(envelope, [b["invariant_id"] for b in blockers]):
        reason = (
            "[invariant-guard] bypass-invariant detected in prompt; "
            "allowing edit. Violations were: "
            + ", ".join(b["invariant_id"] for b in blockers)
        )
        _emit("allow", reason)

    if blockers:
        _emit("deny", _format_reason(blockers, warns))

    # Only warn-level violations → allow but inject reason (visible in transcript).
    _emit("allow", _format_reason([], warns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
