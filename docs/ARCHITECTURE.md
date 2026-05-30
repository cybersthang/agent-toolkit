# Architecture (1 picture)

```
                    ┌─────────────────────────────────────────┐
                    │       DEV (intent owner)                │
                    │  /plan  /clarify  /implement            │
                    └────────────────┬────────────────────────┘
                                     │ slash commands
                                     ▼
              ┌──────────────────────────────────────────────┐
              │           CLAUDE CODE HARNESS                │
              │                                              │
              │  SessionStart ─► [session_brief]             │
              │     │ inject: invariants, ADRs, hook health  │
              │     ▼                                        │
              │  UserPromptSubmit ─► [intent_router]         │
              │     │ suggest skills, write last_intent      │
              │     ▼                                        │
              │  PreToolUse(Bash) ─► [git_guardrails]  ❌DENY │
              │  PreToolUse(Edit) ─► [invariant_guard]  ❌DENY │
              │                  ─► [analyze_halt_gate]      │
              │                  ─► [spec_first_guard]       │
              │     │                                        │
              │     ▼                                        │
              │  PostToolUse(Edit) ─► [tdd_runner]           │
              │                   ─► [verification_loop]     │
              │                   ─► [auto_test_runner]      │
              │                   ─► [auto_run_probes]  ◄─── │
              │     │                                  │     │
              │     ▼                                  │MCP  │
              │  Stop ─► [evidence_audit]   ❌BLOCK ◄──┤probe│
              │       ─► [clarification_gate_enforcer] ❌BLOCK │
              │       ─► [gap_completeness_gate]  ❌BLOCK    │
              │             (chặn drip-feed v0.19)           │
              │       ─► [scope_completeness_gate] ❌BLOCK   │
              │             (chặn partial-done v0.23)        │
              │       ─► [verify_lint]      ❌BLOCK          │
              │       ─► [post_edit_verify_gate] ❌BLOCK     │
              │       ─► [debug_sentry]     ❌BLOCK          │
              │       ─► [implement_notes_gate] ⚠️WARN       │
              │             (md+html sidecar v0.18)          │
              │       ─► [verify_lint_scope]  ❌BLOCK        │
              └──────────────────────────────────────────────┘
                                     │ tool call ▼
              ┌──────────────────────────────────────────────┐
              │             MCP SERVERS (per preset)         │
              │                                              │
              │  codebase ◄─► postgres ◄─► realdata_test     │
              │   (search)    (DB read)    (run module test) │
              │                                              │
              │  + jira (ticket), gitlab (CI), playwright    │
              └──────────────────────────────────────────────┘

   ─────── 3-tier rule (cross-linked, auditable) ───────

         ┌─────────────────────────────────────────┐
         │  1. CONSTITUTION  (slow-changing)        │ ◄─── /constitution
         │     .agent-toolkit/constitution.md       │
         │     project-wide principles              │
         └───────────────┬─────────────────────────┘
                         │ amendments cite
                         ▼
         ┌─────────────────────────────────────────┐
         │  2. ADR LOG  (append-only WHY)          │ ◄─── /adr-add  /decide
         │     .agent-toolkit/decision-log.md      │
         │     one entry per durable decision      │
         └───────────────┬─────────────────────────┘
                         │ enforces via
                         ▼
         ┌─────────────────────────────────────────┐
         │  3. INVARIANTS  (mechanical patterns)   │ ◄─── /inv-add
         │     .agent-toolkit/invariants.json      │     /bug-to-test
         │     regex/AST patterns — hooks DENY     │
         │     edits that strip them               │
         └─────────────────────────────────────────┘
```

[ASCII for browser-friendly inline render; the same diagram in
mermaid/excalidraw form ships in `docs/architecture.md` (planned).]

## Hook fail modes + resilience

- [hook-fail-modes.md](hook-fail-modes.md) — per-hook fail-OPEN / fail-CLOSED behaviour.
- [resilience.md](resilience.md) — `agent_supervisor` stall-watcher + resume-brief.
- [parallel.md](parallel.md) — `parallel_conflict_guard` cross-zone Edit block for concurrent sub-agents.
