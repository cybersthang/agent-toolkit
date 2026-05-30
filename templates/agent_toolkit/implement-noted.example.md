---
schema_version: 1
spec: <slug>
implement_run_at: YYYY-MM-DD
implement_agent: claude-opus-4-7
implement_session_id: <optional uuid or short ref>
total_scope_deviations: 0
total_tradeoffs_with_evidence: 0
total_followups: 0
overall_confidence: high
---

# Implement notes — `<slug>`

Sidecar artifact emitted by AGENT at the end of `/implement <slug>`.
Per-spec scope; lifecycle ends when spec `eval_status: verified`.

> **Schema contract** (enforced by `implement_notes_gate.py` advisory
> Stop hook): 4 sections numbered 1-4, frontmatter declares counts.

---

## 1. Scope deviations (N items)

Decisions AGENT made that are NOT explicitly covered by an
`acceptance_eval` in the spec frontmatter. Includes BOTH:
- choices outside spec's intent (added field X, picked library Y).
- divergences from DEV's literal request that AGENT made on the fly.

Format per item:

- **SD-1**: <short description, e.g. "Added `**/models/*.py` glob for flat layout support">
  - Type: outside-spec | diverged-from-request
  - Lý do: <why this choice>
  - Alternatives considered (if any in transcript): <A / B>
  - File(s) affected: `path/to/file.py:line-line`
  - Spec linkage: `<eval id closest to this decision>` hoặc "none"
  - Confidence: high / medium / low
  - DEV review urgency: low / medium / high

(Repeat for SD-2, SD-3, ...)

---

## 2. In-transcript trade-offs (K items)

**STRICT rule**: only list trade-offs that have explicit evidence in
the conversation transcript. Each item MUST cite turn id /
timestamp / message reference. Cấm reconstruction post-hoc — đó là
hallucination risk, không phải genuine trade-off.

Format per item:

- **T-1**: <decision point, e.g. "warn-only vs blocking for spec_first_guard">
  - Options surfaced in transcript: (a) warn-only emit stderr (b) block tool call
  - Chosen: (a)
  - Transcript evidence: turn id `<id>` hoặc timestamp `2026-05-21T14:30:00Z`
  - Rationale: <one-line summary of why chosen>
  - Reversibility cost: low | medium | high

(Repeat for T-2, ...)

If no trade-offs were explicitly weighed in transcript: write
"None — implementation followed spec directly without alternative
evaluation in this transcript."

---

## 3. Open follow-ups (P items)

Things AGENT noticed during implementation but deferred. Includes:
- Bugs / inconsistencies found but out-of-scope.
- Refactor opportunities.
- Spec-update candidates.
- Future hardening (e.g. "this should become an invariant if
  pattern recurs in 2 more features").

Format per item:

- **F-1**: <description>
  - Priority: high / medium / low
  - Owner: DEV / future-sprint / community-PR
  - Spec to-add candidate?: yes / no
  - Invariant candidate?: yes / no

(Repeat for F-2, ...)

---

## 4. Confidence summary

Self-assessment by AGENT. Used by DEV to prioritize review.

- High-confidence decisions: <count>
  Decisions backed by spec eval + test + standard pattern. Low review urgency.
- Medium-confidence: <count>
  Decisions with multiple defensible options; AGENT picked one but
  alternative may be valid. Review recommended.
- Low-confidence: <count>
  Decisions where AGENT had limited information OR signal in spec.
  **DEV should verify these explicitly.**

### Items DEV should verify next

Bulleted list of SD-N / T-N / F-N ids that map to low-confidence
items. Example:
- `SD-3` — confidence: low — pattern picked under time pressure
- `T-2` — confidence: low — alternative B may have been better in hindsight

---

## Bypass note

If this file is missing OR sections are skipped: the advisory hook
emits a warn at Stop ("[implement-notes-gate] ..."). To suppress
single-shot, include `implement-notes: skip <reason>` in the
implement-done response.

---

## Sample (filled-in stub for reference)

```markdown
## 1. Scope deviations (2 items)

- **SD-1**: Added `**/models/*.py` to DEFAULT_FEATURE_GLOBS for flat-layout support
  - Type: outside-spec
  - Lý do: Spec eval g1 expected match on `models/thing.py` but original glob `**/models/**/*.py` required subdirectory
  - Alternatives considered: keep nested-only + force test to use nested path
  - File(s) affected: `templates/claude/hooks/spec_first_guard.py:62-65`
  - Spec linkage: g1-warn-on-feature-edit
  - Confidence: high
  - DEV review urgency: low

- **SD-2**: Dropped `^` anchor in src_regex test pattern
  - Type: diverged-from-request
  - Lý do: Hook does `re.search` not `re.match`; anchored regex fails against absolute file paths
  - Alternatives considered: change hook to re.match (more invasive)
  - File(s) affected: `tests/test_hooks_integration.py:122`
  - Spec linkage: c9-hook-integration-tests
  - Confidence: medium
  - DEV review urgency: medium

## 2. In-transcript trade-offs (1 item)

- **T-1**: schema_version=2 strict vs lenient parse
  - Options surfaced in transcript: (a) strict reject unknown fields (b) lenient ignore unknowns
  - Chosen: (b) lenient
  - Transcript evidence: turn id "v0.6.2-sprint-S2.2"
  - Rationale: forward-compat with future schema_version=3
  - Reversibility cost: low

## 3. Open follow-ups (1 item)

- **F-1**: Add `dispatcher_fire_log.json` ring buffer for runtime hook fire evidence
  - Priority: medium
  - Owner: DEV (manual T1 evidence collection) or future v0.7.2 sprint
  - Spec to-add candidate?: yes
  - Invariant candidate?: no

## 4. Confidence summary

- High-confidence decisions: 1 (SD-1)
- Medium-confidence: 1 (SD-2)
- Low-confidence: 0

### Items DEV should verify next
- `SD-2` — confidence: medium — verify anchor drop doesn't break other consumers
```
