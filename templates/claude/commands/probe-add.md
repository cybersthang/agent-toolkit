---
description: Register a new acceptance probe in .agent-toolkit/acceptance-probes.json. Use when a feature has a verifiable behavior that the agent must prove via real-data MCP before claiming PASS/DONE (e.g. "this request must BLOCK the UI", "this computed field must match the report total", "this cron must be idempotent").
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: "[probe-id-slug] [short-description]"
---

# /probe-add — Register an acceptance probe

## Goal

Translate a user-stated verifiable behavior into a probe entry in
`.agent-toolkit/acceptance-probes.json`. After registration, the
`evidence_audit` Stop hook BLOCKS any "PASS/DONE/VERIFIED" claim from
the agent unless the matching MCP tool was called in the same turn.

This solves the "agent báo pass nhưng dev test lại không pass" failure
mode: it converts the dev's verification intuition into a mechanical
gate.

Argument: `$ARGUMENTS` — optional probe id + short description. If
empty, prompt the user.

## Step-by-step

1. **Read existing registry** — `Read .agent-toolkit/acceptance-probes.json`.
   Confirm no entry with the same `id` slug exists.

2. **Read the latest ADR** — `Read .agent-toolkit/decision-log.md`. If
   the verifiable behavior hasn't been captured as an ADR, RUN
   `/adr-add` FIRST so the WHY is recorded. The probe must reference
   its ADR.

3. **Frame the verifiable behavior as ONE empirical check**:
   - "This list view must return ≤500 rows for partner=42" → `orm_eval`
     probe via `mcp__realdata_test__eval_orm_expression`.
   - "This computed total must equal the UI report's number" →
     `compare_with_expected` probe.
   - "This request must BLOCK page load" → `timing_perturb` probe:
     inject `time.sleep(N)` into suspected blocking call; downstream
     wait must increase by N±0.1s.
   - "This algorithm must be deterministic" → `consistency_check_eval`
     probe (runs=2 or 3, identical fingerprint).

4. **Identify activation rule** — at least ONE of:
   - `claim_regex`: regex on assistant response text (default:
     match generic PASS words; tighten to feature-specific phrases
     like `partner.*export.*works` if multiple probes coexist).
   - `path_globs`: file globs — probe activates when Edit/Write
     touched a matching path in the turn.
   - `task_tags`: agent declares `[task: <tag>]` in its response;
     probe activates when tag matches.

5. **Identify required evidence tool(s)** — at least one MCP tool name
   the agent MUST call. Examples (Odoo stack — substitute for your
   project's MCP):
   - `mcp__realdata_test__eval_orm_expression`
   - `mcp__realdata_test__compare_with_expected`
   - `mcp__realdata_test__consistency_check_eval`
   - `mcp__realdata_test__run_module_test`
   - `mcp__realdata_test__run_smoke_test`
   - `mcp__postgres__query_readonly`
   - Wildcard form: `mcp__realdata_test__*` (any tool from that server).

6. **Propose the entry to the user** in this exact shape, then STOP for
   approval:

   ```json
   {
     "id": "<kebab-case>",
     "description": "<one-line>",
     "applies_when": {
       "claim_regex": "<optional regex>",
       "path_globs": ["<glob>", "..."],
       "task_tags": ["<tag>", "..."]
     },
     "evidence": {
       "required_tools": ["<mcp_tool_name>", "..."],
       "min_calls": 1,
       "must_include_call": "<optional regex on tool input JSON>"
     },
     "falsification": {
       "type": "timing_perturb | side_effect_inject | log_assertion | null",
       "description": "<human-readable falsification recipe — e.g. 'inject time.sleep(2) into endpoint X, assert downstream wait increases by 2±0.1s'>"
     },
     "severity": "blocker | warn",
     "rationale": "<one paragraph including ADR ref>",
     "added": "<today YYYY-MM-DD>",
     "added_by": "agent | <user-email>",
     "related_adr": "ADR-NNN"
   }
   ```

   Default severity to `blocker` — the entire point of this registry
   is to fail-closed on PASS claims.

7. **On approval** — `Edit` `.agent-toolkit/acceptance-probes.json`:
   - Append the new entry to the `probes` array.
   - Bump `version` by 1.
   - Preserve 2-space indent and trailing newline. **Save without BOM**
     (the hook tolerates BOM via utf-8-sig, but plain utf-8 is the
     project convention).

8. **Smoke-test the hook**:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"
   $env:CLAUDE_PROJECT_DIR="{{WORKSPACE_ROOT}}"
   # Should BLOCK: agent claims PASS without calling the required MCP tool.
   # Construct a minimal transcript and pipe to the hook (see
   # docs for an example harness; toolkit ships
   # `.codex/tests/hooks/test_pass_contract.py` as a programmatic version).
   ```
   Confirm `decision: block` when evidence missing, `allow` when the
   required MCP tool is in the turn.

9. **Report**: show the user the registered probe + smoke-test output
   + how to bypass single-shot (`probe-skip: <id> <reason>` in the
   agent's response).

## Refuse / clarify when

- The behavior cannot be expressed as a real-data check (e.g. "looks
  clean" — that's code review, use `code-review` skill instead).
- `required_tools` is empty — probe with no evidence requirement is
  meaningless.
- `applies_when` is so broad it would fire on every response (e.g.
  `claim_regex: ".*"`). Tighten to feature-specific markers or path
  globs.
- The probe duplicates an existing one. Update the existing entry
  instead.

## What NOT to do

- Do NOT set `severity: warn` by default — defeat the purpose.
- Do NOT register a probe whose `required_tools` references an MCP
  server not configured in `.mcp.json`. Run `mcp__codebase__workspace_status`
  first to verify the server is up.
- Do NOT add probes for code-style/lint rules — those belong in
  `invariants.json` (must_keep_regex) or in CI lint config.

## Stack portability

This command is stack-agnostic. The `required_tools` field references
MCP tool names by string, so swapping Odoo for Django/Rails only
requires editing the registered probes — the hook, registry schema,
and `/probe-add` workflow are unchanged. Ship the toolkit upstream;
each project registers its own probes.
