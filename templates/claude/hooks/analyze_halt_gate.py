#!/usr/bin/env python
"""PreToolUse hook — block Edit/Write/MultiEdit on source files while an
unresolved HALT verdict exists in any `.agent-toolkit/specs/**/analyze-report.md`.

Closes the enforcement gap identified in code review 2026-05-19: previously
`analyze-artifacts/SKILL.md` Step 4 said "Any BLOCK → return verdict HALT.
Auto-chain stops here." but no hook enforced it. The agent (or a fresh
context) could skip /analyze entirely or ignore a HALT verdict and proceed
to Edit source files, defeating the drift gate.

Now: every Edit/Write/MultiEdit/NotebookEdit on a non-toolkit path triggers
this hook. If ANY analyze-report.md under .agent-toolkit/specs/ contains a
HALT verdict, the tool call is BLOCKED with the slug, blocker list, and
resolution paths.

Resolution paths (in order of preference):
  1. Fix the listed C<n> blockers, re-run `/analyze <slug>`. The new report
     overwrites the HALT one; on next Edit attempt this hook fail-opens.
  2. If the spec itself is wrong, run `/clarify <slug>` to refine — the
     subsequent `/analyze` will (hopefully) emit READY.
  3. DEV emergency bypass: `touch .agent-toolkit/.analyze-bypass`. The
     marker is persistent — every Edit/Write while it exists prints a
     stderr diagnostic and allows the call. Delete the marker after use;
     the hook does NOT auto-delete it (intentional: a one-shot bypass
     fails open if the DEV is mid-burst of edits).

Allow-list (never blocked, even with active HALT):
  - .agent-toolkit/**  (spec / tasks / analyze-report artifacts)
  - .codex/**          (canonical_decisions, MCP, registry)
  - .claude/**         (hooks, commands, settings)
  - .cursor/**         (rules, skills, mcp.json)

This lets the agent emit the corrected analyze-report.md, fix the spec, or
adjust hook configuration without tripping its own gate.

Exit codes
----------
  0 — allow (no active HALT, or path is allow-listed, or bypass marker present)
  Any non-zero JSON-encoded `{decision: "block", reason: ...}` blocks the tool.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from _common import wrap_utf8_stdio, find_workspace_root  # noqa: E402

wrap_utf8_stdio()


# Verdict regex — matches the canonical form emitted by analyze-artifacts/SKILL.md
# Step 3 ("**Verdict:** HALT — ..." or "Verdict: BLOCK ..."). Case-insensitive
# so a sloppy agent that writes "verdict: halt" still trips the gate.
_VERDICT_HALT_RE = re.compile(
    r"\bverdict\s*[:\*]*\s*(HALT|BLOCK)\b",
    re.IGNORECASE,
)

# Fallback: count > 0 in the "🔴 BLOCK: N" summary row. Catches reports
# where the agent forgot to render the explicit verdict line.
_BLOCK_COUNT_RE = re.compile(
    r"(?:🔴\s*)?BLOCK\s*:\s*([1-9]\d*)",
    re.UNICODE,
)

# Resolution path detection — if the report contains "Verdict: READY"
# anywhere we treat HALT as overridden (agent may have re-emitted in same
# file with both old and new sections). The LAST verdict line wins.
_VERDICT_LINE_RE = re.compile(
    r"\bverdict\s*[:\*]*\s*(HALT|BLOCK|READY(?:-with-warnings)?)\b",
    re.IGNORECASE,
)

_ALLOWLIST_PARTS = (".agent-toolkit", ".codex", ".claude", ".cursor")
_BYPASS_MARKER = ".analyze-bypass"


def _exit_allow() -> None:
    sys.exit(0)


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def _path_is_allowlisted(file_path: str, workspace: Path) -> bool:
    """True if file_path lives inside a toolkit-managed directory."""
    if not file_path:
        return False
    try:
        rel = Path(file_path).resolve().relative_to(workspace.resolve())
    except ValueError:
        # Path outside workspace (rare — Edit on absolute path elsewhere).
        # Don't block; not our scope.
        return True
    parts = rel.parts
    if not parts:
        return False
    return parts[0] in _ALLOWLIST_PARTS


def _final_verdict(text: str) -> Optional[str]:
    """Return the LAST verdict line value in the report text, uppercased.

    Multiple verdict lines can appear if the agent appended a re-analysis
    to the same file; we honor the most recent one. None if no verdict
    line is found.
    """
    matches = _VERDICT_LINE_RE.findall(text)
    if not matches:
        return None
    return matches[-1].upper()


def _is_halted(text: str) -> bool:
    """Decide whether the report's effective verdict is HALT."""
    last = _final_verdict(text)
    if last is not None:
        return last in ("HALT", "BLOCK")
    # Fallback: row-count form.
    m = _BLOCK_COUNT_RE.search(text)
    if m and int(m.group(1)) > 0:
        return True
    return False


def _find_active_halts(workspace: Path) -> List[Tuple[Path, str]]:
    """Scan every `analyze-report.md` under .agent-toolkit/specs/.

    Returns a list of (report_path, slug) for reports with active HALT.
    Empty list if none.
    """
    specs_dir = workspace / ".agent-toolkit" / "specs"
    if not specs_dir.is_dir():
        return []
    halts: List[Tuple[Path, str]] = []
    for report in specs_dir.rglob("analyze-report.md"):
        try:
            text = report.read_text(encoding="utf-8")
        except OSError:
            continue
        if _is_halted(text):
            # Slug = parent dir name in branch-scoped layout.
            slug = report.parent.name
            halts.append((report, slug))
    return halts


def _extract_blockers(text: str, limit: int = 5) -> List[str]:
    """Pull the table rows marked 🔴 BLOCK for the block reason summary."""
    out: List[str] = []
    # Match table rows: `| C6 | Path realism | 🔴 BLOCK | T4 cites ... |`
    row_re = re.compile(
        r"\|\s*(C\d+)\s*\|\s*([^|]+?)\s*\|\s*🔴?\s*BLOCK\s*\|\s*([^|]+?)\s*\|",
        re.UNICODE,
    )
    for m in row_re.finditer(text):
        check_id, check_name, detail = m.group(1), m.group(2).strip(), m.group(3).strip()
        out.append(f"{check_id} ({check_name}): {detail}")
        if len(out) >= limit:
            break
    return out


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        _exit_allow()

    raw = sys.stdin.read()
    if not raw.strip():
        _exit_allow()
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        _exit_allow()

    # Tool input — what file is being edited?
    tool_input = envelope.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""

    workspace_str = (
        envelope.get("cwd")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.getcwd()
    )
    workspace = find_workspace_root(Path(workspace_str)) or Path(workspace_str).resolve()

    # Allowlist: toolkit-managed dirs are always editable (agent must be
    # able to emit the corrected analyze-report.md, fix the spec, etc.).
    if _path_is_allowlisted(file_path, workspace):
        _exit_allow()

    halts = _find_active_halts(workspace)
    if not halts:
        _exit_allow()

    # Emergency bypass marker — persistent; emits stderr diagnostic each
    # Edit until DEV deletes the marker file (no auto-delete on purpose).
    bypass = workspace / ".agent-toolkit" / _BYPASS_MARKER
    if bypass.exists():
        # Print to stderr so DEV sees the diagnostic but the tool runs.
        slugs = ", ".join(slug for _, slug in halts)
        sys.stderr.write(
            f"[analyze-halt-gate] BYPASS active — {len(halts)} HALT report(s) "
            f"for slug(s): {slugs}. Delete .agent-toolkit/.analyze-bypass "
            f"when done.\n"
        )
        _exit_allow()

    # Compose block reason.
    primary = halts[0]
    report_path, slug = primary
    blockers = _extract_blockers(report_path.read_text(encoding="utf-8"))
    blocker_text = "\n  - ".join(blockers) if blockers else "<no rows parsed>"

    extras = ""
    if len(halts) > 1:
        other_slugs = ", ".join(s for _, s in halts[1:])
        extras = (
            f"\n\nNote: {len(halts) - 1} other HALT report(s) also active: "
            f"{other_slugs}."
        )

    _emit_block(
        f"[analyze-halt-gate] /analyze emitted HALT for spec `{slug}`. "
        f"Edit/Write on source files is blocked until verdict is resolved.\n\n"
        f"Blockers:\n  - {blocker_text}\n\n"
        f"Report: {report_path.relative_to(workspace).as_posix()}\n\n"
        f"Resolve by one of:\n"
        f"  1) Fix the C<n> blockers above, then re-run `/analyze {slug}`.\n"
        f"  2) If spec-level drift, run `/clarify {slug}` then `/analyze {slug}`.\n"
        f"  3) DEV emergency only: `touch .agent-toolkit/.analyze-bypass` "
        f"(does not auto-expire — delete after use).{extras}"
    )


if __name__ == "__main__":
    sys.exit(main())
