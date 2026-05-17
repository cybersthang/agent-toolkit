---
description: ECC eval-harness pattern — write CONCRETE pass/fail criteria into the spec BEFORE `/go`. Each User Story must have 1+ MCP probe (code grader, data grader, model grader) + a fixed expected value. /verify then just re-runs those probes → "correct/wrong" becomes a mechanical check.
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
argument-hint: "<spec-slug>"
---

# /eval-define — Define acceptance evals BEFORE implementation

## Upstream provenance

- **Repo**: https://github.com/affaan-m/everything-claude-code · author [@affaan-m](https://github.com/affaan-m)
- **Upstream skills**:
  - `skills/eval-harness/SKILL.md` — https://github.com/affaan-m/everything-claude-code/blob/main/skills/eval-harness/SKILL.md
  - `skills/agent-eval/SKILL.md` — https://github.com/affaan-m/everything-claude-code/blob/main/skills/agent-eval/SKILL.md
- **Adopted**: 2026-05-17 — adapted for the local MCP toolset (postgres/run_python_tests graders instead of generic npm/pytest).
- Full mapping: see memory `reference_ecc_upstream` (`~/.claude/projects/<encoded>/memory/`).

## Goal

Close the recurring gap: "after implement, /verify runs by feel, the agent
fails to catch wrong cases against real data". Inspired by ECC
`eval-harness` skill: **eval = unit test of AI work**.

After `/plan` + `/grill`, BEFORE `/go`, this command appends an
`acceptance_evals:` block into the spec frontmatter. Each entry is an MCP
probe with a fixed expected value — `/verify` re-runs exactly those probes,
output is mechanical PASS/FAIL, no "looks fine".

Argument: `$ARGUMENTS` = spec slug (required). If empty → list specs at
status `grilled` and ask the user to pick.

## Procedure

1. **Read the spec** — `Read .agent-toolkit/specs/<slug>.md`. Required:
   - `status: grilled` or `planned` (NOT implementing — eval must be defined
     BEFORE code, not after).
   - Section `## User Stories` (numbered) or `## Implementation Decisions`.

2. **Refuse if**:
   - Spec is at `status: implementing | verified | gaps-found` → eval must
     precede Phase 3 (`/go`). Tell the user: to add eval for existing code,
     use `/bug-to-test` instead.
   - No User Stories found → go back to `/plan` for measurable acceptance.

3. **Apply `claim-falsification` skill BEFORE designing the probe** — for each User Story:
   - Parse the story into claim_text (subject_X, property_P, params).
   - Match against the recipe catalog (1-15 in the skill); or derive a
     custom one if the claim shape is not present.
   - Output `recipe: <id>` in the probe YAML (see `[[claim-falsification]]`).

4. **For each User Story, design 1+ probe** per ECC categorization:

   | Grader kind | When to use | Suggested MCP tool |
   |---|---|---|
   | **code** | Deterministic logic, writable test (pytest) | `mcp__<stack>-<v>__run_python_tests` |
   | **data** | "Does the ORM/DB return the right value?" | `mcp__<stack>-<v>__postgres_read_query` or `eval_orm_expression` |
   | **shape** | Endpoint returns JSON in the right structure | `Bash curl -s ... | jq` + assert keys |
   | **regression** | A past bug that must not return | `run_python_tests` on the regression test file |
   | **model** (last resort) | Output requires subjective judgement | Mark explicitly + p@3 target ≥ 0.9 |

   **Hard rule**: prefer code/data graders; use a model grader only when no
   alternative exists (per ECC: "code graders deterministic > probabilistic").

5. **Probe template** (1 story → 1 probe entry in YAML):

   ```yaml
   - id: us1-<short-claim-slug>
     story: "Story 1 — <user story summary>"
     grader: data
     probe:
       tool: mcp__<stack>-<framework><version>__postgres_read_query
       args:
         sql: |
           SELECT COUNT(*) AS n
           FROM <table>
           WHERE <date_field>::date = CURRENT_DATE
     expected:
       assertion: "n > 0"
     target_pass_rate: 1.0
     rationale: "<reason — ref to ADR or spec section>."
   ```

6. **Probe quality checklist** — before writing the spec, ensure:
   - [ ] `expected` is a concrete value / assertion, NOT "looks fine".
   - [ ] `probe.tool` is a real MCP + runnable args (smoke-test once in the same turn).
   - [ ] `target_pass_rate` defaults to `1.0` for code/data; ≥ 0.9 for model.
   - [ ] `rationale` references a spec section or ADR.

7. **Smoke-test one representative probe** — run the first probe right now.
   If it errors (MCP timeout / SQL syntax / model missing) → fix the probe
   before writing the spec. This catches what ECC calls *false confidence*.

8. **Edit spec frontmatter** — append/merge the `acceptance_evals:` block.
   Final shape example:

   ```yaml
   ---
   spec: <your-spec-slug>
   status: grilled            # do NOT change status
   phase: grill
   ...existing keys...
   acceptance_evals:
     - id: us1-<short-claim-slug>
       story: "Story 1 — <summary>"
       grader: data
       probe:
         tool: mcp__<stack>-<framework><version>__postgres_read_query
         args: {sql: "<SQL>"}
       expected: {assertion: "<assertion>"}
       target_pass_rate: 1.0
       rationale: "..."
     - id: us2-<short-claim-slug>
       story: "Story 2 — ..."
       grader: code
       probe:
         tool: mcp__<stack>-<framework><version>__run_python_tests
         args: {module: "<module>", test: "<test_path>"}
       expected: {result: "PASS"}
       target_pass_rate: 1.0
       rationale: "..."
   ---
   ```

9. **Print a summary for the user** (5-10 lines):

   ```
   ✓ Eval defined for `<slug>` — N probe(s) written to frontmatter.
   - us1-<slug-a> (data) — smoke OK
   - us2-<slug-b> (code) — smoke pending
   - us3-<slug-c> (data) — smoke OK

   Next:
   - /go <slug>     → enable autonomy, implement.
   - /verify <slug> → re-run all probes, emit PASS/FAIL table.
   ```

## Refuse / clarify when

- The spec does not exist / wrong slug.
- The spec is already at status `implementing` or beyond → refuse, suggest `/bug-to-test`.
- User Stories are too vague ("nicer UI") → refuse, send back to `/plan`
  for measurable stories.
- The user wants a model grader on 100% of stories → warn: ECC recommends
  code/data first, model grader only as a fallback.

## Must NOT

- Do NOT modify `status` in the frontmatter (eval-define only adds probes;
  it does not advance phase).
- Do NOT write a probe without smoke-testing at least one entry — that
  creates "phantom probes".
- Do NOT accept `expected: <free text>`; it must be a JSON value or a
  one-line assertion.
- Do NOT duplicate eval id per story — max 3 evals per story (keeps
  /verify fast).
