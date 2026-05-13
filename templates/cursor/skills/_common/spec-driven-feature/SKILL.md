---
name: spec-driven-feature
description: Write a structured spec BEFORE coding a new feature, module, or non-trivial refactor. Forces the assumptions, success criteria, and boundaries into a 6-field document the user reviews and approves. Open this skill whenever the user asks for "add X feature", "tạo module mới", "implement Y", "refactor Z" — anything that will produce > 30 lines of new code.
---

# Spec-Driven Feature — Specify → Plan → Tasks → Implement

> Default failure mode: the agent reads a one-line request, fills in the
> blanks silently, and writes code that solves a *different* problem than
> the user had in mind. This skill is the antidote: surface every gap
> *before* a single line is written, and freeze the answers in a spec the
> user can point at when something later drifts.

Pair this skill with the stack-specific scaffold skill (e.g.
`odoo-12-module-scaffold`) for the BUILD phase. This skill owns SPECIFY +
PLAN + TASKS; the scaffold skill owns IMPLEMENT.

## Four phases (advance only with user OK between each)

```
SPECIFY  →  PLAN  →  TASKS  →  IMPLEMENT
   ↑          ↑        ↑          ↑
   you        you      you        scaffold skill takes over
```

The first three phases produce text the user reads and approves. Phase 4
runs only after explicit go-ahead.

## When to skip this skill

- The user's request already specifies every field below (rare — usually
  one line is missing).
- A trivial in-place edit the user spelled out line-by-line.
- A bug fix isolated to a single function (use `code-review` +
  `<stack>-debug-troubleshoot` instead).
- An exploratory "what would it look like if…?" question (no commitment
  yet — answer in prose, not a spec).

## Phase 1: SPECIFY — the 6-field document

Produce **all six fields**. Marking a field "TBD — need user input" is
acceptable; silently omitting it is not.

### 1. Objective
One sentence stating what the user gets when the feature is done. Phrased
as a user-observable outcome, not as an implementation detail.

> ❌ "Add a JSON field to res.partner."
>
> ✅ "When the API exporter runs, partners flagged `is_nakivo_customer`
> appear in the dump with their NAKIVO contract id."

### 2. Commands / Entry points
The exact ways the feature is invoked. Buttons, cron jobs, controllers,
shell commands, ORM methods — be specific. If the entry point doesn't
exist yet, name it and where it will live.

### 3. Project Structure
The files that will be created or modified, with one-line purpose each.
Use the stack's discovery skill (e.g. `odoo-12-codebase-discovery`) to
find where similar files live — never invent a new layout.

### 4. Code Style
Stack conventions the implementation MUST honor. Pull from the registry
(`<stack>-deterministic-answers`) and `.cursor/rules/*.mdc`. Cite, don't
re-derive.

> Example for Odoo 12:
> - `@api.multi` everywhere, never `@api.one`.
> - Logger via `_logger = logging.getLogger(__name__)`.
> - String literals user-facing → wrap with `_()`.

### 5. Testing Strategy
Three sub-questions the spec must answer:

- **Unit:** which functions get pytest/`tagged` unit tests?
- **Integration:** does this need an end-to-end ORM test
  (`<stack>-data-verification` recipe)?
- **Manual smoke:** what does the user click/check after install to know
  it works?

"TBD — feature is data-only, no behavior to test" is acceptable when
justified; "tests later" is not.

### 6. Boundaries — Always / Ask first / Never
Three lists that prevent scope creep mid-implementation.

- **Always do:** non-negotiables (e.g. "register `ir.model.access` for the
  new model", "preserve uninstall path").
- **Ask first:** decisions the user owns (e.g. "if a related record is
  missing, fail-fast vs silently skip — ask").
- **Never do:** explicit out-of-scope (e.g. "do not touch the legacy
  `partner_v1` table", "do not introduce a new dependency").

## Phase 2: PLAN — components + order

After SPECIFY is approved:

1. List the components/files in the order they will be built.
2. Mark dependencies (`B needs A first`).
3. Flag any *unknown unknowns* — places where you'll need to read code
   or run a probe before writing the next file. Spec them as discovery
   tasks (e.g. "T0 — read existing `nakivo_export.py` to confirm field
   ordering"), not "I'll figure it out".

Stop and ask for OK before producing tasks.

## Phase 3: TASKS — discrete + verifiable

Each task is a self-contained unit with:

- **ID:** `T1`, `T2`…
- **Goal:** one sentence.
- **Acceptance criteria:** observable, not "code is written" — e.g.
  "running `<expression>` via realdata_test returns `expected_value`",
  "view loads in dev DB without error".
- **Verification step:** the exact command / MCP call.

A task that lacks an acceptance line is a `TODO`, not a task — split or
sharpen it. Don't accept tasks whose only success criterion is "code
compiles".

Stop and ask for OK before implementing.

## Phase 4: IMPLEMENT — hand off

Hand the spec + plan + tasks to the stack scaffold/code skill. As that
skill executes:

- After each task, run its verification step and report PASS/FAIL.
- If a task discovers something that contradicts SPECIFY (e.g. the file
  doesn't exist where assumed), **stop and update the spec** — do not
  silently work around it. The spec is the contract.

## Output contract

The spec lives at `.codex/specs/<feature-name>.md` (create the dir if
absent — gitignored unless the user wants to commit it). Open the file
with a frontmatter block:

```yaml
---
spec: <feature-name>
status: draft | approved | implementing | done
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
owner: <user>
related_jira: <NKV-…> (optional)
---
```

When the user approves Phase 1, set `status: approved`. When Phase 4
starts, set `status: implementing`. When all tasks pass, set
`status: done`.

## Rationalizations — counter each one

| Rationalization | Counter-argument |
|---|---|
| "It's a small change, I don't need a spec" | The cost of writing 6 short fields is ~2 minutes. The cost of throwing away the wrong implementation is hours. The line where this trade-off flips is much smaller than the agent's intuition suggests. |
| "I can fill in the boundaries while coding" | You won't. The mid-flight you'll silently extend scope to make a problem tractable; the user will see only the final diff. Boundaries up front are the audit log of what you *didn't* do. |
| "Testing strategy can wait until after the feature works" | "Feature works" is meaningless without a test. The test is what defines "works". Write the strategy first, even if you implement tests last. |
| "The user is in a hurry, skipping SPECIFY is faster" | Skipping SPECIFY produces an artifact the user has to either accept (wrong) or reject (slower than if you'd asked). Negotiate scope at the spec, not at the PR. |

## Red flags

- Spec missing any of the 6 fields without a "TBD" explanation.
- Acceptance criteria phrased as "code is correct" or "tests pass".
- "Always do" list is empty (every stack has non-negotiables — failure to
  list them means you didn't check the rules).
- Phase 4 started without `status: approved` on the spec file.
- A discovery during implementation contradicted the spec and the spec
  was *not* updated.

## Sibling skills

- `<stack>-<version>-module-scaffold` — Phase 4 implementer for new modules.
- `<stack>-<version>-code-patterns` — supplies "Code Style" content.
- `<stack>-<version>-deterministic-answers` — supplies cited conventions.
- `<stack>-<version>-data-verification` — supplies "Verification step" tooling.
- `code-review` — the gate the feature passes through before merge.
- `doubt-driven-review` — apply per task before reporting PASS.
