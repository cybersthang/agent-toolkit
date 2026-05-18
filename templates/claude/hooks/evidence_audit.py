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

# Make `_audit` package importable when invoked as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _audit.claim_audit import (
    find_claims, has_disclaimer, has_evidence,
)
from _audit.pass_contract import (
    DEFAULT_PASS_CLAIM_REGEX, DEFAULT_PASS_EXEMPT_MARKERS, DEFAULT_REQUIRED_TOOL_PREFIXES,
    default_pass_evidence_satisfied, edited_paths_in_turn, load_probes_registry,
    matching_probes, meta_review_mode, pass_claim_present, probe_evidence_satisfied,
    probe_skip_requested,
)
from _audit.progress_checks import (
    ALL_PROGRESS_CHECKS, progress_skip_requested, run_progress_checks,
)
from _audit.reasons import (
    format_generic_claim_reason, format_pass_block_reason, format_progress_block_reason,
)
from _audit.telemetry import log_event
from _audit.transcript import (
    extract_text_and_tools, extract_tool_results, read_transcript, split_current_turn,
)


# UTF-8 stdin/stdout for Vietnamese identifiers.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _exit_allow(workspace: Path, reason_categories: List[str] = None, bypass: List[str] = None) -> None:
    log_event(workspace, hook="evidence_audit", decision="allow",
              categories=reason_categories or [], bypass=bypass or [])
    sys.exit(0)


def _emit_block(workspace: Path, reason: str, categories: List[str]) -> None:
    log_event(workspace, hook="evidence_audit", decision="block",
              categories=categories)
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
    required_prefixes = tuple(
        defaults.get("required_tool_prefixes") or DEFAULT_REQUIRED_TOOL_PREFIXES
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
        for p in matched:
            if not probe_evidence_satisfied(p, tool_calls, results_by_id):
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
    sys.exit(main())
