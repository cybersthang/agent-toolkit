#!/usr/bin/env python
"""PostToolUse Edit hook — auto-run matching unit tests after an edit.

Replaces the manual `tdd_runner.py` nudge (text only) with mechanical
test execution via the mcp_call CLI bridge. When DEV edits
`models/foo.py`, this hook looks up `tests/test_foo.py` (and similar
patterns) and invokes the project's configured test MCP tool.

Config: `.agent-toolkit/auto_test.json` (see _DEFAULT_CONFIG).

Project-agnostic via per-stack `test_mapping` patterns:
- Odoo: `{module}/models/foo.py` -> `{module}` via realdata_test:run_module_test
- Django: `app/views/foo.py` -> `app/tests/test_foo.py` via pytest MCP
- Generic: regex group capture to test file path.

Debounce: per-test last-run timestamp in
`.agent-toolkit/.auto_test_state.json`.

Fails open: any error logged, exit 0.
"""
from __future__ import annotations

import fnmatch
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_DEFAULT_CONFIG = {
    "enabled": True,
    "debounce_s": 10,
    "mcp_server": "realdata_test",
    "mcp_tool": "run_module_test",
    "test_mappings": [
        {
            "_doc": "Odoo: match `*/models/*.py` or `*/controllers/*.py` -> module dir.",
            "src_regex": r"^(?P<module>[^/]+(?:/[^/]+)*?)/(models|controllers|wizard|wizards|jobs)/[^/]+\.py$",
            "mcp_args_template": {
                "module_name": "{module_name}",
                "module_action": "update",
                "allow_db_write": True,
                "test_tag": "/{module_name}"
            },
            "module_name_from": "module_basename"
        }
    ],
    "skip_path_globs": [
        "**/tests/**", "**/test_*.py",
        ".agent-toolkit/**", ".codex/**", ".claude/**",
        "**/__pycache__/**", "**/migrations/**"
    ],
    "state_file": ".agent-toolkit/.auto_test_state.json",
    "timeout_s": 600
}


def _load_config(workspace: Path) -> Dict[str, Any]:
    path = workspace / ".agent-toolkit" / "auto_test.json"
    cfg = json.loads(json.dumps(_DEFAULT_CONFIG))  # deep copy
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8-sig"))
            cfg.update(override)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _matches_any_glob(path: str, globs: List[str]) -> bool:
    rel = path.replace("\\", "/")
    for g in globs or []:
        if fnmatch.fnmatch(rel, g.replace("\\", "/")):
            return True
    return False


def _resolve_module_name(file_path: str, mapping: Dict[str, Any],
                         match: re.Match) -> Optional[str]:
    """Extract the module identifier per `module_name_from` strategy."""
    strategy = (mapping.get("module_name_from") or "module_basename").lower()
    groupdict = match.groupdict()
    if strategy == "module_basename":
        full = groupdict.get("module") or ""
        return full.split("/")[-1] if full else None
    if strategy == "first_group":
        return match.group(1) if match.groups() else None
    if strategy == "literal":
        return mapping.get("module_name_literal")
    return None


def _apply_args_template(template: Dict[str, Any], module_name: str) -> Dict[str, Any]:
    """Fill {module_name} placeholders inside the mcp_args_template."""
    try:
        rendered = json.dumps(template, ensure_ascii=False)
        rendered = rendered.replace("{module_name}", module_name)
        return json.loads(rendered)
    except (TypeError, ValueError):
        return template


def _find_mapping(edited_path: str, mappings: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], re.Match]]:
    rel = edited_path.replace("\\", "/")
    for m in mappings:
        rx = m.get("src_regex")
        if not rx:
            continue
        try:
            match = re.search(rx, rel)
            if match:
                return m, match
        except re.error:
            continue
    return None


def _load_state(workspace: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    p = workspace / config["state_file"]
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(workspace: Path, config: Dict[str, Any],
                state: Dict[str, Any]) -> None:
    p = workspace / config["state_file"]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    except OSError:
        pass


def _invoke_mcp(workspace: Path, server: str, tool: str,
                args: Dict[str, Any], timeout_s: int) -> Dict[str, Any]:
    cli = workspace / ".codex" / "tools" / "mcp_call.py"
    if not cli.exists():
        return {"status": "no-mcp-call", "msg": "Run setup.py update first."}
    try:
        proc = subprocess.run(
            [sys.executable, str(cli), server, tool,
             "--args", json.dumps(args, ensure_ascii=False),
             "--timeout", str(timeout_s)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout_s + 30,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except OSError as e:
        return {"status": "error", "msg": str(e)}

    verdict = "passed" if proc.returncode == 0 else (
        "failed" if proc.returncode == 1 else "invocation-error"
    )
    return {
        "status": verdict,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-400:],
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def main() -> int:
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return 0

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()
    config = _load_config(workspace)
    if not config.get("enabled"):
        return 0

    inp = envelope.get("tool_input") or {}
    file_path = inp.get("file_path") or inp.get("notebook_path")
    if not file_path:
        return 0
    edited = str(file_path).replace("\\", "/")

    if _matches_any_glob(edited, config.get("skip_path_globs") or []):
        return 0

    mapping_match = _find_mapping(edited, config.get("test_mappings") or [])
    if not mapping_match:
        return 0
    mapping, match = mapping_match
    module_name = _resolve_module_name(edited, mapping, match)
    if not module_name:
        return 0

    state = _load_state(workspace, config)
    debounce_s = int(config.get("debounce_s", 10))
    last = state.get(module_name, {}).get("ts") or 0
    now = time.time()
    if (now - last) < debounce_s:
        return 0

    args_template = mapping.get("mcp_args_template") or {}
    final_args = _apply_args_template(args_template, module_name)

    result = _invoke_mcp(
        workspace,
        config["mcp_server"], config["mcp_tool"],
        final_args, int(config.get("timeout_s", 600))
    )
    state[module_name] = {
        "ts": now,
        "status": result.get("status"),
        "returncode": result.get("returncode"),
    }
    _save_state(workspace, config, state)

    print(f"[auto_test_runner] {module_name}: {result.get('status')} "
          f"(rc={result.get('returncode')})")
    tail = (result.get("stdout_tail") or "").strip()
    if tail:
        last_line = tail.splitlines()[-1][:200] if tail.splitlines() else tail[:200]
        print(f"  last: {last_line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
