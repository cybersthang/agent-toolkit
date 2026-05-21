#!/usr/bin/env python
"""PostToolUse hook — SAFETY NET for missing probes after feature-scope edits.

CHANGED behavior (per DEV directive 2026-05-18):
  Old: auto-stub probe entry with `_stub: true` + TODO fields (forced DEV
       to manually fill TODOs afterward).
  New: detect new feature in Edit/Write. Check if a probe already covers
       this path. If YES (agent wrote probe from grill-captured params)
       → silent OK. If NO → emit STERN warning that grill phase failed
       to capture probe params, telling agent to GO BACK TO DEV and ask
       the missing PROBE_READINESS questions before continuing.

  → Hook never writes TODOs anymore. Either agent has done the right
    thing (probe registered with full params) → hook stays quiet, OR
    agent shipped feature without grill capture → hook flags it loudly.

Trigger: after Edit/Write/MultiEdit on a feature-scope file.

Detection patterns mirror `.codex/precommit_hooks/feature_probe_suggest.py`:
  - `@http.route(...)` → HTTP feature
  - `def <name>(self, ...)` in feature-scope file → method feature
  - `@api.depends` / `@api.constrains` → consistency feature

Fails open: silent on any error. Honors AGENT_TOOLKIT_DISABLE.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import wrap_utf8_stdio, run_main_safe  # noqa: E402

wrap_utf8_stdio()


PROBES_REL = ".agent-toolkit/acceptance-probes.json"
COVERAGE_REL = ".agent-toolkit/coverage_config.json"


# Detection patterns. Each yields (probe_kind, identifier, line_pattern_for_runner).
def _detect_new_features(new_text: str, old_text: str) -> List[Tuple[str, str, str]]:
    """Return list of (kind, ident, line_pattern). Only flags content
    PRESENT in new_text but NOT in old_text (genuine additions)."""
    added: List[Tuple[str, str, str]] = []

    def _new_only(pat: str, flags: int = 0) -> List[re.Match]:
        new_matches = list(re.finditer(pat, new_text, flags))
        old_set = {m.group(0) for m in re.finditer(pat, old_text, flags)}
        return [m for m in new_matches if m.group(0) not in old_set]

    # HTTP route
    for m in _new_only(r"@http\.route\((['\"])([^'\"]+)\1"):
        route = m.group(2)
        line_pat = re.escape(m.group(0))
        added.append(("http_route", route, line_pat))

    # Controller method (def <name>(self...))
    for m in _new_only(r"def\s+([a-z_][a-zA-Z0-9_]*)\s*\(self"):
        name = m.group(1)
        # Skip private + dunder
        if name.startswith("_"):
            continue
        line_pat = rf"def\s+{re.escape(name)}\\("
        added.append(("controller_method", name, line_pat))

    # @api.depends / @api.constrains
    for m in _new_only(r"@api\.(depends|constrains)\("):
        kind = m.group(1)
        added.append(("api_" + kind, kind, ""))

    return added


def _load_probes(workspace: Path) -> Dict[str, Any]:
    path = workspace / PROBES_REL
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_coverage_config(workspace: Path) -> Dict[str, Any]:
    path = workspace / COVERAGE_REL
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _path_matches_feature(file_path: str, feature_globs: List[str]) -> bool:
    if not feature_globs:
        return False
    rel = file_path.replace("\\", "/")
    for g in feature_globs:
        if fnmatch.fnmatch(rel, g.replace("\\", "/")):
            return True
    return False


def _path_already_covered(file_path_rel: str, probes: List[Dict[str, Any]]) -> bool:
    """Return True if any probe (non-stub) has path_globs that match the
    file path. If agent already wrote a probe from grill-captured params,
    we stay silent."""
    rel = file_path_rel.replace("\\", "/")
    for p in probes:
        if not isinstance(p, dict):
            continue
        # Skip _stub probes — they don't count as "covered"
        if p.get("_stub"):
            continue
        globs = (p.get("applies_when") or {}).get("path_globs") or []
        for g in globs:
            if fnmatch.fnmatch(rel, g.replace("\\", "/")):
                return True
    return False


def _read_text(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


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

    tool_name = envelope.get("tool_name") or ""
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    tool_input = envelope.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    # File path workspace-relative for storage
    try:
        rel_path = str(Path(file_path).resolve().relative_to(workspace)).replace("\\", "/")
    except (ValueError, OSError):
        rel_path = file_path.replace("\\", "/")

    # Check feature scope
    coverage = _load_coverage_config(workspace)
    feature_globs = coverage.get("feature_globs") or []
    if not _path_matches_feature(rel_path, feature_globs):
        return 0

    # Read current file content as new_text
    new_text = _read_text(Path(file_path))
    # Old text approx: for Edit, use tool_input.old_string; for Write,
    # assume empty (new file).
    if tool_name == "Edit":
        old_text = tool_input.get("old_string") or ""
    elif tool_name == "MultiEdit":
        # Concat all old_strings
        old_text = "\n".join(
            e.get("old_string") or ""
            for e in (tool_input.get("edits") or [])
        )
    else:
        old_text = ""

    added = _detect_new_features(new_text, old_text)
    if not added:
        return 0

    registry = _load_probes(workspace)
    probes = registry.get("probes") or []

    # Path already covered by a real (non-stub) probe? Agent wrote it from
    # grill answers — stay silent, this is the happy path.
    if _path_already_covered(rel_path, probes):
        return 0

    # No covering probe exists. Agent's grill phase missed the PROBE_READINESS
    # block, OR agent forgot to register probe after Edit. Emit STERN warning.
    feature_summary = ", ".join(f"{k}:{ident}" for k, ident, _ in added[:3])
    msg_lines = [
        "[probe-autostub] WARNING: you just edited a feature-scope file "
        f"({rel_path}) and added new feature(s) ({feature_summary}), "
        "but NO probe in .agent-toolkit/acceptance-probes.json covers this path.",
        "",
        "This indicates grill phase did NOT capture PROBE_READINESS — "
        "the clarification-gate skill should have asked DEV for:",
        "  - description (semantic claim DEV will accept as 'works')",
        "  - measurement_command (full curl/CLI hitting the new code path)",
        "  - falsification recipe (e.g. time.sleep + expected delta)",
        "  - MCP evidence tool (mcp__realdata_test__* name)",
        "",
        "Action: STOP further implementation. Go back to DEV in a new turn",
        "and ask the missing PROBE_READINESS questions. After DEV answers,",
        "write the FULL probe entry to acceptance-probes.json (no _stub,",
        "no TODO) before continuing.",
        "",
        "If this edit is genuinely test code / fixture / non-feature scope:",
        "add the path to `.agent-toolkit/coverage_config.json` `exempt_globs`.",
    ]
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(msg_lines),
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0



if __name__ == "__main__":
    sys.exit(run_main_safe(main))
