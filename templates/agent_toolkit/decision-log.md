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
