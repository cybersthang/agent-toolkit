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

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, match_glob, run_main_safe, emit_fire_event,
    is_strict_mode, get_enforce_mode,
)
from _patterns import BYPASS_INVARIANT_RE  # noqa: E402

wrap_utf8_stdio()


INVARIANTS_REL = ".agent-toolkit/invariants.json"
BYPASS_FILE_REL = ".agent-toolkit/.bypass_next_edit.json"
SUPPORTED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# G4 v0.10.0 — text scan regex used when invariants.json fails to parse.
# Detects presence of any blocker invariant so we can fail-closed
# conservatively even when JSON is corrupt.
_BLOCKER_TEXT_SCAN_RE = re.compile(
    r'["\']severity["\']\s*:\s*["\']blocker["\']',
    re.IGNORECASE,
)


def _emit(decision: str, reason: str = "") -> None:
    """Write the Claude Code PreToolUse JSON envelope and exit 0."""
    # Phase C v0.9.1: record fire event (silent on failure)
    try:
        emit_fire_event("invariant_guard.py", verdict=decision)
    except Exception:
        pass
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


def _has_blocker_text_scan(workspace: Path) -> bool:
    """G4 v0.10.0 — cheap raw-text scan of invariants.json + external sources
    to detect whether ANY blocker invariant is configured.

    Used as conservative-deny signal when JSON parse fails: if the file
    exists and contains the literal `"severity": "blocker"` pattern, we
    know enforcement was intended even if the structure is now corrupt,
    so we should fail-closed rather than silently allow.
    """
    path = workspace / INVARIANTS_REL
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return False
    return bool(_BLOCKER_TEXT_SCAN_RE.search(text))


def _load_invariants(workspace: Path) -> Tuple[List[Dict[str, Any]], bool]:
    """Load invariants from `.agent-toolkit/invariants.json` + any
    `external_sources` declared there (e.g. `.codex/canonical_decisions.json`).

    External sources are normal JSON files. The hook walks top-level array
    keys (`decisions`, `invariants`) and picks up entries that carry an
    `enforcement` object (applies_to + rules + severity). This lets project-
    feature regressions live in a project-local registry while still being
    mechanically enforced, without coupling the toolkit framework to any
    specific project path.

    Returns (invariants, load_error). G4 v0.10.0: load_error=True signals
    that invariants.json exists but failed to parse — callers should
    consult `_has_blocker_text_scan()` to decide fail-open vs fail-closed.
    """
    invariants: List[Dict[str, Any]] = []
    external_sources: List[str] = []
    load_error = False
    path = workspace / INVARIANTS_REL
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw_invs = data.get("invariants") or []
                invariants = [inv for inv in raw_invs if isinstance(inv, dict)]
                ext = data.get("external_sources") or []
                if isinstance(ext, list):
                    external_sources = [s for s in ext if isinstance(s, str) and s.strip()]
            else:
                # File parsed but shape wrong — treat as load error.
                load_error = True
        except (json.JSONDecodeError, OSError):
            load_error = True
    invariants.extend(_load_external_enforcements(workspace, external_sources))
    return invariants, load_error


def _load_external_enforcements(workspace: Path, sources: List[str]) -> List[Dict[str, Any]]:
    """For each external source path, load entries whose `enforcement` field
    declares an invariant. Each loaded entry is normalized to the same shape
    as `.agent-toolkit/invariants.json` entries, with `_source_path` tagged
    so violation messages cite the right file.
    """
    out: List[Dict[str, Any]] = []
    for source_rel in sources:
        path = workspace / source_rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for array_key in ("decisions", "invariants"):
            entries = data.get(array_key) or []
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                enforcement = entry.get("enforcement")
                if not isinstance(enforcement, dict):
                    continue
                description = (
                    entry.get("question")
                    or entry.get("description")
                    or entry.get("topic")
                    or ""
                )
                rationale = (
                    enforcement.get("rationale")
                    or (entry.get("answer") or "")[:300]
                )
                out.append({
                    "id": entry.get("id") or "<no-id>",
                    "description": description,
                    "applies_to": enforcement.get("applies_to") or [],
                    "rules": enforcement.get("rules") or {},
                    "severity": enforcement.get("severity") or "warn",
                    "rationale": rationale,
                    "_source_path": source_rel,
                })
    return out


_matches_path = match_glob  # backwards-compat alias; empty_returns defaults to True.


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


def _find_call_names_via_ast(code: str):
    """G3 v0.11.0 — extract set of called function/method names from a
    Python snippet via stdlib `ast`. Returns:

    - `None` if the snippet failed to parse (partial code, syntax error,
      indented chunk). Caller treats as "AST inconclusive".
    - `set()` (empty) if parse succeeded but no Call nodes found
      (e.g. `def foo(): pass`). Caller treats as "definitive: no calls".
    - non-empty set otherwise.

    Distinguishing the two empty cases matters for Write tool: a new
    file with no calls is a definitive miss for must_keep_call_ast,
    NOT an inconclusive parse.

    Handles:
    - `foo()` → {"foo"}
    - `obj.method()` → {"method"} (Attribute callee)
    - `obj.attr.method()` → {"method"}
    - `getattr(obj, 'foo')()` is NOT caught — getattr-bypass is a known
      blind spot of static AST; pair with regex for stronger coverage.
    """
    if not code or not code.strip():
        return None
    try:
        import textwrap
        # textwrap.dedent handles common indent so a `def foo(): ...` block
        # extracted mid-file still parses.
        tree = ast.parse(textwrap.dedent(code))
    except (SyntaxError, ValueError, IndentationError, TypeError):
        return None
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _ast_call_removals(old_code: str, new_code: str,
                       required_names: List[str]) -> List[str]:
    """For each name in required_names, return those that disappeared
    between old_code and new_code per AST analysis.

    Returns [] if EITHER snippet failed to parse (AST inconclusive —
    caller falls back to regex-only signal). Returns the removed names
    when both parsed and a name appears in old but not new.
    """
    old_names = _find_call_names_via_ast(old_code)
    new_names = _find_call_names_via_ast(new_code)
    if old_names is None or new_names is None:
        # Inconclusive parse — let regex be the authoritative signal.
        return []
    removed = []
    for name in required_names:
        if not isinstance(name, str) or not name.strip():
            continue
        n = name.strip()
        if n in old_names and n not in new_names:
            removed.append(f"ast-call:{n}")
    return removed


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

    is_python_file = file_path.lower().endswith(".py")

    for inv in invariants:
        applies = inv.get("applies_to") or []
        if not _matches_path(file_path, applies, workspace):
            continue
        rules = inv.get("rules") or {}
        patterns = _compile_patterns(rules)
        ast_call_names = rules.get("must_keep_call_ast") or []
        if not patterns and not ast_call_names:
            continue

        removed: List[str] = []
        if tool_name in ("Edit", "NotebookEdit"):
            old_s = tool_input.get("old_string") or ""
            new_s = tool_input.get("new_string") or ""
            if patterns:
                removed = _check_edit_pair(old_s, new_s, patterns)
            # G3 v0.11.0: AST-based shadow check for .py files. AST is more
            # robust than regex against whitespace reformat / import-alias
            # rename — pairs with regex for stronger coverage.
            if is_python_file and ast_call_names:
                removed.extend(_ast_call_removals(old_s, new_s, ast_call_names))
        elif tool_name == "MultiEdit":
            for edit in tool_input.get("edits") or []:
                old_s = edit.get("old_string") or ""
                new_s = edit.get("new_string") or ""
                if patterns:
                    removed.extend(_check_edit_pair(old_s, new_s, patterns))
                if is_python_file and ast_call_names:
                    removed.extend(_ast_call_removals(old_s, new_s, ast_call_names))
        elif tool_name == "Write":
            content = tool_input.get("content") or ""
            # For Write we only care if the FINAL file lacks the pattern.
            # If file didn't exist before, "missing" is still a violation.
            if patterns:
                removed = _check_write(content, patterns)
            # G3: AST check on full new content. If parse succeeds AND
            # any required call name is absent → flag missing. Parse
            # failure (None) → inconclusive, don't add false-positive.
            if is_python_file and ast_call_names:
                new_names = _find_call_names_via_ast(content)
                if new_names is not None:  # parse succeeded (set possibly empty)
                    for name in ast_call_names:
                        if isinstance(name, str) and name.strip() and \
                                name.strip() not in new_names:
                            removed.append(f"ast-call:{name.strip()}")

        if not removed:
            continue
        source_path = inv.get("_source_path") or INVARIANTS_REL
        entry = {
            "invariant_id": inv.get("id") or "<no-id>",
            "description": inv.get("description") or "",
            "rationale": inv.get("rationale") or "",
            "removed_patterns": removed,
            "source": f"{source_path}#{inv.get('id', '?')}",
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


def _bypass_requested(envelope: Dict[str, Any], blocker_ids: List[str],
                      workspace: Path) -> bool:
    """Detect a single-use `bypass-invariant: <id>` token.

    G2 v0.10.0 — two sources, in order:

    1. **Ephemeral file** `.agent-toolkit/.bypass_next_edit.json`, written
       by `intent_router.py` (UserPromptSubmit hook) when the user types
       a bypass marker. This is the production path because Claude Code's
       PreToolUse envelope does NOT contain the user prompt.

    2. **Envelope fields** (`user_prompt`, `prompt`, `last_user_message`)
       — kept as fallback for: (a) test fixtures that mock the envelope,
       (b) any future Claude Code version that adds prompt context,
       (c) third-party harnesses that wrap our hooks differently.

    A hit on the ephemeral file is **consumed** (file deleted) so the
    bypass covers exactly one Edit. Expired files are also cleaned up.
    """
    import time
    # --- Source 1: ephemeral file (G2 production path) ---
    bypass_path = workspace / BYPASS_FILE_REL
    if bypass_path.exists():
        try:
            data = json.loads(bypass_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            ts = int(data.get("ts") or 0)
            ttl = int(data.get("ttl_seconds") or 300)
            requested = data.get("ids") or []
            expired = (int(time.time()) - ts) > ttl
            if expired:
                try:
                    bypass_path.unlink()
                except OSError:
                    pass
            elif isinstance(requested, list) and any(
                bid in requested or "all" in requested for bid in blocker_ids
            ):
                try:
                    bypass_path.unlink()  # single-use; consume.
                except OSError:
                    pass
                return True

    # --- Source 2: envelope fields (legacy / test fixture fallback) ---
    prompt = ""
    for key in ("user_prompt", "prompt", "last_user_message"):
        if envelope.get(key):
            prompt = str(envelope[key])
            break
    if not prompt:
        return False
    matches = BYPASS_INVARIANT_RE.findall(prompt)
    if not matches:
        return False
    requested = []
    for chunk in matches:
        requested.extend(item.strip() for item in chunk.replace(",", " ").split())
    return any(bid in requested or "all" in requested for bid in blocker_ids)


def _fail_closed_for_corrupt_state(workspace: Path, reason_tag: str) -> None:
    """G4 v0.10.0 — emit deny when we cannot read the invariant config but
    a blocker invariant *was* configured (per cheap text scan). Conservative
    over silently allowing.

    Fail-open is preserved when:
    - No invariants.json exists at all (greenfield project, nothing to guard).
    - File exists but the text scan finds no `blocker` severity (only warns).
    - `AGENT_TOOLKIT_DISABLE=1` was set (kill-switch already handled earlier).

    Fail-closed kicks in when:
    - File exists + text scan finds blocker + JSON is corrupt OR envelope is
      corrupt OR tool_input is malformed.
    - `enforce_mode.json` per-hook=block or AGENT_TOOLKIT_STRICT=1 globally.
    """
    has_blocker = _has_blocker_text_scan(workspace)
    mode = get_enforce_mode(workspace, "invariant_guard", default="warn")
    strict = is_strict_mode()
    # Conservative-deny if a blocker was clearly configured, OR if operator
    # opted into strict/block mode.
    if has_blocker or mode == "block" or strict:
        _emit(
            "deny",
            f"[invariant-guard] {reason_tag}. Invariants config is unreadable "
            f"but blocker rules are configured — denying conservatively. "
            f"Fix `.agent-toolkit/invariants.json` (or set "
            f"AGENT_TOOLKIT_DISABLE=1 as emergency override).",
        )
    _allow()


def _silent_exit() -> None:
    """v0.12.3 — exit 0 without JSON output / fire log. Used by the
    empty-registry fast path so the hook becomes a true no-op when no
    invariants are configured (Claude Code treats absent output as
    default allow). Avoids the ~30 tokens of `{"permissionDecision":
    "allow"}` JSON per fire — empirically 66 fires/session × 30 tokens
    = ~2k tokens saved when registry is empty."""
    sys.exit(0)


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _silent_exit()

    raw = sys.stdin.read()

    # Workspace discovery — needed even on envelope parse failure so we
    # can run the conservative-deny text scan.
    workspace_str = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    if not raw.strip():
        # Empty envelope: legitimate when Claude Code probes the hook. No
        # tool to evaluate; allow.
        _silent_exit()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        # G4: envelope corrupt — can't tell what's being edited. If any
        # blocker invariant is configured, fail-closed.
        _fail_closed_for_corrupt_state(
            Path(workspace_str).resolve(),
            "envelope JSON could not be parsed",
        )

    tool_name = envelope.get("tool_name") or ""
    if tool_name not in SUPPORTED_TOOLS:
        _silent_exit()

    tool_input = envelope.get("tool_input") or {}
    workspace_str = envelope.get("cwd") or workspace_str
    workspace = Path(workspace_str).resolve()

    # v0.12.3 — fast path: if invariants.json missing OR empty AND no
    # blocker text scan signal → silent no-op exit (saves ~30 tokens
    # per fire × ~66 fires/session on registries with 0 invariants).
    # Keeps fail-closed behavior intact: blocker text in file or parse
    # error still falls through to the conservative-deny path below.
    invariants_path = workspace / INVARIANTS_REL
    if not invariants_path.exists() and not _has_blocker_text_scan(workspace):
        _silent_exit()

    invariants, load_error = _load_invariants(workspace)

    if load_error:
        # G4: invariants.json exists but didn't parse cleanly. Conservative
        # deny if blocker rules are configured per text scan.
        _fail_closed_for_corrupt_state(
            workspace,
            "invariants.json exists but could not be parsed",
        )

    if not invariants:
        # File exists but registry is empty — silent exit, no log noise.
        _silent_exit()

    blockers, warns = _collect_violations(tool_name, tool_input, invariants, workspace)

    if not blockers and not warns:
        _allow()

    if blockers and _bypass_requested(envelope, [b["invariant_id"] for b in blockers], workspace):
        reason = (
            "[invariant-guard] bypass-invariant token consumed; "
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
    sys.exit(run_main_safe(main))
