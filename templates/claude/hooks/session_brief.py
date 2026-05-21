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

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))
from _common import wrap_utf8_stdio, run_main_safe  # noqa: E402

wrap_utf8_stdio()


MAX_INVARIANTS = 6
MAX_ADRS = 3
MAX_OUTPUT_CHARS = 2100  # +600 headroom for autonomy + audit-lock banners

AUTONOMY_REL = ".agent-toolkit/.autonomy_active.json"

# Lock-file glob used by code-review/SKILL.md Section 0. The skill is on
# the honor system to apply Section 0; surfacing the file count here is
# the SessionStart enforcement nudge so the agent CAN'T plausibly miss it.
_LOCK_GLOB = ".codex/audit_findings*_locked.md"


def _format_autonomy(workspace: Path) -> str:
    """Render the AUTONOMY banner if `.autonomy_active.json` exists + not expired.

    Load-bearing signal for the classifier — without this banner, each
    prompt is read in isolation and dangerous-but-approved ops (kill
    process, drop test table, ...) are refused. See ADR-002.

    Returns "" when: file missing / expired / malformed.
    """
    path = workspace / AUTONOMY_REL
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""

    from datetime import datetime, timezone, timedelta
    expires_str = data.get("expires_at") or ""
    spec = data.get("spec") or "<unknown>"
    scopes = data.get("scopes") or []
    blocked = data.get("still_blocked") or []

    # Parse expires_at as timezone-aware when possible.
    #
    # Real-world bug caught 2026-05-18: `/go` command wrote `expires_at` using
    # `date -u +...+0700` which produced UTC time stamped with `+0700` tz
    # suffix — these are inconsistent (the time IS UTC but suffix claims
    # +0700). Previous parser stripped the tz suffix and treated as naive
    # local → false-expired banner. Fix: parse tz-aware when suffix present,
    # convert to local for comparison.
    expires_dt = None
    if expires_str:
        # Try fromisoformat first (Python 3.7+ handles `+HH:MM` aware,
        # but not `+HHMM` without colon — normalize first).
        normalized = expires_str.strip()
        # Insert colon into bare offset like `+0700` -> `+07:00` for fromisoformat.
        import re as _re
        normalized = _re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", normalized)
        try:
            expires_dt = datetime.fromisoformat(normalized)
        except (ValueError, TypeError):
            # Fallback: strip tz suffix + strptime as naive (legacy behavior).
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
                try:
                    expires_dt = datetime.strptime(
                        expires_str.split(".")[0].split("+")[0].split("Z")[0],
                        fmt,
                    )
                    break
                except ValueError:
                    continue

    now = datetime.now()
    if expires_dt is not None and expires_dt.tzinfo is not None:
        # Aware comparison — use local-aware now.
        now = datetime.now().astimezone()
        if now.tzinfo is None:
            # Fallback: convert expires to naive UTC then subtract from naive
            # local — best-effort if astimezone fails (no system tz info).
            expires_dt = expires_dt.replace(tzinfo=None)
            now = datetime.now()

    if expires_dt and now > expires_dt:
        return ""

    remaining = ""
    if expires_dt:
        delta = expires_dt - now
        hours = int(delta.total_seconds() // 3600)
        mins = int((delta.total_seconds() % 3600) // 60)
        remaining = f" · còn {hours}h{mins:02d}m" if hours else f" · còn {mins}m"

    scopes_str = ", ".join(scopes[:3]) + ("…" if len(scopes) > 3 else "")
    blocked_str = ", ".join(blocked[:3])

    return (
        f"🚀 **AUTONOMY ON** · spec=`{spec}`{remaining}\n"
        f"  · Approved scopes: {scopes_str}\n"
        f"  · Always blocked: {blocked_str}\n"
        f"  · Agent được tự do trong scopes — DEV đã approve qua `/go`. "
        f"Cắt sớm: `/stop-autonomy`. (Vẫn dưới `invariant-guard` + "
        f"`evidence-audit` + `debug-sentry`.)"
    )


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _format_audit_locks(workspace: Path) -> str:
    """Surface any `.codex/audit_findings*_locked.md` files at SessionStart.

    Lock files are the canonical recount source for code-review/SKILL.md
    Section 0 (lock-file precedence). Without this banner the agent can
    silently skip Section 0 and produce a fresh count that contradicts
    the locked one — the "recount drift" we saw before.
    """
    codex = workspace / ".codex"
    if not codex.is_dir():
        return ""
    locks = sorted(codex.glob("audit_findings*_locked.md"))
    if not locks:
        return ""
    lines = [
        "🔒 **Audit lock-files present** — apply `code-review/SKILL.md` "
        "Section 0 (Lock-file precedence) BEFORE any new review work:"
    ]
    for lock in locks[:5]:  # cap at 5 entries
        try:
            head = lock.read_text(encoding="utf-8-sig").splitlines()[:6]
        except OSError:
            head = []
        # Best-effort: extract a count-looking line if present.
        summary = next(
            (l.strip() for l in head if re.search(r"\d+\s*(BLOCKER|MEDIUM|LOW)", l, re.IGNORECASE)),
            "",
        )
        rel = lock.relative_to(workspace).as_posix()
        if summary:
            lines.append(f"- `{rel}` — {summary}")
        else:
            lines.append(f"- `{rel}`")
    if len(locks) > 5:
        lines.append(f"- … +{len(locks) - 5} more")
    lines.append(
        "  → Cite the recorded count verbatim. Only diverge with "
        "reproducible PROOF (Section 0 rule 2)."
    )
    return "\n".join(lines)


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


def _read_hook_stats(workspace: Path) -> Dict[str, Any]:
    """Read recent telemetry events from .codex/logs/hook_events.jsonl
    and return aggregate stats. Returns empty if log missing."""
    log_path = workspace / ".codex" / "logs" / "hook_events.jsonl"
    if not log_path.exists():
        return {}
    try:
        with log_path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return {}
    recent = lines[-200:]
    total = 0
    blocked = 0
    bypassed = 0
    by_category: Dict[str, int] = {}
    for line in recent:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        if (evt.get("decision") or "") == "block":
            blocked += 1
        if evt.get("bypass"):
            bypassed += 1
        for cat in evt.get("categories") or []:
            by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": total,
        "blocked": blocked,
        "bypassed": bypassed,
        "by_category": by_category,
    }


def _format_hook_stats(stats: Dict[str, Any]) -> str:
    if not stats or not stats.get("total"):
        return ""
    total = stats["total"]
    blocked = stats.get("blocked", 0)
    bypassed = stats.get("bypassed", 0)
    block_rate = (blocked / total * 100) if total else 0
    top_cats = sorted(
        (stats.get("by_category") or {}).items(),
        key=lambda kv: kv[1], reverse=True,
    )[:3]
    cat_str = ", ".join(f"{c}={n}" for c, n in top_cats) if top_cats else "(none)"
    return (
        f"**Hook health** (last {total} events): "
        f"{blocked} block ({block_rate:.0f}%), {bypassed} bypass · top: {cat_str}"
    )


def _build_brief(workspace: Path) -> str:
    cfg = _load_json(workspace / "agent-toolkit.config.json")
    invariants_data = _load_json(workspace / ".agent-toolkit" / "invariants.json")
    invariants = [i for i in (invariants_data.get("invariants") or []) if isinstance(i, dict)]
    probes_data = _load_json(workspace / ".agent-toolkit" / "acceptance-probes.json")
    probes_count = len([p for p in (probes_data.get("probes") or []) if isinstance(p, dict)])
    hook_stats = _read_hook_stats(workspace)

    decision_log = ""
    log_path = workspace / ".agent-toolkit" / "decision-log.md"
    if log_path.exists():
        try:
            decision_log = log_path.read_text(encoding="utf-8-sig")
        except OSError:
            decision_log = ""

    sections: List[str] = ["[project-brief]"]
    stack = _format_stack(cfg)
    if stack:
        sections.append(stack)

    # ADR-002: AUTONOMY banner — placed BEFORE invariants so it's the most
    # prominent signal in every turn the flag is active. The classifier reads
    # from the top of the SessionStart additional context.
    autonomy = _format_autonomy(workspace)
    if autonomy:
        sections.append(autonomy)

    # Audit lock-files surface — same prominence tier as autonomy, since
    # code-review/SKILL.md Section 0 is honor-system without it.
    audit_locks = _format_audit_locks(workspace)
    if audit_locks:
        sections.append(audit_locks)

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
        f"Registry loaded: {len(invariants)} invariant · {probes_count} probe. "
        "See `.agent-toolkit/README.md` for the contract."
    )
    stats_line = _format_hook_stats(hook_stats)
    if stats_line:
        sections.append(stats_line)
    out = "\n\n".join(sections)
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[: MAX_OUTPUT_CHARS - 3] + "…"
    return out


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0

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
    sys.exit(run_main_safe(main))
