# {{PROJECT_NAME}} — Agent Constitution

> **Inspired by**: GitHub Spec Kit's `memory/constitution.md` concept.
> **Purpose**: a single, short, slow-changing file the agent loads at the
> top of every spec-driven session. Aggregates the karpathy operating
> principles + the toolkit's hard rules + the most-load-bearing canonical
> decisions. If you need to remember ONE file before writing code in this
> project, this is it.

Installed by **agent-toolkit** preset `{{PRESET_NAME}}` ({{STACK_LABEL}}) on {{TODAY_ISO_DATE}}.

Edit this file when you change a project-wide principle. Smaller, more
context-specific rules belong in:
- `.cursor/rules/*.mdc` — always-apply Cursor rules
- `.codex/canonical_decisions.json` — recurring "how do we do X" answers
- `.agent-toolkit/decision-log.md` — ADRs (one per WHY)
- `.agent-toolkit/invariants.json` — mechanically-enforced patterns

---

## I. Operating principles (Karpathy-derived)

These are non-negotiable; they govern HOW the agent works, not WHAT it
builds.

1. **Think before coding.** State assumptions, surface tradeoffs.
   Specify → Clarify → Tasks → Analyze → Implement → Verify is the
   default flow for anything > 30 LOC.
2. **Simplicity first.** Smallest solution that satisfies the request.
   No speculative abstractions; no "while we're here" cleanups.
3. **Surgical changes.** Every changed line traces to a User Story or
   acceptance_eval in the spec.
4. **Goal-driven execution.** Define success criteria up front
   (acceptance_evals), verify against them at the end (`/verify`).
5. **MCP before file reads.** Use the right MCP server for discovery,
   DB lookups, and real-data probes. Don't guess what code looks like
   when `mcp__codebase__*` can show you.
6. **Canonical answers, not guesses.** For recurring questions (e.g.
   "which Python", "which DB", "which API decorator"), call
   `lookup_canonical_decision` — don't re-derive.
7. **Doubt before shipping.** Before sending a non-trivial finding,
   run `doubt-driven-review` (CLAIM → EXTRACT → DOUBT → RECONCILE).
8. **Confirm before acting.** On any prompt with an action verb
   (implement, fix, refactor, scaffold, modify, add, tạo, sửa, làm…),
   emit UNDERSTANDING / ASSUMPTIONS / QUESTIONS before any Edit/Write.
   Bypass per-prompt with "just do it" / "không cần hỏi".

## II. The spec-driven workflow (Spec Kit-aligned)

```
DEV: /plan <feature>  →  /clarify <slug>
        ↓                    ↓
    spec.md draft       spec refined + acceptance_evals locked

  [agent auto-fires]
       /tasks <slug>   →   STOP (DEV review gate)
                            ↓
                       DEV: /implement <slug>
                            ↓
  [agent auto-chain]
   /analyze  →  implement  →  /verify  →  report back to DEV
```

- **DEV owns Phase 1+2** (plan, clarify) — the requirement-defining work.
- **AGENT owns Phase 3-5** under autonomy after DEV approves tasks.md.
- **Verify is the gate.** No "done" without a `/verify` PASS report.

## III. Hard rules (project-wide invariants)

1. **Module-agnostic.** Invariant rules and skill text must not hard-code
   project module names, DB names, or addon-root paths. Discover at
   runtime via codebase MCP. Allowed: the user typing the name (preserve
   as-is). Forbidden: skill files ship with any project-specific literal
   baked into examples — use `<module>`, `<addon>`, `<your.model>` placeholders.
2. **Determinism.** Recurring "how do we do X" answers come from
   `.codex/canonical_decisions.json`, not re-derived per conversation.
3. **Credentials policy.** Real credentials live only in
   `.codex/mcp.local.env` (gitignored). Never commit creds, never paste
   them into spec / decision / memory files. Reference by name only.
4. **Python venv.** Always use the project venv `{{PYTHON_BIN}}`. Never
   bare `python` / `python3` from PATH.
5. **No silent skip.** When a check fails, surface it. WARN > silent
   PASS. BLOCK > WARN. Never demote severity to keep a flow green.
6. **Real-data verification before "done".** `/verify` probes the real
   DB / endpoint / log layer. Mock-only tests are insufficient evidence.

## IV. Stack-specific constants

These come from preset `{{PRESET_NAME}}`. Authoritative source for stack
conventions is `.codex/canonical_decisions.json`; this section is a
1-line summary.

- **Language:** {{STACK_LANGUAGE}} {{STACK_LANGUAGE_VERSION}}
- **Framework:** {{STACK_FRAMEWORK}} {{STACK_FRAMEWORK_VERSION}}
- **Default DB:** `{{DEFAULT_DB}}`
- **Reply language:** {{RESPONSE_LANGUAGE}}
- **Addon roots:** {{ADDON_ROOTS_CSV}}
- **MCP servers:** {{MCP_SERVERS_CSV}}

## V. Where to look when in doubt

| You need… | Read this |
|---|---|
| The exact convention for X | `.codex/canonical_decisions.json` |
| WHY a past decision was made | `.agent-toolkit/decision-log.md` |
| What patterns the toolkit enforces | `.agent-toolkit/invariants.json` |
| Skill-level workflow detail | `.cursor/skills/<name>/SKILL.md` |
| Stack-level coding rules | `.cursor/rules/*.mdc` |
| The current spec / tasks / analyze / verify report | `.agent-toolkit/specs/<branch>/<slug>/*` |

## VI. Changing the constitution

This file is slow-changing. Edit only when:
- A new project-wide principle is settled.
- An old principle is contradicted by a new ADR (cite the ADR in the
  edit + mark the obsoleted principle).

For everything else, prefer adding to `decision-log.md` (ADR) or
`canonical_decisions.json` (recurring answer).

---

Last revised: {{TODAY_ISO_DATE}} · toolkit `{{PRESET_NAME}}` preset.
