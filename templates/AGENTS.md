# {{PROJECT_NAME}} Agent Instructions

> Installed by **agent-toolkit** with preset `{{PRESET_NAME}}`.
> To refresh from latest toolkit: `python <toolkit>/setup.py update {{WORKSPACE_ROOT}}`.

This file is the entry-point for any AI coding agent in this workspace.
The heavy material lives in:

- `.agent-toolkit/constitution.md` (toolkit principles — read FIRST before specs)
- `.cursor/rules/*.mdc` (always-apply project rules)
- `.cursor/skills/*` (focused skills)
- `.codex/canonical_decisions.json` (single source of truth for recurring answers)
- `.codex/audit_findings_locked.md` (locked audit findings, if present)

## Spec-driven workflow (Spec Kit aligned)

The default flow for anything > 30 LOC:

```
DEV:    /plan <feature>  →  /clarify <slug>
            ↓                    ↓
        spec.md draft       spec refined + acceptance_evals locked

[agent auto-fires]
        /tasks <slug>   →   STOP (DEV reviews tasks.md)
                                ↓
DEV:    /implement <slug>
                                ↓
[agent auto-chain]
        /analyze  →  execute tasks  →  /verify  →  báo cáo DEV
```

DEV chỉ làm 3 lệnh: `/plan`, `/clarify`, `/implement` (sau khi review
tasks.md). Phần còn lại agent tự chạy dưới autonomy.

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
| `/plan <feature>`, "tạo feature mới", "implement X", "refactor Y" (> 30 LOC) | `plan-feature` (Spec Kit Phase 1: SPECIFY) |
| `/clarify <slug>`, "grill me", "stress-test spec", "đóng GAP" | `clarify` (Spec Kit Phase 2: CLARIFY — auto-fires `/tasks`) |
| `/tasks <slug>` (manual re-emit), "rã task" | `tasks-breakdown` (Spec Kit Phase 3: TASKS — STOPs for DEV review) |
| `/analyze <slug>`, "lint spec ↔ tasks" | `analyze-artifacts` (Spec Kit Phase 3.5: ANALYZE — gate before implement) |
| `/implement <slug>`, "bắt đầu code", "execute tasks" | auto-chain: analyze → tasks execute → `verify-feature` (Phase 5) |
| `/verify <slug>`, "kiểm tra dữ liệu", "verify real data" | `verify-feature` (Spec Kit Phase 5: VERIFY) |
| "review", "audit", "phân tích sâu", "tìm bug", "còn gì cần fix nữa không?" | `code-review` → then `odoo-code-review` overlay (auto-detects v12/17/18/19/20 from `__manifest__.py`) |
| "I'm not sure", "double-check", "are you sure?", before sending a non-trivial finding | `doubt-driven-review` (overlay on any finding skill) |
| "how do we do X in this project", "what's the convention for…", recurring fact lookup | `odoo-deterministic-answers` (canonical_decisions.json — registry is version-agnostic) |
| "tìm file", "where is X defined", "trace the call site" | `odoo-codebase-discovery` (MCP tools are version-agnostic) |
| "lỗi", "bug", "không chạy", "exception", traceback pasted | `odoo-debug-troubleshoot` (auto-detects version, loads matching pitfalls) |
| "viết test trước", "TDD", "test driven" | `odoo-tdd` (auto-detects version, loads matching framework quirks) |
| "tạo module", "scaffold" (already specced) | `odoo-module-scaffold` (auto-detects version from sibling manifests) |
| "viết theo pattern X", "follow project style for Y" | `odoo-code-patterns` (auto-detects version, loads matching patterns ref) |
| "Jira", "ticket", "NKV-…" | `odoo-jira-workflow` (version-agnostic) |

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
- **No drip-feed (v0.19+)**: when surfacing GAP/BLOCKER lists, expect
  `gap_completeness_gate` Stop hook to track them in
  `.agent-toolkit/.open_gaps.json`. A subsequent "done" claim is BLOCKED
  until every open gap is resolved (fix and re-emit; or mark
  `gap-defer: G<N> <reason>`; or escalate `gap-cant-fix: G<N> <reason>`).
  Whole-gate single-shot bypass via prior prompt
  `bypass-gap-gate: <reason>`. Rooted in `feedback_exhaustive_analysis`
  memory: ONE exhaustive pass, not iterative discovery.
- **Implement-doc sidecar (v0.18+)**: after `/implement <slug>` +
  `/verify`, agent auto-emits `<slug>.implement-noted.{md,html}`
  (Phase 5.5 of `/implement`). DEV opens the HTML in browser to review
  scope deviations, in-transcript trade-offs (cite required),
  follow-ups, and confidence summary. Disable via
  `.agent-toolkit/implement_notes.json` `"auto_emit": false`.
