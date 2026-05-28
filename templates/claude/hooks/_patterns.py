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

# v0.23.1: negative lookbehind `(?<!chưa\s)` so a negated claim ("chưa
# xong" / "chưa hoàn thành" = NOT done yet) no longer reads as a completion
# claim. Step-level mentions ("Bước 1 xong") are left as-is — this gate only
# warn-nudges /verify, so over-triggering there is low harm.
COMPLETION_RE = re.compile(
    r"(?<!ch(?:ư|u)a\s)\b(done|ready|verified|complete|completed|finished|fixed|"
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


# --- v0.23.0 scope-completeness-gate (R9) --------------------------------
# Used by: scope_completeness_gate (Stop), intent_router (UserPromptSubmit
# bypass capture). Sibling of gap-completeness-gate but tracks UPFRONT
# request scope (manifest items S<N>) instead of mid-work surfaced gaps.
#
# Distinction from DONE_CLAIM_GAP_RE: scope gate fires on a broader
# done/full claim because the manifest enumerates the FULL request scope
# declared upfront (tasks.md / acceptance_evals / TodoWrite≥3), so any
# completion phrasing should trigger the unresolved-item check.

# Per-item resolution markers in agent response. Reason ≥ 8 chars
# (audit-friendly, same standard as gap-defer / skip-clarification).
SCOPE_DONE_RE = re.compile(
    r"\bscope-done:\s*S(\d+)\b",
    re.IGNORECASE | re.UNICODE,
)

SCOPE_DEFER_RE = re.compile(
    r"\bscope-defer:\s*S(\d+)\s+(\S(?:.{6,196}\S)?)",
    re.IGNORECASE | re.UNICODE,
)

SCOPE_CANT_RE = re.compile(
    r"\bscope-cant:\s*S(\d+)\s+(\S(?:.{6,196}\S)?)",
    re.IGNORECASE | re.UNICODE,
)

# Whole-gate single-shot bypass in user prompt. intent_router writes
# .skip_scope_gate_next.json; scope_completeness_gate consumes on Stop.
BYPASS_SCOPE_GATE_RE = re.compile(
    r"\bbypass-scope-gate:\s*(\S{8,200})\b",
    re.IGNORECASE,
)

# v0.25.0 parallel-subagent-guard — single-shot bypass for the PreToolUse
# parallel_conflict_guard. intent_router writes .skip_parallel_guard_next.json;
# parallel_conflict_guard.py consumes (unlinks) on next matching Edit/Write.
# Symmetric with BYPASS_GIT_GUARD_RE / BYPASS_GAP_GATE_RE.
BYPASS_PARALLEL_GUARD_RE = re.compile(
    r"\bbypass-parallel-guard:\s*(\S{8,200})\b",
    re.IGNORECASE,
)

# Broader done/full claim for scope gate. The manifest enumerates the full
# upfront scope, so any claim-of-completion should gate against pending
# items — this needs higher RECALL than DONE_CLAIM_GAP_RE.
#
# v0.23.1 fix: the earlier version wrapped every alternative in `\b(?:…)\b`,
# which silently KILLED two branches — `\b` cannot match before the emoji
# `✅` (non-word char) nor after a trailing `.`/`—` (non-word char). Net: the
# emoji branch and the "Done."/"Verified —" punctuation branch never fired,
# and ~12/22 real completion phrasings slipped through (verified empirically
# via tests/test_claim_detection_patterns.py). Each branch now manages its
# own boundaries; no outer `\b` wrapper. Negation (`chưa xong` / `chưa hoàn
# thành`) is excluded via lookbehind so "not done yet" never reads as done.
DONE_FULL_CLAIM_RE = re.compile(
    r"(?:"
    # scope-word + done-word within 30 chars ("all done", "tất cả ... pass",
    # "mọi thứ đã ổn", "everything complete", "toàn bộ done").
    r"(?:t(?:ất|at)\s*c(?:ả|a)|to(?:à|a)n\s*b(?:ộ|o)|m(?:ọ|o)i\s*th(?:ứ|u)|all|everything)"
    r"\b[^.\n]{0,30}?\b(?:done|xong|ho(?:à|a)n\s*th(?:à|a)nh|complete[d]?|pass(?:ed)?|(?:ổ|o)n)"
    # implement/sprint done, completed successfully, finished implementing.
    r"|\b(?:implement\s+done|sprint\s+(?:complete|done|ho(?:à|a)n\s*th(?:à|a)nh)"
    r"|completed\s+successfully|finished\s+implement\w*)"
    r"|\bready\s+to\s+merge\b"
    # hoàn tất / hoàn thành (not negated by "chưa").
    r"|(?<!ch(?:ư|u)a\s)\bho(?:à|a)n\s*(?:t(?:ấ|a)t|th(?:à|a)nh)\b"
    # đã [word word] xong | xong rồi/hết | fix hết rồi (not negated).
    r"|(?<!ch(?:ư|u)a\s)\bđã\s+(?:\w+\s+){0,2}xong\b"
    r"|\bxong\s+(?:r(?:ồ|o)i|h(?:ế|e)t)\b"
    r"|\bfix\s+h(?:ế|e)t\s+r(?:ồ|o)i\b"
    # ✅ emoji branch — no \b before the emoji (it is a non-word char).
    r"|✅\s*(?:implement\s+done|done|complete[d]?|ho(?:à|a)n\s*th(?:à|a)nh)"
    # standalone done/verified/complete/finished terminated by punct or EOL.
    r"|(?<!\w)(?:done|verified|complete[d]?|finished)\s*(?:[—\-.!:]|$)"
    r")",
    re.IGNORECASE | re.UNICODE,
)
