# `.agent-toolkit/` — per-project agent runtime

Files in this folder are **per-project, durable, version-controlled**.
They are read on every Claude Code session by hooks shipped from
`agent-toolkit`. Edit them via slash commands; the agent + dev both
write here.

## Files

| File | Read by | Written by | Purpose |
|---|---|---|---|
| `invariants.json` | `invariant_guard.py` (PreToolUse on Edit/Write/MultiEdit) | `/inv-add`, dev | Durable patch-level rules. If an edit removes a `must_keep_regex` pattern with severity `blocker`, the edit is **denied**. |
| `decision-log.md` | `session_brief.py` (SessionStart) | `/adr-add`, dev | ADR-style log of WHY decisions were made. Last 3 entries injected at session start. |

## How the three problems are addressed

1. **"Agent quên decision cũ"** — invariants are mechanical: the hook
   blocks edits that violate them. Memory ≠ enforcement; this file is
   the contract.

2. **"Agent hỏi câu vô nghĩa"** — `intent_router.py` requires every
   question to carry a `Searched:` line. Questions about facts derivable
   from the codebase are rejected at the skill level.

3. **"Agent không phân tích data thực"** — `evidence_audit.py` reads
   the transcript after the response and rejects it (re-prompts agent)
   when claims like "X is slow / root cause / Y is missing" appear
   without an accompanying Read/Grep/MCP call in the same turn.

## Adding an invariant — golden path

```
User: "List view của model X phải sort theo type cố định, đừng để nó
       mất sort như lần trước."
Agent: <reads .agent-toolkit/decision-log.md, sees no existing ADR>
       → invokes /adr-add to capture context + WHY
       → invokes /inv-add to write the regex into invariants.json
       → confirms with user before persisting
Subsequent Edit that drops `order='type'` → BLOCKED with ADR reference.
```

## Bypass

A blocked edit can be unblocked for a single tool call by adding
`bypass-invariant: <id>` (or `bypass-invariant: all`) to the user's
prompt. The bypass is single-shot — the next edit re-enforces.

For permanent change: add a new ADR to `decision-log.md` superseding
the old one, then update `invariants.json` via `/inv-add`.

## Why JSON not YAML for invariants

- Stdlib only — hooks run in the project venv without extra deps.
- Easy for the agent to maintain via slash command without escape
  hazards.
- One-file source of truth, version-controlled with the project.
