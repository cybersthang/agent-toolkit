# `.agent-toolkit/` — per-project agent runtime

Files in this folder are **per-project, durable, version-controlled**.
They are read on every Claude Code session by hooks shipped from
`agent-toolkit`. Edit them via slash commands; the agent + dev both
write here.

## Files

| File | Read by | Written by | Purpose |
|---|---|---|---|
| `invariants.json` | `invariant_guard.py` (PreToolUse on Edit/Write/MultiEdit) | `/inv-add`, dev | Durable patch-level rules. If an edit removes a `must_keep_regex` pattern with severity `blocker`, the edit is **denied**. |
| `acceptance-probes.json` | `evidence_audit.py` (Stop) | `/probe-add`, dev | Empirical PASS-claim contract. If the agent declares "PASS/DONE/VERIFIED" without calling the required MCP tool in the same turn, the Stop is **blocked** and the agent must re-verify or downgrade the claim. |
| `decision-log.md` | `session_brief.py` (SessionStart) | `/adr-add`, dev | ADR-style log of WHY decisions were made. Last 3 entries injected at session start. |

## How the four problems are addressed

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

4. **"Agent báo PASS nhưng dev test lại không pass"** — the same hook
   has a **PASS-claim contract** (fail-CLOSED, stricter than #3): any
   "passed / done / verified / hoàn thành / đã test" claim must be
   backed by an MCP call on real data — either matching a registered
   probe in `acceptance-probes.json`, or (fallback) at least one call
   to a canonical evidence MCP (`mcp__realdata_test__*`,
   `mcp__postgres__*`). `[assumption]` does NOT exempt PASS claims —
   PASS is incompatible with "I'm not sure". Bypass single-shot via
   `probe-skip: <id|all> <reason>` in the response.

   **Per-feature probes** declare:
   - `applies_when` (claim regex / path globs / task tags) — activation rule
   - `evidence.required_tools` — which MCP tool(s) must run
   - `falsification.description` — recipe for physical hypothesis test
     (e.g. inject `time.sleep(N)`, observe downstream wait increases by
     N±0.1s; if not → claim is wrong)
   - `severity` (blocker | warn)

5. **"Agent báo đã làm X nhưng thực ra không làm" (hallucinated
   progress)** — `evidence_audit` also runs 5 stack-agnostic
   cross-checks against the turn's tool_use/tool_result record:

   | Code | Category | What it catches |
   |---|---|---|
   | A | `action_ghost` | "đã thêm X" / "fixed Y" without any Edit/Write/MultiEdit/Bash tool_use in turn |
   | B | `tool_result_fabrication` | "tests passed / no errors" while a Bash/MCP tool_result in the same turn has `is_error=true` or `Exit code: N` (N≠0) |
   | C | `phantom_citation` | Cite `path.ext:line` for a file not Read/Grep'd in turn AND not present on disk |
   | D | `todo_inconsistency` | "hoàn thành tất cả / all done" while latest `TodoWrite` state (anywhere in transcript) still has `pending`/`in_progress` items |
   | E | `overcount` | "đã sửa N file" but actual `Edit/Write/MultiEdit` count < N |

   Bypass single-shot: `progress-skip: <category|all> <reason>` in the
   response. Disable per-project: list categories in
   `acceptance-probes.json._defaults.disabled_progress_checks`.
   `[assumption]` does NOT exempt — these are factual claims, not
   opinions.

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

## Adding an acceptance probe — golden path

```
User: "Request /web/dataset/load_views phải BLOCK trang chính —
       đừng để nó async ra phía sau và user thấy UI trắng."
Agent: → invokes /adr-add (ADR-002: load_views must be blocking)
       → invokes /probe-add to register a timing_perturb probe:
            required_tools: ["mcp__realdata_test__run_smoke_test"]
            falsification: "inject time.sleep(2) into the controller,
              re-run smoke, assert page load increases by 2±0.1s.
              If page load unchanged → request is NOT actually blocking
              and the claim is false."
Subsequent "implementation done" without running the smoke probe → BLOCKED.
```

## PASS-claim contract — when does the hook block?

| Situation | Hook behavior |
|---|---|
| Agent says "tests pass" + called `mcp__realdata_test__run_module_test` in turn | ✅ allow |
| Agent says "verified" + called `Read` only (no MCP) | 🛑 block — Read on source ≠ real-data verification |
| Agent says "implementation done" + called Agent (sub-agent) only | 🛑 block — sub-agent tool calls don't bubble up; parent must call MCP directly OR include `probe-skip:` |
| Agent says "looks correct [assumption]" | ✅ allow — disclaimer downgrades to non-PASS |
| Agent says "PASS but probe-skip: load-views-blocking DB is down" | ✅ allow — bypass logged |
| Response < 240 chars or contains `evidence-audit: skip` | ✅ allow — short reply or explicit opt-out |
