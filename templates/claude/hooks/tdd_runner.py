#!/usr/bin/env python
"""PostToolUse hook — Vibe-flow Phase 3: TDD auto-loop.

Sau mỗi Edit / Write / MultiEdit trên file matching glob trong
`.agent-toolkit/tdd.json`, hook này emit `additionalContext` nhắc agent
chạy MCP `run_python_tests` (mode `nudge`) hoặc tự subprocess pytest
(mode `run`).

Config: `<workspace>/.agent-toolkit/tdd.json`.

```json
{
  "enabled": true,
  "mode": "nudge",                              // "nudge" | "run"
  "test_glob": ["**/tests/test_*.py"],
  "source_glob": ["**/models/**.py", "**/controllers/**.py", "**/wizards/**.py"],
  "test_command": "<python> -m pytest -x"       // chỉ dùng nếu mode=run
}
```

Behaviour:

- Hook silent khi config thiếu / enabled=false / file path không match glob /
  tool không phải Edit/Write/MultiEdit.
- Mode `nudge`: emit additionalContext có 3-4 dòng nhắc agent (idempotent —
  không nudge 2 lần liên tiếp cho cùng 1 file).
- Mode `run`: subprocess `test_command <path>` với timeout 30s, capture
  stdout/stderr, emit additionalContext kèm pass/fail + tail 20 dòng output.

Fail open: lỗi gì cũng exit 0 (không bao giờ block edit đã rồi).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, atomic_write_json, match_glob,
)

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/tdd.json"
SUPPORTED_TOOLS = {"Edit", "Write", "MultiEdit"}
NUDGE_STATE_REL = ".agent-toolkit/.tdd_runner_last.json"
NUDGE_TTL_SECONDS = 30  # don't repeat the same nudge within this window
RUN_TIMEOUT_SECONDS = 30


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
    if not isinstance(cfg, dict):
        return None
    return cfg


def _classify(file_path: str, cfg: Dict[str, Any], workspace: Path) -> Optional[str]:
    """Return 'test' if file matches test_glob, 'source' if source_glob, else None."""
    test_glob = cfg.get("test_glob") or []
    source_glob = cfg.get("source_glob") or []
    if match_glob(file_path, test_glob, workspace, empty_returns=False):
        return "test"
    if match_glob(file_path, source_glob, workspace, empty_returns=False):
        return "source"
    return None


def _read_state(workspace: Path) -> Dict[str, Any]:
    path = workspace / NUDGE_STATE_REL
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(workspace: Path, state: Dict[str, Any]) -> None:
    atomic_write_json(workspace / NUDGE_STATE_REL, state)


def _is_duplicate_nudge(workspace: Path, file_path: str) -> bool:
    """Suppress nudge if same file was nudged within the TTL window."""
    import time
    state = _read_state(workspace)
    last_path = state.get("file_path")
    last_at = state.get("at", 0)
    now = int(time.time())
    if last_path == file_path and (now - last_at) < NUDGE_TTL_SECONDS:
        return True
    _write_state(workspace, {"file_path": file_path, "at": now})
    return False


def _is_odoo_addon_test(file_path: str) -> bool:
    """Return True iff the test file lives inside an Odoo addon
    (an ancestor directory contains `__manifest__.py`). Toolkit-own tests
    in `templates/` or `tests/` of the agent-toolkit repo are NOT Odoo
    addon tests — they test the framework itself and don't import
    `odoo.tests.common`. Skipping ADR-003 quality warnings for them
    avoids noisy false-positives on the toolkit's own test suite.
    """
    try:
        cursor = Path(file_path).resolve().parent
        # Walk up to FS root looking for __manifest__.py.
        while True:
            if (cursor / "__manifest__.py").exists():
                return True
            if cursor.parent == cursor:
                return False
            cursor = cursor.parent
    except OSError:
        return False


def _check_test_quality(file_path: str) -> List[str]:
    """ADR-003 check: test file phải dùng dữ liệu thật + ORM call.

    Trả về danh sách warning (rỗng nếu file OK). Đọc nội dung file trực
    tiếp — chấp nhận false-positive nhẹ vì chỉ là nudge, không block.
    Bỏ qua hoàn toàn nếu file không nằm trong Odoo addon (toolkit-own
    tests, generic Python tests) — ADR-003 chỉ áp cho Odoo addon tests.
    """
    warns: List[str] = []
    if not _is_odoo_addon_test(file_path):
        return warns
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return warns

    if not re.search(r"from\s+odoo\.tests(\.common)?\s+import|@odoo\.tests\.tagged", content):
        warns.append(
            "thiếu `from odoo.tests.common import ...` — test không kế thừa "
            "TransactionCase/SavepointCase/HttpCase → có thể đang test mock object"
        )

    if not re.search(r"self\.env\[|self\.env\.|\.search\(|\.browse\(|\.create\(", content):
        warns.append(
            "không phát hiện ORM call thật (`self.env[...]`, `.search(`, `.browse(`, "
            "`.create(`) — test mock-only vi phạm ADR-003 (test phải dùng dữ liệu thật)"
        )

    return warns


def _nudge_test_file(file_path: str) -> str:
    base = (
        f"[tdd-runner] File test vừa được Edit/Write: `{file_path}`.\n"
        "Trước khi sửa code nguồn, CHẠY test này để chắc nó FAIL như mong đợi (RED phase):\n"
        "  - Ưu tiên MCP: `mcp__<stack>-<version>__run_python_tests` với path trên.\n"
        "  - Fallback: Bash `pytest <path> -x` (cần venv hoạt động).\n"
        "Nếu test PASS ngay → có thể anh đang test behaviour đã tồn tại → review lại "
        "ý nghĩa test. Nếu test FAIL với AssertionError/AttributeError/KeyError → đúng "
        "RED phase, sang GREEN (viết code tối thiểu để pass)."
    )

    warns = _check_test_quality(file_path)
    if warns:
        warn_block = (
            "\n\n⚠ ADR-003 check (test real-data + regression):\n"
            + "\n".join(f"  · {w}" for w in warns)
            + "\nXem `.agent-toolkit/decision-log.md#ADR-003` để biết WHY. "
            "Sửa test trước khi sang GREEN."
        )
        base += warn_block

    base += "\nTắt nhắc này: `/tdd off`."
    return base


def _nudge_source_file(file_path: str) -> str:
    return (
        f"[tdd-runner] File nguồn vừa được Edit/Write: `{file_path}`.\n"
        "TDD phase: chạy test liên quan để confirm GREEN (test pre-existing vẫn pass, "
        "test mới nếu có cũng pass):\n"
        "  - Tìm test file: `tests/test_<model>.py` cùng module, hoặc grep test name "
        "matching method anh vừa sửa.\n"
        "  - Chạy: MCP `run_python_tests` hoặc `pytest -x` trên test file đó.\n"
        "Nếu chưa có test cho behaviour vừa thay đổi → cân nhắc viết test trước "
        "(RED) rồi sửa code (GREEN) — đọc skill `<stack>-<version>-tdd`.\n"
        "Tắt nhắc này: `/tdd off`."
    )


def _run_mode(file_path: str, cfg: Dict[str, Any], kind: str) -> str:
    cmd_template = cfg.get("test_command") or "python -m pytest -x"
    # naive split — DEV controls the config string
    target = file_path if kind == "test" else _guess_test_for_source(file_path)
    if not target or not Path(target).exists():
        return (
            f"[tdd-runner mode=run] {file_path} edited, nhưng không tìm được test file "
            f"tương ứng để chạy. Switch lại mode `nudge` (chỉ nhắc, không chạy)."
        )
    cmd_parts = shlex.split(cmd_template) + [target]
    try:
        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
            cwd=str(Path(file_path).parent),
        )
    except subprocess.TimeoutExpired:
        return f"[tdd-runner mode=run] Test timeout sau {RUN_TIMEOUT_SECONDS}s: {target}"
    except (OSError, FileNotFoundError) as exc:
        return f"[tdd-runner mode=run] Không chạy được test_command `{cmd_template}`: {exc}"

    tail_lines = (result.stdout + "\n" + result.stderr).splitlines()[-20:]
    tail = "\n".join(tail_lines)
    status = "PASS" if result.returncode == 0 else f"FAIL (exit {result.returncode})"
    return (
        f"[tdd-runner mode=run] {target} → {status}\n"
        f"```\n{tail}\n```"
    )


def _guess_test_for_source(source_path: str) -> Optional[str]:
    """Heuristic: from `<addons>/<mod>/models/foo.py` → `<addons>/<mod>/tests/test_foo.py`."""
    p = Path(source_path)
    # Walk up until we find a directory that has a `tests/` sibling.
    cursor = p.parent
    for _ in range(5):
        candidate_dir = cursor / "tests"
        if candidate_dir.is_dir():
            for prefix in ("test_", ""):
                cand = candidate_dir / f"{prefix}{p.stem}.py"
                if cand.exists():
                    return str(cand)
            # Generic fallback
            return None
        cursor = cursor.parent
    return None


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

    kind = _classify(file_path, cfg, workspace)
    if not kind:
        _exit_silent()

    if _is_duplicate_nudge(workspace, file_path):
        _exit_silent()

    mode = (cfg.get("mode") or "nudge").lower()
    if mode == "run":
        text = _run_mode(file_path, cfg, kind)
    else:
        text = _nudge_test_file(file_path) if kind == "test" else _nudge_source_file(file_path)

    _emit(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
