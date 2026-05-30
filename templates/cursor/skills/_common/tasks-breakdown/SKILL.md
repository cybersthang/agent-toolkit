---
name: tasks-breakdown
description: Spec Kit Phase 3 — TASKS. Take a clarified spec at `.agent-toolkit/specs/<branch>/<slug>.md` (status=`grilled` / `clarified`) and emit `tasks.md` next to it — a discrete, verifiable task list the agent will execute under autonomy. Auto-fired by the agent right after `/clarify` finishes; can also be invoked manually via `/tasks <slug>`. DEV reviews tasks.md, then types `/implement <slug>` to start the auto-chain (analyze → implement → verify).
---

# Tasks Breakdown — Spec Kit Phase 3

> Purpose: turn the spec's Implementation Decisions + User Stories into a
> linear list of self-contained tasks the agent can execute one at a time
> under autonomy. Each task carries its own acceptance + verification step,
> so PASS/FAIL is mechanical, not subjective.

## When to apply

- The agent auto-invokes this skill **right after `/clarify` completes**
  (one shot, same session — see "Auto-chain" below).
- The user types `/tasks <slug>` to re-emit tasks for an already-clarified
  spec (e.g. after a manual spec edit).

## When to SKIP

- Spec status is `draft` (not yet through `/clarify`) → refuse, tell DEV
  to run `/clarify <slug>` first.
- A `tasks.md` already exists next to the spec with `status: approved`
  in its frontmatter → refuse to overwrite silently; ask DEV to edit
  manually or pass `--regenerate`.
- Spec has no `acceptance_evals` block in frontmatter → refuse; tell DEV
  to run `/clarify` (which auto-refines the eval skeleton from `/plan`).

## Procedure

### Step 0 — Locate spec

The agent resolves spec by slug:

```
Glob: .agent-toolkit/specs/**/<slug>.md
```

Pick the most-recently-modified hit if multiple. If 0 hits → refuse and
tell DEV to run `/plan <slug>` first.

### Step 1 — Load spec + acceptance_evals + constitution

Parallel reads:

- The spec file (full body + frontmatter).
- `.agent-toolkit/constitution.md` — toolkit-level principles (karpathy +
  canonical decisions summary). Tasks must not violate constitution.
- `.agent-toolkit/invariants.json` — any `must_keep_regex` patterns the
  tasks could accidentally strip.
- `.codex/canonical_decisions.json` — stack conventions.

### Step 2 — Emit `tasks.md` next to the spec

Path: `.agent-toolkit/specs/<branch>/<slug>/tasks.md` (use the spec's
parent dir). This is the **only supported layout** as of toolkit v0.5.1.

**Migration from legacy flat layout** (`.agent-toolkit/specs/<slug>.md`):
if the spec is still at the flat path, the agent MUST migrate before
emitting tasks:

1. Create `.agent-toolkit/specs/<branch>/<slug>/` (use `_default` for
   branch if not in a git repo).
2. Move `.agent-toolkit/specs/<slug>.md` → `<branch>/<slug>/spec.md` (or
   `<branch>/<slug>.md` — pick the convention the rest of the project
   uses; both work because hooks rglob).
3. Move `.agent-toolkit/specs/<slug>.tasks.md` (if it exists from an
   older flow) → `<branch>/<slug>/tasks.md`.
4. Continue with tasks emission at `<branch>/<slug>/tasks.md`.

> Tooling note: hooks (`verify_lint`, `verify_nudge`,
> `analyze_halt_gate`) use `rglob` so legacy files still work without
> migration, but new emissions always use branch-scoped — keep the tree
> consistent.

Frontmatter:

```yaml
---
tasks_for: <slug>
status: draft        # draft → approved (by DEV "/implement") → done
created: <YYYY-MM-DD>
last_updated: <YYYY-MM-DD>
auto_chain_after_approval: true   # /implement triggers /analyze→implement→/verify
---
```

Body — one section per task, in dependency order:

```markdown
## T1 — <one-line goal>

- **Touches:** <comma-sep file paths from spec §3 Affected Modules>
- **Depends on:** <T0 if any, else "none">
- **Acceptance:** <observable outcome — NOT "code compiles". Cite an
  acceptance_eval id if one matches: "covers `us1-flag-set`".>
- **Verification:** <exact MCP call or shell command. Example:
  `mcp__postgres__run_query("SELECT count(*) FROM …")` returns `42`.>
- **Risk:** low | medium | high — short reason if not low.

## T2 — …
```

**Rules:**

1. **Every User Story → ≥1 task.** A story without a covering task is a
   spec drift — STOP and tell DEV before emitting tasks.
2. **Every `acceptance_evals` entry → cited by exactly 1 task.** If an
   eval has no task → flag as unreachable.
3. **No "Refactor sibling file X" tasks** unless spec §3 lists that file
   as "extend" or "refactor". Otherwise out-of-scope.
4. **Verification step is concrete.** "Run tests" is not a verification
   step; "`pytest tests/test_foo.py::test_bar` exits 0" is.
5. **Tasks ≤ 30 LOC of new/changed code each.** Bigger → split. The unit
   the agent executes between verifications.
6. **No "Document X" tasks** unless the spec explicitly listed docs as a
   User Story. Auto-docs is scope creep.

### Step 3 — Emit summary + STOP (DEV review gate)

After writing tasks.md, print 5-10 lines to DEV:

```
Tasks ready — <branch>/<slug> · <N> tasks · <M> total LOC budget
- T1: <one-line goal>
- T2: …
- T<N>: <one-line goal>

Coverage:
  ✓ Stories: <stories-covered>/<stories-total>
  ✓ acceptance_evals: <evals-cited>/<evals-total>
  <warning if any story or eval uncovered>

Parallelism (python3 tools/wave_planner.py plan <tasks.md>):
  <K> parallel wave(s), max width <W> — e.g. wave 3 = [T3, T4] run concurrently
  (or "all sequential — no provably file-disjoint tasks")

→ DEV review tasks.md, gõ `/implement <slug>` để bắt đầu auto-chain
  (analyze → implement → verify). Hoặc edit tasks.md, gõ `/tasks <slug> --regenerate`.
```

> **Parallelism is automatic at /implement, conservative by construction.**
> Run `python3 tools/wave_planner.py plan <tasks.md>` to preview the waves.
> `/implement` dispatches each ≥2-task wave as concurrent sub-agents (file
> -disjoint zones enforced by `parallel_conflict_guard`); anything not
> provably disjoint stays sequential. To MAKE tasks parallelizable, give each
> a precise, NON-overlapping `Touches` list (no globs) — that is the only
> signal the planner trusts.

**STOP — DO NOT auto-trigger /analyze or /implement in the same turn.**
This is the DEV review gate: the user reads tasks.md, edits if needed,
then explicitly types `/implement <slug>` to authorize the auto-chain.

## Auto-chain entry

The `/clarify` skill, on completion (DEV typed "done" / "xong"), is
expected to call this skill inline as its final step. The DEV does
**not** need to type `/tasks` manually — but they can, to re-emit.

After this skill emits tasks.md, the flow stops here until DEV
authorizes `/implement`.

## Module-agnostic — no hardcoding

Task descriptions must cite paths discovered from the spec, not invented.
If a path doesn't exist on disk yet (will be created), mark it `(new)`.

## Anti-rationalizations

| Temptation | Counter |
|---|---|
| "Task is small, no acceptance line needed" | Without acceptance, /verify cannot tell PASS from FAIL. Mechanical verification is the whole point. |
| "Add a refactor task while I'm here" | Out-of-scope unless spec §3 lists it. Open a separate spec for the refactor. |
| "30 LOC is too small, group tasks" | The 30-LOC bound is what makes pause-and-verify cheap. Grouping defers the verification, which defers detection of drift. |
| "Story 5 is fuzzy, skip the task" | A fuzzy story is a `/clarify` gap. Send it back, do NOT silently drop. |

## Red flags — skill is failing if

- A User Story has zero covering tasks.
- An `acceptance_evals` entry is uncited by any task.
- A task lacks **Acceptance** or **Verification** line.
- The skill ran `/analyze` or any Edit in the same turn (must STOP).
- `tasks.md` written to a path other than next-to-spec.
- Tasks reference project-specific names (modules, DB, addon roots)
  that weren't in the original spec — fabrication.

## Sibling skills

- `plan-feature` — Phase 1 (creates the spec).
- `clarify` (was `grill`) — Phase 2 (refines spec + acceptance_evals).
- `analyze-artifacts` — Phase 3.5 (cross-artifact lint, fires from /implement).
- `verify-feature` — Phase 5 (real-data validation, fires from /implement).
- `<stack>-<version>-module-scaffold` — Phase 4 implementer for new modules.
