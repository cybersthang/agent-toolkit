#!/usr/bin/env python
"""SessionStart hook — inject a short project brief so the agent sees
active invariants + recent decisions on every fresh conversation.

Reads (all optional):
- `<workspace>/agent-toolkit.config.json` — stack/preset info from installer.
- `<workspace>/.agent-toolkit/invariants.json` — durable rules enforced by
  invariant_guard hook.
- `<workspace>/.agent-toolkit/decision-log.md` — ADR-style decision log
  (last 3 entries surfaced).

Output is capped at ~1500 chars to stay cheap on every session.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


MAX_INVARIANTS = 6
MAX_ADRS = 3
MAX_OUTPUT_CHARS = 1500


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _format_invariants(invariants: List[Dict[str, Any]]) -> str:
    if not invariants:
        return ""
    lines = ["**Active invariants** (enforced by `invariant-guard` PreToolUse hook):"]
    for inv in invariants[:MAX_INVARIANTS]:
        sev = (inv.get("severity") or "warn").upper()
        marker = "🛑" if sev == "BLOCKER" else "⚠"
        applies = inv.get("applies_to") or []
        applies_str = ", ".join(applies[:3]) + ("…" if len(applies) > 3 else "")
        lines.append(
            f"- {marker} `{inv.get('id', '?')}` ({sev}) — {inv.get('description', '')}"
            + (f"  · scope: `{applies_str}`" if applies_str else "")
        )
    if len(invariants) > MAX_INVARIANTS:
        lines.append(f"- … +{len(invariants) - MAX_INVARIANTS} more in `.agent-toolkit/invariants.json`")
    return "\n".join(lines)


def _format_recent_adrs(decision_log: str) -> str:
    if not decision_log:
        return ""
    # Strip everything before the "Add new ADRs BELOW this line" marker
    # so template/doc-example headers don't get parsed as real ADRs.
    marker = "Add new ADRs BELOW this line"
    if marker in decision_log:
        decision_log = decision_log.split(marker, 1)[1]
    # Match real ADRs only: `## ADR-<digits>:` — three-digit numeric
    # IDs distinguish them from the schema example `## ADR-NNN:`.
    matches = list(re.finditer(r"^## ADR-(\d{3,}):\s*(.+)$", decision_log, re.MULTILINE))
    if not matches:
        return ""
    bodies: List[Tuple[str, str, str]] = []  # (id, title, status)
    for idx, m in enumerate(matches):
        adr_id = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(decision_log)
        body = decision_log[start:end]
        status_m = re.search(r"^\s*-\s*\*\*Status\*\*:\s*(.+)$", body, re.MULTILINE)
        status = f" [{status_m.group(1).strip()}]" if status_m else ""
        bodies.append((adr_id, title, status))
    recent = bodies[-MAX_ADRS:]
    lines = ["**Recent decisions** (`.agent-toolkit/decision-log.md`):"]
    for adr_id, title, status in recent:
        lines.append(f"- ADR-{adr_id}: {title}{status}")
    return "\n".join(lines)


def _format_stack(cfg: Dict[str, Any]) -> str:
    if not cfg:
        return ""
    stack = cfg.get("stack") or {}
    bits = []
    if cfg.get("project_name"):
        bits.append(f"**Project**: {cfg['project_name']}")
    label = stack.get("label") or cfg.get("preset")
    if label:
        bits.append(f"**Stack**: {label}")
    if cfg.get("response_language") and cfg["response_language"].lower() != "english":
        bits.append(f"**Reply language**: {cfg['response_language']}")
    return " · ".join(bits)


def _build_brief(workspace: Path) -> str:
    cfg = _load_json(workspace / "agent-toolkit.config.json")
    invariants_data = _load_json(workspace / ".agent-toolkit" / "invariants.json")
    invariants = [i for i in (invariants_data.get("invariants") or []) if isinstance(i, dict)]

    decision_log = ""
    log_path = workspace / ".agent-toolkit" / "decision-log.md"
    if log_path.exists():
        try:
            decision_log = log_path.read_text(encoding="utf-8")
        except OSError:
            decision_log = ""

    sections: List[str] = ["[project-brief]"]
    stack = _format_stack(cfg)
    if stack:
        sections.append(stack)

    inv = _format_invariants(invariants)
    if inv:
        sections.append(inv)
    else:
        sections.append(
            "_No invariants registered yet. Use `/inv-add` when the user makes "
            "a durable rule (e.g. 'always sort list X by type')._"
        )

    adrs = _format_recent_adrs(decision_log)
    if adrs:
        sections.append(adrs)

    sections.append(
        "**Enforcement active**: `invariant-guard` (PreToolUse), "
        "`evidence-audit` (Stop), `intent-router` (UserPromptSubmit). "
        "See `.agent-toolkit/README.md` for the contract."
    )
    out = "\n\n".join(sections)
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[: MAX_OUTPUT_CHARS - 3] + "…"
    return out


def main() -> int:
    raw = sys.stdin.read()
    envelope: Dict[str, Any] = {}
    if raw.strip():
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            envelope = {}

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    brief = _build_brief(workspace)
    if not brief.strip():
        return 0

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": brief,
        }
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
