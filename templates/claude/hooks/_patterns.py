"""Shared compiled regex patterns for `.claude/hooks/*.py`.

Before 2026-05-18 these were defined locally in 4 hooks (evidence_audit,
verify_lint, verify_nudge, post_edit_verify_gate). Drift risk: edit one,
forget another → hooks parse the same text differently. Centralizing here
keeps the contracts consistent.

Compile-once: patterns are module-level, compiled at import time. Cheap
import overhead, no per-call recompile.
"""
from __future__ import annotations

import re


# --- Spec frontmatter parsers --------------------------------------------
# Used by: verify_nudge, post_edit_verify_gate, verify_lint, intent_router
# (indirectly via spec scans).

SPEC_STATUS_RE = re.compile(
    r"^status\s*:\s*([a-z_-]+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

SPEC_SLUG_RE = re.compile(
    r"^spec\s*:\s*([a-z0-9][a-z0-9_-]+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Status values that indicate the spec is mid-flight (Vibe-flow Phase 4
# or post-/verify gaps). Used by verify_nudge + post_edit_verify_gate.
IMPLEMENTING_STATUSES = ("implementing", "gaps-found")


# --- Verify Report header --------------------------------------------------
# Used by: evidence_audit (probe-spread check), verify_lint (slug extract +
# trigger), post_edit_verify_gate (indirectly via /verify mention).
#
# BUG-FIX B1 (2026-05-17): must be case-insensitive + tolerant of
# single/double hash + the inline header form `Verify Report —`
# (no leading hash) used by verify-feature/SKILL.md.

VERIFY_REPORT_HEADER_RE = re.compile(
    r"(?:#+\s*|^\s*)verify\s*report\b",
    re.IGNORECASE | re.UNICODE | re.MULTILINE,
)

# Override marker: when present, evidence_audit skips the probe-spread
# check because the agent explicitly declared sequential dependency.
SEQUENTIAL_OVERRIDE_RE = re.compile(
    r"sequential\s*[-—]\s*depends\s*on",
    re.IGNORECASE | re.UNICODE,
)


# --- Slug extraction from Verify Report text ------------------------------
# Used by: verify_lint. Tried in order; verify_lint picks the first that
# resolves to a real spec file under `.agent-toolkit/specs/`.

SLUG_PATTERNS = [
    re.compile(
        r"verify\s*report\s*[-—]\s*`?([a-z0-9][a-z0-9_-]+)`?",
        re.IGNORECASE | re.UNICODE,
    ),
    # Branch-scoped layout: .agent-toolkit/specs/<branch>/<slug>.md
    # Flat legacy layout: .agent-toolkit/specs/<slug>.md
    # Both captured via optional `<branch>/` segment.
    re.compile(
        r"\.agent-toolkit/specs/(?:[A-Za-z0-9_-]+/)?([a-z0-9][a-z0-9_-]+)\.md",
        re.IGNORECASE | re.UNICODE,
    ),
    re.compile(
        r"\bspec\s*[:=]\s*`?([a-z0-9][a-z0-9_-]+)`?",
        re.IGNORECASE | re.UNICODE,
    ),
]


# --- Completion claim detector --------------------------------------------
# Used by: post_edit_verify_gate. Matches Vietnamese + English completion
# phrases that should trigger the gate when paired with an Edit on a
# spec-tracked file but no /verify run.

COMPLETION_RE = re.compile(
    r"\b(done|ready|verified|complete|completed|finished|fixed|"
    r"ready\s*to\s*merge|xong|ho(à|a)n\s*th(à|a)nh|đã\s*fix|đã\s*xong|"
    r"feature\s*ready|deploy\s*ready)\b",
    re.IGNORECASE | re.UNICODE,
)

VERIFY_INVOCATION_RE = re.compile(
    r"(?:^|\s|`)/verify\b|run_python_tests|perturb[-_]?test|"
    r"acceptance[_-]?eval",
    re.IGNORECASE | re.UNICODE,
)


# --- Bypass directives in user prompts ------------------------------------
# Used by: invariant_guard. Single-shot override marker.

BYPASS_INVARIANT_RE = re.compile(
    r"bypass-invariant\s*:\s*([A-Za-z0-9_\-,\s]+)",
    re.IGNORECASE,
)

# v0.13.0 — escape token for clarification-gate enforcer (D9).
# Reason must be 8-200 non-whitespace chars to be audit-able; shorter
# rejected → enforcer enforces shape as usual.
SKIP_CLARIFICATION_RE = re.compile(
    r"\bskip-clarification:\s*(\S{8,200})\b",
    re.IGNORECASE,
)


# --- v0.19.0 gap-completeness-gate --------------------------------------
# Used by: gap_completeness_gate (Stop), intent_router (UserPromptSubmit
# state writer). Detects when agent surfaces a numbered gap list, resolution
# markers (defer / cant_fix), and whole-gate single-shot bypass.

# Gap list emission: `G1`, `G2 -`, `**G3**:` etc. with description.
# v0.21 T17B (M15): tightened — require LINE-START (not just whitespace)
# so prose mentions like "Graph 1 - main" or "G7 — good performance"
# embedded in sentences don't false-create gap entries. Pattern now:
# 1. Anchored to ^ via MULTILINE
# 2. Optional list marker (`- `, `* `, `1. `, `**`)
# 3. G<digits> followed by — / - / : / .
# 4. Description text 3-200 chars
GAP_LIST_EMIT_RE = re.compile(
    r"^(?:[\s>]*(?:[-*]|\d+\.)\s+)?(?:[*_`]*?)G(\d+)\b(?:[*_`]*?)\s*[—\-:.]\s*([^\n]{3,200})",
    re.IGNORECASE | re.UNICODE | re.MULTILINE,
)

# Per-gap resolution in agent response. Reason must be ≥ 8 chars per
# `skip-clarification` precedent — audit-friendly.
GAP_DEFER_RE = re.compile(
    r"\bgap-defer:\s*G(\d+)\s+(\S(?:.{6,196}\S)?)",
    re.IGNORECASE | re.UNICODE,
)

GAP_CANT_FIX_RE = re.compile(
    r"\bgap-cant-fix:\s*G(\d+)\s+(\S(?:.{6,196}\S)?)",
    re.IGNORECASE | re.UNICODE,
)

# Whole-gate single-shot bypass in user prompt.
BYPASS_GAP_GATE_RE = re.compile(
    r"\bbypass-gap-gate:\s*(\S{8,200})\b",
    re.IGNORECASE,
)

# v0.20.0 — git-guardrails single-shot bypass keyword.
# Reason must be ≥ 8 non-whitespace chars (same audit-trail standard as
# skip-clarification). intent_router writes .skip_git_guard_next.json;
# git_guardrails consumes (unlinks) on next matching Bash tool call.
BYPASS_GIT_GUARD_RE = re.compile(
    r"\bbypass-git-guard:\s*(\S{8,200})\b",
    re.IGNORECASE,
)

# v0.21 T16 (M13) — debug-sentry single-shot bypass keyword.
# Symmetric with bypass-git-guard. intent_router writes
# .skip_debug_sentry_next.json; debug_sentry consumes on Stop.
BYPASS_DEBUG_SENTRY_RE = re.compile(
    r"\bbypass-debug-sentry:\s*(\S{8,200})\b",
    re.IGNORECASE,
)

# Completion claim variant scoped for gap-gate. Reuses COMPLETION_RE
# semantics but tightens to "agent says workflow done", not casual mention.
DONE_CLAIM_GAP_RE = re.compile(
    r"\b(?:"
    r"(?:t(?:ất|at|oàn|oan)\s*bộ|all|everything)\s+(?:done|xong|ho(?:à|a)n\s*th(?:à|a)nh|complete)"
    r"|implement\s+done"
    r"|đã\s+xong\s+(?:to(?:à|a)n\s*b(?:ộ|o)|h(?:ế|e)t)"
    r"|sprint\s+(?:complete|done|ho(?:à|a)n\s*th(?:à|a)nh)"
    r"|✅\s*(?:Implement\s+done|Done|Complete)"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)
