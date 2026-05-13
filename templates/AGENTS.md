# {{PROJECT_NAME}} Agent Instructions

> Installed by **agent-toolkit** with preset `{{PRESET_NAME}}`.
> To refresh from latest toolkit: `python <toolkit>/setup.py update {{WORKSPACE_ROOT}}`.

This file is the entry-point for any AI coding agent in this workspace.
The heavy material lives in:

- `.cursor/rules/*.mdc` (always-apply project rules)
- `.cursor/skills/*` (focused skills)
- `.codex/canonical_decisions.json` (single source of truth for recurring answers)
- `.codex/audit_findings_locked.md` (locked audit findings, if present)

## Workspace

- Root: `{{WORKSPACE_ROOT}}`
- Stack: {{STACK_LABEL}}
- Language: {{STACK_LANGUAGE}} {{STACK_LANGUAGE_VERSION}}
- Python interpreter: `{{PYTHON_BIN}}`
- Default database: `{{DEFAULT_DB}}`
- Default reply language: {{RESPONSE_LANGUAGE}}

## Addon / Code roots

{{ADDON_ROOTS}}

## MCP Servers

{{MCP_SERVERS}}

Credentials live in `.codex/mcp.local.env` (gitignored). Configure via the
`.codex/mcp.local.env.example` template.

## Intent → Skill routing (use this before answering)

When the user's message matches one of these intents, open the listed skill
*first*. Multiple skills can apply — open all that match, in the order
shown.

| User says (intent) | Open skill(s) |
|---|---|
| Any action verb that mutates state ("làm", "tạo", "sửa", "fix", "implement", "refactor", "thêm", "add", "update"…) | `clarification-gate` (run FIRST — emits UNDERSTANDING/ASSUMPTIONS/QUESTIONS + STOP before any Edit/Write) |
| "review", "audit", "phân tích sâu", "tìm bug", "còn gì cần fix nữa không?" | `code-review` → then `{{STACK_FRAMEWORK}}-code-review` overlay |
| "I'm not sure", "double-check", "are you sure?", before sending a non-trivial finding | `doubt-driven-review` (overlay on any finding skill) |
| "how do we do X in this project", "what's the convention for…", recurring fact lookup | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-deterministic-answers` |
| "tìm file", "where is X defined", "trace the call site" | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-codebase-discovery` |
| "kiểm tra dữ liệu", "verify against real DB", "is this true on prod data?" | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-data-verification` |
| "lỗi", "bug", "không chạy", "exception", traceback pasted | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-debug-troubleshoot` |
| "tạo feature mới", "implement X", "refactor Y" (> 30 LOC) | `spec-driven-feature` (Phase 1-3) → then `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-module-scaffold` (Phase 4) |
| "viết test trước", "TDD", "test driven" | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-tdd` |
| "tạo module", "scaffold" (already specced) | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-module-scaffold` |
| "viết theo pattern X", "follow project style for Y" | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-code-patterns` |
| "Jira", "ticket", "NKV-…" | `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-jira-workflow` |

If two intents match (e.g. a review of a real-DB issue), open both skills
and merge their workflows — do not pick one.

## Operating Principles

These principles mirror the upstream **Karpathy** guidelines we adopted for
this workspace; the full rules live in `.cursor/rules/karpathy-guidelines.mdc`
and the skill `.cursor/skills/karpathy-guidelines/`.

1. **Think before coding.** State assumptions, surface tradeoffs.
2. **Simplicity first.** Smallest solution that satisfies the request.
3. **Surgical changes.** Every changed line traces to the user's request.
4. **Goal-driven execution.** Define success criteria up front, verify against them.
5. **MCP before file reads.** Use the right MCP server for discovery and DB lookups.
6. **Canonical answers, not guesses.** For recurring questions, call
   `codebase.lookup_canonical_decision` first.
7. **Doubt before shipping.** Before sending a non-trivial finding or
   recommendation, run the `doubt-driven-review` loop (CLAIM → EXTRACT →
   DOUBT → RECONCILE → STOP).
8. **Confirm before acting.** On any prompt containing an action verb
   (implement, fix, refactor, scaffold, modify, add, tạo, sửa, làm…),
   open `clarification-gate` FIRST and emit the 3-block
   UNDERSTANDING / ASSUMPTIONS / QUESTIONS before calling any
   state-changing tool. The user opts out per-prompt with
   "just do it" / "không cần hỏi" / "implement luôn".

## Hard rules

- Do not edit committed config files to add credentials.
- Do not invent answers for recurring questions; lookup or propose registry update.
- Do not add features outside the request without asking first.
