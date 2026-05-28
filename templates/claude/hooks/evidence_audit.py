#!/usr/bin/env python
"""Stop hook entry — wires 3 enforcement layers in priority order:

1. PASS-claim contract (fail-CLOSED): acceptance probes + generic fallback.
2. Hallucinated-progress contract (fail-CLOSED): 5 categories A-E cross-check.
3. Generic claim audit (fail-open via [assumption]).

Detailed logic lives in `_audit/` package modules. This file is the
single entry script wired into `.claude/settings.json`.

Fails open on any unexpected error — better to under-block than to
permanently jam the workflow.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))
from _common import (
    run_main_safe, emit_fire_event, atomic_write_json,
    envelope_protocol_drift_warning,
)

# Make `_audit` package importable when invoked as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent))


# G7 v0.11.0 — recursion guard backup.
#
# Primary recursion break: Claude Code sets `stop_hook_active=True` on
# the envelope when re-invoking us after a block, so we exit cleanly.
# If Anthropic ever renames that field (or strips it from the envelope),
# evidence_audit could loop indefinitely — block → re-prompt → block.
#
# Backup: count Stop events within a short window (`.stop_audit_count.json`,
# 60s rolling) and bail out after `_RECURSION_HARD_CAP` consecutive blocks.
# Independent of envelope shape; trades a bit of clarity for safety.
_RECURSION_STATE_REL = ".agent-toolkit/.stop_audit_count.json"
_RECURSION_WINDOW_SECS = 60
_RECURSION_HARD_CAP = 3

from _audit.claim_audit import (
    find_claims, has_disclaimer, has_evidence,
)
from _audit.pass_contract import (
    DEFAULT_PASS_CLAIM_REGEX, DEFAULT_PASS_EXEMPT_MARKERS, DEFAULT_REQUIRED_TOOL_PREFIXES,
    additional_evidence_satisfied, default_pass_evidence_satisfied,
    discover_required_prefixes, edited_paths_in_turn,
    load_additional_evidence_patterns, load_probes_registry, matching_probes,
    meta_review_mode, pass_claim_present, probe_evidence_satisfied,
    probe_skip_requested,
)
from _audit.progress_checks import (
    ALL_PROGRESS_CHECKS, progress_skip_requested, run_progress_checks,
)
from _audit.reasons import (
    format_generic_claim_reason, format_pass_block_reason, format_progress_block_reason,
)
# v0.23 C1 (two-source) — optional cross-source corroboration layer.
from _audit.cross_source import (
    cross_source_warning, requires_cross_source,
)
from _audit.telemetry import log_event
from _audit.transcript import (
    extract_text_and_tools, extract_tool_results, read_transcript, split_current_turn,
)
from _audit.verify_report import verify_report_probe_spread


# UTF-8 stdin/stdout for Vietnamese identifiers.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _read_recursion_state(workspace: Path) -> Dict[str, Any]:
    """Return {'count': N, 'first_ts': epoch}. Empty dict if missing or stale."""
    import time
    path = workspace / _RECURSION_STATE_REL
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    first_ts = int(data.get("first_ts") or 0)
    if int(time.time()) - first_ts > _RECURSION_WINDOW_SECS:
        # Window expired — fresh slate.
        return {}
    return data


def _bump_recursion_state(workspace: Path, current: Dict[str, Any]) -> int:
    """Increment block counter; return the new count. Resets when window
    expires. Silent on filesystem failure (best-effort safety net)."""
    import time
    now = int(time.time())
    count = int(current.get("count") or 0) + 1
    first_ts = int(current.get("first_ts") or now)
    path = workspace / _RECURSION_STATE_REL
    # v0.21 T02 (H7): atomic write — concurrent crashes can race counter.
    atomic_write_json(path, {
        "count": count, "first_ts": first_ts, "last_ts": now,
    })
    return count


def _clear_recursion_state(workspace: Path) -> None:
    """Clear counter — called when we emit allow (loop broken naturally)."""
    path = workspace / _RECURSION_STATE_REL
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _exit_allow(workspace: Path, reason_categories: List[str] = None, bypass: List[str] = None) -> None:
    log_event(workspace, hook="evidence_audit", decision="allow",
              categories=reason_categories or [], bypass=bypass or [])
    # Phase C v0.9.1: fire event capture
    try:
        emit_fire_event("evidence_audit.py", verdict="allow")
    except Exception:
        pass
    # G7 v0.11.0: allow path breaks any potential block-loop → clear counter.
    _clear_recursion_state(workspace)
    sys.exit(0)


def _emit_block(workspace: Path, reason: str, categories: List[str]) -> None:
    # G7 v0.11.0: bump recursion counter BEFORE emitting block. If we've
    # hit the hard cap within the rolling window, bail out (allow) and
    # surface a warning so DEV sees the runaway.
    state = _read_recursion_state(workspace)
    count = _bump_recursion_state(workspace, state)
    if count > _RECURSION_HARD_CAP:
        warn_reason = (
            f"[evidence-audit] recursion hard-cap hit ({count} blocks in "
            f"≤ {_RECURSION_WINDOW_SECS}s) — primary `stop_hook_active` signal "
            f"may be missing from envelope. Allowing this Stop to break the "
            f"loop. Original block reason was: {reason[:300]}"
        )
        log_event(workspace, hook="evidence_audit", decision="allow",
                  categories=["recursion_cap"])
        try:
            emit_fire_event("evidence_audit.py", verdict="allow",
                            detail="recursion_cap_hit")
        except Exception:
            pass
        _clear_recursion_state(workspace)
        # Use additionalContext envelope (non-blocking) so DEV still sees
        # the warning in transcript.
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": warn_reason,
            }
        }, ensure_ascii=False))
        sys.exit(0)

    log_event(workspace, hook="evidence_audit", decision="block",
              categories=categories)
    try:
        emit_fire_event("evidence_audit.py", verdict="block",
                        detail=",".join(categories)[:200])
    except Exception:
        pass
    # v0.21 E6 (UX improvement) — append structured docs reference + bypass tail.
    reason = (
        f"{reason}\n"
        "  · See docs: docs/hooks/evidence_audit.md\n"
        "  · Bypass once: `probe-skip: all <reason>` or `[assumption]` tag in response"
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        sys.exit(0)

    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    # Don't recurse — Claude Code re-runs the agent if we block; bail out
    # the second time so we never loop forever.
    if envelope.get("stop_hook_active"):
        sys.exit(0)

    # v0.23 R8-wire: surface envelope schema drift (Claude Code format change
    # early-warning). evidence_audit is the FIRST Stop hook to parse the
    # envelope, so it's the natural place to detect when Anthropic changes the
    # envelope schema — before all 27 hooks silently break together.
    #
    # Emitted via STDERR (not stdout additionalContext) on purpose:
    #   - Advisory only — must NOT block the Stop.
    #   - stdout is reserved for the block/allow JSON envelope; printing an
    #     additionalContext object here AND a decision object later would emit
    #     two JSON lines and risk parser confusion. stderr is shown in the
    #     transcript, carries no envelope semantics, and never conflicts.
    drift = envelope_protocol_drift_warning(envelope, "Stop")
    if drift:
        sys.stderr.write(drift + "\n")
        # continue normal flow — drift is advisory only, does NOT block.

    transcript_path = envelope.get("transcript_path")
    if not transcript_path:
        sys.exit(0)
    tpath = Path(transcript_path)
    if not tpath.exists():
        sys.exit(0)

    messages = read_transcript(tpath)
    if not messages:
        sys.exit(0)

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    turn = split_current_turn(messages)
    text, tool_calls = extract_text_and_tools(turn)
    results_by_id = extract_tool_results(turn)

    if not text or len(text) < 240:
        _exit_allow(workspace)
    if "evidence-audit: skip" in text.lower():
        _exit_allow(workspace, bypass=["evidence-audit:skip"])

    # ----- PASS-claim contract -----
    registry = load_probes_registry(workspace)
    probes = [p for p in (registry.get("probes") or []) if isinstance(p, dict)]
    defaults = registry.get("_defaults") or {}
    pass_re = defaults.get("pass_claim_regex") or DEFAULT_PASS_CLAIM_REGEX
    # Per-project override > auto-discovered from .mcp.json > toolkit default.
    # discover_required_prefixes reads `.mcp.json` and returns project's actual
    # MCP server prefixes (e.g. `mcp__<project>-odoo12__`) so PASS-claim contract
    # doesn't false-block projects with non-default MCP naming.
    required_prefixes = tuple(
        defaults.get("required_tool_prefixes")
        or discover_required_prefixes(workspace)
    )
    pass_exempt_markers = tuple(
        defaults.get("pass_exempt_markers") or DEFAULT_PASS_EXEMPT_MARKERS
    )

    meta_mode = meta_review_mode(text, pass_exempt_markers)
    edited_paths = edited_paths_in_turn(tool_calls)
    matched = [] if meta_mode else matching_probes(probes, text, edited_paths)
    pass_hit = False if meta_mode else pass_claim_present(text, pass_re)

    if matched or pass_hit:
        probe_ids = [p.get("id", "") for p in matched] + ["default"]
        skip_reason = probe_skip_requested(text, probe_ids)
        if skip_reason is not None:
            _exit_allow(workspace, bypass=["probe-skip"])

        all_probes_ok = True
        # C1 — load project-defined additional evidence recognizers
        # (e.g. Playwright stdout markers). When a probe's standard
        # required_tools check fails, fall back to text-pattern match
        # against tool_results before declaring the probe unsatisfied.
        extra_patterns = load_additional_evidence_patterns(workspace)
        for p in matched:
            if not probe_evidence_satisfied(p, tool_calls, results_by_id):
                if additional_evidence_satisfied(p, results_by_id, extra_patterns):
                    continue
                if (p.get("severity") or "blocker").lower() == "blocker":
                    all_probes_ok = False
                    break

        fallback_blocks = False
        if not matched and pass_hit:
            if not default_pass_evidence_satisfied(tool_calls, required_prefixes):
                fallback_blocks = True

        if not all_probes_ok or fallback_blocks:
            _emit_block(workspace,
                        format_pass_block_reason(text, matched, fallback_blocks, required_prefixes),
                        categories=["pass_contract"])

        # ----- Cross-source corroboration (v0.23 C1, two-source) -----
        # Opt-in + warn-only. Fires ONLY for matched probes that declared
        # `cross_source_required: true` AND make a critical-class claim.
        # When the turn lacks evidence from ≥2 distinct MCP backends we emit
        # a NON-blocking warning — a single-source read may be a Postgres
        # replica-lag false positive. Conservative rollout: never blocks
        # (see _audit/cross_source.py docstring to promote to block later).
        cross_probes = [p for p in matched if requires_cross_source(text, p)]
        if cross_probes:
            warning = cross_source_warning(cross_probes, tool_calls)
            if warning is not None:
                log_event(workspace, hook="evidence_audit",
                          decision="warn", categories=["cross_source"])
                try:
                    emit_fire_event("evidence_audit.py", verdict="warn",
                                    detail="cross_source")
                except Exception:
                    pass
                # Warn-only short-circuit: emit ONE additionalContext
                # envelope and exit. Exiting here avoids printing a second
                # JSON object later (the allow/block paths each print their
                # own). This is a non-blocking outcome → clear recursion
                # state like the allow path does.
                _clear_recursion_state(workspace)
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "Stop",
                        "additionalContext": warning,
                    }
                }, ensure_ascii=False))
                sys.exit(0)

    # ----- Hallucinated-progress contract -----
    disabled_cats = set(defaults.get("disabled_progress_checks") or [])
    skip_directive = progress_skip_requested(text)
    bypass_marks: List[str] = []
    if skip_directive is not None:
        cats, _reason = skip_directive
        if "all" in cats:
            disabled_cats |= set(ALL_PROGRESS_CHECKS)
            bypass_marks.extend(ALL_PROGRESS_CHECKS)
        else:
            disabled_cats |= set(cats)
            bypass_marks.extend(cats)

    progress_violations = run_progress_checks(
        text=text,
        tool_calls=tool_calls,
        results_by_id=results_by_id,
        all_messages=messages,
        workspace=workspace,
        disabled=disabled_cats,
    )
    if progress_violations:
        _emit_block(workspace,
                    format_progress_block_reason(progress_violations, bypass_marks),
                    categories=[v.split(":", 1)[0] for v in progress_violations])

    # ----- Verify Report probe-spread (ADR-007 Bước 3) -----
    # Runs BEFORE generic claim audit because structural Verify-Report
    # violation is independent of claim/evidence count.
    probe_spread_reason = verify_report_probe_spread(turn, text)
    if probe_spread_reason:
        _emit_block(workspace, probe_spread_reason, categories=["verify_report_spread"])

    # ----- Generic claim audit (fail-open via disclaimer) -----
    if meta_mode:
        _exit_allow(workspace, bypass=["meta-review"])
    if has_disclaimer(text):
        _exit_allow(workspace, bypass=["disclaimer"])

    claims = find_claims(text)
    if not claims:
        _exit_allow(workspace)

    if has_evidence(tool_calls):
        _exit_allow(workspace, reason_categories=["claim_with_evidence"])

    _emit_block(workspace, format_generic_claim_reason(text, claims),
                categories=["generic_claim"])
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
