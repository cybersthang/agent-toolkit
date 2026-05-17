---
description: ECC eval-harness pattern (retrofit variant) — convert the "Testing Decisions" section (written as free-form markdown bullets) of a spec at status `implementing` / `verified` / `gaps-found` into a machine-runnable `acceptance_evals:` YAML block. Unlike `/eval-define` (which only runs before /go), this command is designed for specs that have ALREADY been implemented but whose pass/fail criteria remain in prose.
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
argument-hint: "<spec-slug>"
---

# /eval-backfill — Retrofit acceptance evals for an already-implemented spec

## Upstream provenance

- **Repo**: https://github.com/affaan-m/everything-claude-code · author [@affaan-m](https://github.com/affaan-m)
- **Upstream skills**: `skills/eval-harness/SKILL.md` + `skills/ai-regression-testing/SKILL.md` (combining 2 patterns: define + persist).
- **Adopted**: 2026-05-17 — a variant of `/eval-define` for retrofitting already-implemented specs.

## Goal

`/eval-define` refuses any spec at status ≠ `grilled` (correct — eval must be
defined before code). But a project may have many specs already in flight
with "Testing Decisions" written in prose (markdown bullets); to machine-
verify them, the team needs to convert to `acceptance_evals:` YAML WITHOUT
losing the original content.

This is backfill: an old spec → new persistent evals → /verify becomes
mechanical.

Argument: `$ARGUMENTS` = spec slug (required). If empty → list specs with
status ∈ {`implementing`, `verified`, `gaps-found`} and ask the user to pick.

## Procedure

1. **Read the spec** — `Read .agent-toolkit/specs/<slug>.md`. Required:
   - `status` ∈ {`implementing`, `verified`, `gaps-found`} (NOT `draft`,
     NOT `grilled` — those cases use `/eval-define` instead).
   - Section `## 6. Testing Decisions` OR `## Testing` OR `## Tests`.
   - Section `## 4. User Stories` OR `## User Stories`.

2. **Refuse if**:
   - The spec has no Testing section → go back to `/plan` or suggest
     `/eval-define` (the user must define from scratch).
   - Spec status=`draft` / `grilled` → use `/eval-define` instead.

3. **Apply `claim-falsification` skill on each bullet** — parse the bullet
   → claim_text → match a recipe in the catalog (1-15). If the bullet only
   describes a passive test (count rows), promote it to active perturbation
   per the matching recipe (caching → recipe 3, idempotency → recipe 4,
   ...). See `[[claim-falsification]]`.

4. **Parse the Testing section** (heuristic, the user will review):
   - Each top-level bullet (`- ` or `* `) = 1 eval probe candidate.
   - Pattern priority:
     - `Test N — <title>: <body>` → name = title, body = description.
     - `<endpoint/model> → <CLASSIFICATION>` → grader=data, expected.assertion.
     - `run <script.py>` / `via MCP <tool>` → grader=code.
     - `expected <value>` / `kỳ vọng <value>` → expected JSON value.
     - `deterministic` / `10/10 identical` / `pass^k` → mark `pass_at_k: k`.
   - Unparseable pattern → mark `[needs-manual-review]` in the proposal.

5. **Cross-reference User Stories**: for each probe candidate, assign the
   closest Story # by:
   - Keyword overlap (endpoint name, model name, action name).
   - If no Story matches → mark `story: "?"` and ask the user.

6. **Smoke-test at least one representative probe** right now:
   - `grader: data` → smoke via `postgres_read_query` on the SQL.
   - `grader: code` → smoke via `run_python_tests` on the path.
   - If smoke fails (SQL syntax / missing file) → mark the probe
     `[smoke-fail: <reason>]`, do NOT apply to the spec.

7. **Render proposal** for the user to approve (do NOT apply yet):

   ````markdown
   ## Eval backfill proposal — `<slug>`

   Parsed N candidates from Section <6/Testing>. M smoke-OK, K need manual review.

   ```yaml
   acceptance_evals:
     - id: <test-id-from-section6>
       story: "Story <N> — <user story summary>"
       source_section: "Section 6 · Test <K> — <title>"
       grader: data
       probe:
         tool: mcp__<stack>-<framework><version>__postgres_read_query
         args:
           sql: |
             SELECT <field> AS <alias>
             FROM <table>
             WHERE <predicate>
       expected:
         assertion: "<alias> <op> <expected>"
       target_pass_rate: 1.0
       smoke: ok | pending | smoke-fail:<reason>
       source_bullet: "<original bullet from Section 6>"
     - id: <next-test-id>
       ...
   ```

   Approve `y` to edit the spec, `n` to cancel, or reply inline edits to
   adjust a probe.
   ````

8. **On approval**:
   - `Edit` the spec frontmatter — insert (or merge) the `acceptance_evals:` block.
   - Do NOT change `status` (stays at `implementing` / `verified` / `gaps-found`).
   - Set `last_updated`, append a history line:
     ```
     ## Eval backfill history
     - <YYYY-MM-DD>: Backfilled N evals from Section 6 (M smoke-OK, K manual-review).
     ```

9. **Auto-suggest `/verify <slug>`** immediately after backfill — now that
   probes are mechanical, `/verify` output moves from ad-hoc to deterministic.

## Refuse / clarify when

- Section 6 is too vague (bullets like "full tests") → cannot parse → refuse,
  ask the user to rewrite the bullets with concrete endpoint/model/expected.
- An `acceptance_evals:` block already exists AND overlaps > 50% with the
  proposal → warn about duplication, ask to merge / replace / skip.
- The user passes a slug at `draft` / `grilled` → redirect to `/eval-define`.

## Must NOT

- Do NOT overwrite an existing `acceptance_evals:` block (use merge instead).
- Do NOT delete the original Section 6 — the prose is still valuable for the
  user; YAML is added to frontmatter as a sibling, not a substitute.
- Do NOT mark `smoke: ok` without actually running the probe — that creates
  false confidence.
- Do NOT guess `expected.assertion` from a short bullet ("full tests") —
  there must be a concrete expected value in the original bullet, otherwise
  mark `[needs-manual-review]`.
