#!/usr/bin/env python
"""PreToolUse(Bash) hook — block destructive git commands the AGENT is
not authorized to run.

Inspired by [mattpocock/skills/misc/git-guardrails-claude-code](https://github.com/mattpocock/skills/tree/main/skills/misc/git-guardrails-claude-code)
(MIT — Copyright (c) Matt Pocock). Adapted to Python to match the rest
of the toolkit's hook layer (uniform `_common`/`emit_fire_event`
plumbing, no `jq` dependency, `get_enforce_mode` integration).

Default blocked patterns (per ADR-aligned `feedback_no_ai_commit` —
DEV is the sole gatekeeper for git state changes):

  - `git commit`           (any variant, including `--amend`)
  - `git push`             (any variant, including `--force`)
  - `git add`              (any variant, including `-A` / `.`)
  - `git reset --hard`
  - `git clean -f` / `git clean -fd`
  - `git branch -D`
  - `git checkout .` / `git restore .`
  - flag `--no-verify`     (skip pre-commit hooks)
  - flag `--no-gpg-sign`   (skip commit signing)
  - flag `--force` / `-f`  (when paired with push / branch)

Enforce mode (per `get_enforce_mode(workspace, 'git_guardrails')`):
  - `block` (default)  → permissionDecision=deny + stderr reason.
  - `warn`             → permissionDecision=allow + reminder injected.
  - `off`              → silent allow.

Bypass mechanism (single-use, consumed on read):
  - `.agent-toolkit/.skip_git_guard_next.json` fresh (mtime < 600s) →
    allow ONE git command, then delete the marker. Lets DEV explicitly
    pre-authorize a single agent-driven git op without disabling the
    hook globally.

Fails open on any unexpected error — better to under-block than to
permanently jam the workflow.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, run_main_safe, emit_fire_event, get_enforce_mode,
)

wrap_utf8_stdio()

# Kill-switch — every toolkit hook honors AGENT_TOOLKIT_DISABLE=1 so DEV
# can disable the whole stack at once (e.g. recovering from a hook bug
# without uninstalling). Checked at module-import time.
if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }}, ensure_ascii=False))
    sys.exit(0)


SKIP_TOKEN_REL = ".agent-toolkit/.skip_git_guard_next.json"
SKIP_TOKEN_TTL_SECONDS = 600
HOOK_NAME = "git_guardrails"


# (pattern_regex, human_label) — order matters for clearer first-match reason.
# Use word-boundary / lookahead to avoid false positives like `git committed/`
# being a directory name. Patterns assume normal shell tokenization
# (whitespace-separated).
_DANGEROUS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+commit(?:\s|$)"),       "git commit"),
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+push(?:\s|$)"),         "git push"),
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+add(?:\s|$)"),          "git add"),
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+reset\s+--hard\b"),     "git reset --hard"),
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+clean\s+-[A-Za-z]*f"),  "git clean -f"),
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+branch\s+-D\b"),        "git branch -D"),
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+checkout\s+\.(?:\s|$)"),"git checkout ."),
    (re.compile(r"(?:^|\s|;|&&|\|\|)git\s+restore\s+\.(?:\s|$)"), "git restore ."),
    (re.compile(r"--no-verify\b"),                                "--no-verify flag"),
    (re.compile(r"--no-gpg-sign\b"),                              "--no-gpg-sign flag"),
    (re.compile(r"(?:^|\s)git\s+\S+\s+(?:--force|-f)\b"),         "--force flag"),
]


def _emit_allow(detail: Optional[str] = None) -> None:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="allow", detail=detail)
    except Exception:
        pass
    payload = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": "allow"}}
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _emit_deny(reason: str) -> None:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="block", detail=reason[:200])
    except Exception:
        pass
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _emit_warn(reason: str) -> None:
    try:
        emit_fire_event(f"{HOOK_NAME}.py", verdict="warn", detail=reason[:200])
    except Exception:
        pass
    # warn mode = allow but surface the reason in agent's context.
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": f"[git-guardrails warn] {reason}",
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _read_off_override(workspace: Path) -> bool:
    """`_common.get_enforce_mode` only validates "warn"/"block" — `"off"`
    falls through. Read the file directly so DEV can disable the hook
    without uninstalling it."""
    cfg_path = workspace / ".agent-toolkit" / "enforce_mode.json"
    if not cfg_path.exists():
        return False
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(cfg, dict):
        return False
    per_hook = cfg.get("per_hook") or {}
    if isinstance(per_hook, dict) and per_hook.get(HOOK_NAME) == "off":
        return True
    return cfg.get("default") == "off"


def _consume_skip_token(workspace: Path) -> bool:
    """Return True iff a fresh bypass marker exists; delete on use."""
    path = workspace / SKIP_TOKEN_REL
    if not path.exists():
        return False
    try:
        age = time.time() - path.stat().st_mtime
        if age > SKIP_TOKEN_TTL_SECONDS:
            # Stale marker — clean up but don't honor.
            path.unlink(missing_ok=True)
            return False
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _find_workspace_root(start: Path) -> Path:
    """Walk up looking for `.agent-toolkit/`. Fall back to start."""
    for candidate in [start, *start.parents]:
        if (candidate / ".agent-toolkit").is_dir():
            return candidate
    return start


def _scan(command: str) -> Optional[str]:
    """Return human label of first matched dangerous pattern, or None."""
    if not command:
        return None
    for pattern, label in _DANGEROUS_PATTERNS:
        if pattern.search(command):
            return label
    return None


def _main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        _emit_allow(detail="bad-json")
        return

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or ""

    if not isinstance(command, str) or not command.strip():
        _emit_allow(detail="empty-command")
        return

    workspace = _find_workspace_root(Path.cwd())
    label = _scan(command)
    if label is None:
        _emit_allow()
        return

    # Dangerous pattern detected. Check bypass + enforce mode.
    if _consume_skip_token(workspace):
        _emit_allow(detail=f"bypass:{label}")
        return

    # `_common.get_enforce_mode` only validates "warn"/"block"; `"off"` is
    # checked explicitly first so DEV can fully disable the hook.
    if _read_off_override(workspace):
        _emit_allow(detail=f"off:{label}")
        return

    # `feedback_no_ai_commit` is strict — git_guardrails defaults to `block`
    # even when the rest of the toolkit defaults to `warn`.
    mode = get_enforce_mode(workspace, HOOK_NAME, default="block")
    reason = (
        f"git-guardrails: command matches '{label}'. The AGENT is not "
        f"authorized to run this — DEV must run it from their own "
        f"terminal. To grant a one-time bypass, DEV can create "
        f"`.agent-toolkit/.skip_git_guard_next.json` (any content; expires "
        f"in {SKIP_TOKEN_TTL_SECONDS}s) and retry."
    )

    if mode == "warn":
        _emit_warn(reason)
        return
    # default = block
    _emit_deny(reason)


if __name__ == "__main__":
    sys.exit(run_main_safe(_main))
