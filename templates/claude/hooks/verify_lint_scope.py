#!/usr/bin/env python
"""Stop hook — Layer 5 file-level scope creep check at /verify time.

Complements existing `verify_lint.py` (which checks acceptance_eval
coverage). This hook checks SCOPE compliance:

  Files actually modified during `/implement <slug>` (via snapshot
  diff) MUST be within the union of:
    - spec.affected_modules prefixes
    - implement-noted SD-N file references with valid Spec linkage
    - `scope-creep-allowed: <file> <reason>` bypass markers
       in the assistant response

Verdict:
  - Clean → allow Stop (silent).
  - Issues + enforce=warn → emit additionalContext (warn-only).
  - Issues + enforce=block → emit decision=block.

Config: `<workspace>/.agent-toolkit/scope_audit.json`
  {"enabled": true, "enforce": "warn"}

Bypass marker single-shot: `scope-creep-allowed: <file> <reason>` in
the response → that file exempt for this Stop.

Universal kill-switch: `AGENT_TOOLKIT_DISABLE=1`.

Fails open: any error → exit 0 silent.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, read_jsonl_transcript, split_current_turn,
    run_main_safe, emit_fire_event,
)

wrap_utf8_stdio()


CONFIG_REL = ".agent-toolkit/scope_audit.json"
SNAPSHOT_TOOL_REL = ".codex/tools/implement_snapshot.py"
MISSING_DETECTOR_REL = ".codex/tools/missing_sd_detector.py"

TRUNK_BRANCHES = {"main", "master", "trunk", "develop"}

VERIFY_REPORT_RE = re.compile(
    r"(?im)^\s*#+\s*verify\s+report\b",
)
DONE_CLAIM_RE = re.compile(
    r"\b(implement\s+done|implement\s+xong|sprint\s+(?:hoàn\s*tất|done|complete)"
    r"|feature\s+ready\s+for\s+(?:review|/verify))\b",
    re.IGNORECASE,
)
BYPASS_RE = re.compile(
    r"scope-creep-allowed\s*:\s*(\S+)", re.IGNORECASE,
)
SLUG_HINT_RE = re.compile(
    r"(?:Verify\s+Report\s*[-—]\s*|spec\s*:\s*\.?agent-toolkit/specs/[^/]+/)([A-Za-z0-9.\-]+)",
)


def _exit_allow() -> None:
    sys.exit(0)


def _emit_warn(message: str) -> None:
    # Phase C v0.9.1: fire event capture
    try:
        emit_fire_event("verify_lint_scope.py", verdict="warn")
    except Exception:
        pass
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _emit_block(reason: str) -> None:
    try:
        emit_fire_event("verify_lint_scope.py", verdict="block")
    except Exception:
        pass
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _load_config(workspace: Path) -> Dict[str, Any]:
    p = workspace / CONFIG_REL
    cfg: Dict[str, Any] = {"enabled": True, "enforce": "warn"}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                cfg.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _resolve_branch(workspace: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        if proc.returncode == 0:
            out = (proc.stdout or "").strip()
            if out and out != "HEAD":
                return out
        proc2 = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5,
        )
        if proc2.returncode == 0:
            return (proc2.stdout or "").strip()
        return ""
    except (subprocess.SubprocessError, OSError):
        return ""


def _branch_to_slug(branch: str) -> str:
    if "/" in branch:
        return branch.rsplit("/", 1)[1]
    return branch


def _extract_assistant_text(turn: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for msg in turn:
        if (msg.get("role") or msg.get("type")) != "assistant":
            continue
        content = (msg.get("message") or {}).get("content") or msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    parts.append(b.get("text") or "")
    return "\n".join(parts)


def _infer_slug(asst_text: str, fallback: str) -> str:
    m = SLUG_HINT_RE.search(asst_text)
    if m:
        return m.group(1)
    return fallback


def _extract_bypass(asst_text: str) -> Set[str]:
    return {m.group(1).replace("\\", "/") for m in BYPASS_RE.finditer(asst_text)}


def _run_missing_detector(workspace: Path, slug: str) -> Dict[str, Any]:
    tool = workspace / MISSING_DETECTOR_REL
    if not tool.exists():
        return {"error": "missing-sd-detector-not-found"}
    try:
        proc = subprocess.run(
            [sys.executable, str(tool), slug,
             "--workspace", str(workspace), "--json"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        return json.loads(proc.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        return {"error": f"detector-invocation-failed: {e}"}


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

    cfg = _load_config(workspace)
    if not cfg.get("enabled"):
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
    asst_text = _extract_assistant_text(turn)
    if not asst_text:
        _exit_allow()

    # Only trigger on Verify Report or "implement done" style turns.
    if not (VERIFY_REPORT_RE.search(asst_text) or DONE_CLAIM_RE.search(asst_text)):
        _exit_allow()

    branch = _resolve_branch(workspace)
    if not branch or branch in TRUNK_BRANCHES:
        _exit_allow()
    branch_slug = _branch_to_slug(branch)
    slug = _infer_slug(asst_text, branch_slug)

    result = _run_missing_detector(workspace, slug)
    if "error" in result:
        _exit_allow()

    if result.get("verdict") == "clean":
        _exit_allow()

    missing = result.get("missing_files") or []
    if not missing:
        _exit_allow()

    # Apply bypass markers
    bypass = _extract_bypass(asst_text)
    missing_filtered = [f for f in missing if f.replace("\\", "/") not in bypass]
    if not missing_filtered:
        _exit_allow()

    sample = missing_filtered[:5]
    remainder = len(missing_filtered) - len(sample)
    lines = [
        f"[verify-lint-scope] Scope creep detected for slug `{slug}`:",
        "",
        "Files modified but not declared in spec.affected_modules / SD-N / bypass:",
    ]
    for f in sample:
        lines.append(f"  - {f}")
    if remainder > 0:
        lines.append(f"  ... +{remainder} more")
    lines.extend([
        "",
        "Resolve by ONE of:",
        "  (a) Add the file path prefix to spec frontmatter `affected_modules`.",
        "  (b) Declare an SD-N entry in implement-noted.md with valid Spec linkage.",
        "  (c) Add `scope-creep-allowed: <file> <reason>` token to this response (single-shot).",
    ])
    message = "\n".join(lines)

    enforce = (cfg.get("enforce") or "warn").lower()
    if enforce == "block":
        _emit_block(message)
    else:
        _emit_warn(message)
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
