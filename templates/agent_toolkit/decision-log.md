# Decision Log — {{PROJECT_NAME}}

Append-only ADR-style log. The agent reads the latest entries via
`session_brief.py` (SessionStart hook) so every conversation starts
aware of recent decisions. The dev / agent appends a new ADR via
`/adr-add`.

Each entry follows this shape:

```
## ADR-NNN: <short title>
- **Date**: YYYY-MM-DD
- **Status**: Proposed | Accepted | Superseded by ADR-MMM | Deprecated
- **Context**: 1-3 sentences explaining the trigger.
- **Decision**: the rule, in declarative form.
- **Enforcement**: invariants.json#<id> | code review | manual | none
- **Consequences**: who/what is affected; trade-offs accepted.
```

References:
- Michael Nygard, "Documenting Architecture Decisions" (2011).
- Invariant registry: `.agent-toolkit/invariants.json`
- Hook enforcement: `.claude/hooks/invariant_guard.py`

---

<!--
  Add new ADRs BELOW this line. The session_brief hook surfaces the
  last 3 entries; older ADRs stay searchable in this file.
-->

## ADR-001: Spec-first mandatory for orchestration patches

- **Date**: 2026-05-21
- **Status**: Accepted
- **Context**: Vibe-flow Phase 1 ("Plan-first") is a contract value but
  had no enforcement. v0.6.0 patches shipped with a retrospective spec
  (`retrospective: true` in frontmatter), exposing the gap.
- **Decision**: For changes that touch `feature_scope_globs` paths AND
  land on a non-trunk branch, a spec MUST exist at
  `.agent-toolkit/specs/**/<branch-slug>.md` with non-empty
  `acceptance_evals:` BEFORE the first feature-code commit. Hotfixes
  and typo-fixes are exempt — declare via `spec-first-guard: skip
  <reason>` bypass marker.
- **Enforcement**:
  - Advisory hook `.claude/hooks/spec_first_guard.py` (PreToolUse) —
    warns on feature edit without spec; does NOT block (toolkit
    contract is "nudge, don't gate").
  - Tool `.codex/tools/detect_retrospective_spec.py` — git-log
    timestamp comparison; flagged retrospectives must declare
    `retrospective: true` in spec frontmatter.
  - CHANGELOG entries must mark retrospective specs with
    `[retrospective]` tag in the section header.
- **Consequences**:
  - DEV / AGENT gets nudge before Edit on feature-scope file with no spec.
  - Hook is warn-only → workflow not blocked; honor system + advisory
    metrics aggregated via `gap_status`.
  - Trade-off accepted: AGENT may write spec retrospectively when
    iterating on hotfix-style patches; mismatch between declared flag
    and detector verdict is surfaced but not blocking.

