#!/usr/bin/env python
"""PostToolUse hook — verification loop on every .py Edit/Write/MultiEdit.

Upstream provenance
-------------------
- Repo   : https://github.com/affaan-m/everything-claude-code
- Author : @affaan-m
- Skill  : skills/verification-loop/SKILL.md
- URL    : https://github.com/affaan-m/everything-claude-code/blob/main/skills/verification-loop/SKILL.md
- Adopted: 2026-05-17 (commit not pinned — upstream evolves fast)
- License: see upstream repo

This file is a derivative — adapted from a generic Node/TS build-lint-
typecheck loop to the Odoo 12 MCP probe set
(`python_syntax_check` / `python_import_check` / `xml_validate` /
`odoo_manifest_validate`). To re-sync with upstream, WebFetch the URL
above and diff against this docstring's behaviour section.

After each Edit / Write / MultiEdit on a `.py` file inside one of the
configured `addon_roots`, this hook emits an `additionalContext` reminder
listing the MCP probes the agent SHOULD run before the next response:

  1. `python_syntax_check` — catches IndentationError / SyntaxError at edit
     time, before any test runs.
  2. `python_import_check` — catches ModuleNotFoundError / ImportError that
     would surface only at module install.
  3. `xml_validate` if the edit was an XML view / data file.
  4. `odoo_manifest_validate` if the edit was a `__manifest__.py`.

The hook is **nudge-only** (never blocks the Edit). It is the *Stop* hook
`evidence_audit.py` that will reject the final response if the agent claims
"done" without these checks in its tool-call history for this turn.

Config: `<workspace>/.agent-toolkit/verification.json`:

```json
{
  "enabled": true,
  "mcp_prefix": "mcp__<project-slug>-<framework><version>__",
  "addon_globs": [
    "**/__manifest__.py",
    "**/models/**.py",
    "**/controllers/**.py",
    "**/wizards/**.py",
    "**/views/**.xml"
  ]
}
```

Behaviour:

- Hook silent when config missing / enabled=false / tool not Edit/Write/
  MultiEdit / file path not under addon_globs.
- Duplicate suppression: don't re-nudge the same file within 30 s.
- File-type aware: `.py` → syntax + import; `.xml` → xml_validate;
  `__manifest__.py` → manifest_validate (in addition to syntax).
- Fails open on any error.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, atomic_write_json, match_glob, discover_mcp_prefix,
)

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/verification.json"
STATE_REL = ".agent-toolkit/.verification_loop_last.json"
SUPPORTED_TOOLS = {"Edit", "Write", "MultiEdit"}
NUDGE_TTL_SECONDS = 30


def _exit_silent() -> None:
    sys.exit(0)


def _emit(text: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _load_config(workspace: Path) -> Optional[Dict[str, Any]]:
    path = workspace / CONFIG_REL
    if not path.exists():
        return None
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return cfg if isinstance(cfg, dict) else None


def _classify(file_path: str) -> List[str]:
    """Return list of probe kinds applicable to this file.

    Note: `import` probe is NOT applicable to Odoo addon code — the MCP
    `python_import_check` runs in a bare subprocess without the Odoo
    registry, so any module under `odoo.addons.*` will always raise
    ModuleNotFoundError. Similarly `run_python_tests` MCP does NOT load
    the Odoo registry — HttpCase/TransactionCase tests fail to import
    `from odoo.tests.common`. The right path for Odoo addon tests is
    `odoo-bin -d <db> -i <addon> --test-enable --stop-after-init`. The
    hook detects when a sibling `tests/` folder exists and nudges that
    command instead.
    """
    p = Path(file_path)
    name = p.name
    suffix = p.suffix.lower()
    kinds: List[str] = []
    if suffix == ".py":
        kinds.append("syntax")
        if name == "__manifest__.py":
            kinds.append("manifest")
        elif _has_sibling_tests(p):
            kinds.append("addon_test")  # nudge odoo-bin --test-enable
    elif suffix == ".xml":
        kinds.append("xml")
    return kinds


def _has_sibling_tests(file_path: Path) -> bool:
    """Return True if file's addon has a `tests/` folder with __init__.py.

    Walks up from file_path looking for the closest `__manifest__.py`, then
    checks if that addon directory contains `tests/__init__.py`. Avoids
    nudging odoo-bin --test-enable when no test infrastructure exists.
    """
    try:
        cursor = file_path.parent if file_path.is_file() else file_path
        # M1 fix (2026-05-17): walk to FS root instead of magic bound — handles
        # arbitrarily deep addon trees (e.g. OCA nested submodules ≥ 8 levels).
        while True:
            if (cursor / "__manifest__.py").exists():
                tests_init = cursor / "tests" / "__init__.py"
                return tests_init.exists()
            if cursor.parent == cursor:
                return False
            cursor = cursor.parent
    except OSError:
        return False
    return False


def _addon_name(file_path: Path) -> Optional[str]:
    """Find addon name (directory containing __manifest__.py) for a file."""
    try:
        cursor = file_path.parent if file_path.is_file() else file_path
        # M1 fix: walk to FS root instead of magic bound.
        while True:
            if (cursor / "__manifest__.py").exists():
                return cursor.name
            if cursor.parent == cursor:
                return None
            cursor = cursor.parent
    except OSError:
        pass
    return None


def _is_duplicate(workspace: Path, file_path: str) -> bool:
    path = workspace / STATE_REL
    state: Dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    now = int(time.time())
    if state.get("file_path") == file_path and (now - int(state.get("at", 0))) < NUDGE_TTL_SECONDS:
        return True
    atomic_write_json(path, {"file_path": file_path, "at": now})
    return False


def _build_message(file_path: str, rel_path: str, kinds: List[str], mcp_prefix: str) -> str:
    lines = [
        f"[verification-loop] Vừa Edit/Write `{rel_path}` — TRƯỚC khi trả lời "
        "\"đã xong / ready / verified\", phải chạy các probe sau và đưa output "
        "vào tool-call history của turn này:",
        "",
    ]
    step = 1
    if "syntax" in kinds:
        lines.append(
            f"  {step}. `{mcp_prefix}python_syntax_check` với path `{rel_path}` "
            "→ bắt SyntaxError / IndentationError ngay tại edit-time."
        )
        step += 1
    if "manifest" in kinds:
        lines.append(
            f"  {step}. `{mcp_prefix}odoo_manifest_validate` với path `{rel_path}` "
            "→ depends/data/version structure phải hợp lệ trước khi install."
        )
        step += 1
    if "addon_test" in kinds:
        addon = _addon_name(Path(file_path)) or "<addon>"
        lines.append(
            f"  {step}. Chạy test addon `{addon}` qua `odoo-bin --test-enable`:\n"
            f"     ```\n"
            f"     <venv-python> <odoo-bin-path> -d <dev_db> "
            f"-i {addon} --test-enable --stop-after-init --log-level=test\n"
            f"     ```\n"
            f"     (Thay `<odoo-bin-path>` bằng `odoo-bin` thực tế của "
            f"project — discover qua `agent-toolkit.config.json` "
            f"`stack.odoo_bin_rel`, hoặc `find . -name odoo-bin`.)\n"
            f"     KHÔNG dùng MCP `python_import_check` hoặc `run_python_tests` "
            f"cho Odoo addon — cả hai chạy subprocess KHÔNG load Odoo registry "
            f"→ HttpCase/TransactionCase fail import `from odoo.tests.common`."
        )
        step += 1
    if "xml" in kinds:
        lines.append(
            f"  {step}. `{mcp_prefix}xml_validate` với path `{rel_path}` "
            "→ bắt malformed XML / unknown view inherit_id / arch sai."
        )
        step += 1
    lines.extend([
        "",
        "Nếu probe FAIL → fix ngay, KHÔNG được claim done.",
        "Tắt nhắc này: sửa `.agent-toolkit/verification.json` → `enabled: false`.",
    ])
    return "\n".join(lines)


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        _exit_silent()

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_silent()

    tool_name = envelope.get("tool_name") or ""
    if tool_name not in SUPPORTED_TOOLS:
        _exit_silent()

    tool_input = envelope.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        _exit_silent()

    workspace_str = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(workspace_str).resolve()

    cfg = _load_config(workspace)
    if not cfg or not cfg.get("enabled"):
        _exit_silent()

    addon_globs = cfg.get("addon_globs") or []
    if not match_glob(file_path, addon_globs, workspace, empty_returns=False):
        _exit_silent()

    kinds = _classify(file_path)
    if not kinds:
        _exit_silent()

    if _is_duplicate(workspace, file_path):
        _exit_silent()

    # Dynamic discovery: trust cfg if concrete, else read .mcp.json.
    mcp_prefix = discover_mcp_prefix(workspace, cfg.get("mcp_prefix"))
    try:
        rel_path = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel_path = file_path

    _emit(_build_message(file_path, rel_path, kinds, mcp_prefix))
    return 0


if __name__ == "__main__":
    sys.exit(main())
