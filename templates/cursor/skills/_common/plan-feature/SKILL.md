---
name: plan-feature
description: Spec Kit Phase 1 — SPECIFY. The user invokes `/plan <feature>` to turn a feature request into a structured spec (Problem / Solution / Modules / User stories / Tests / Out-of-scope / Open Questions) BEFORE writing code. Entry-point of the 5-phase Spec Kit flow (PLAN → CLARIFY → TASKS → ANALYZE+IMPLEMENT → VERIFY). Open this skill WHEN the user says "make a plan for X", "write a PRD for Y", "/plan ...", or anything that will produce more than 30 lines of new code.
---

# Plan Feature — Spec Kit Phase 1: SPECIFY

> Purpose: before writing code, produce a clear spec both the user and the
> agent can look at. This skill does NOT interview the user (that is
> `/clarify`); it consolidates what the agent already knows about the
> codebase + the request into a first-draft spec, used as input for the
> CLARIFY phase.

This is **Phase 1** of the 5-phase Spec Kit flow:

```
DEV: /plan  →  /clarify
              ↓ (auto-fires after clarify done)
        /tasks  →  STOP (DEV review)
                    ↓
DEV: /implement
              ↓ (auto-chain)
        /analyze  →  execute tasks  →  /verify  →  report
```

## When to apply

- The user types `/plan <feature description>`.
- The prompt contains intents like "make a plan", "write a PRD", "create a
  spec for ...", "before coding, I want to ...".
- After a `clarification-gate` session where the answer is "I want to make
  this clear first, not code yet".

## When to SKIP

- Tiny requests (one-character edit, one-constant change).
- Read-only questions (read / understand / where is X).
- A spec already exists at `.agent-toolkit/specs/**/<slug>.md` for the same
  feature (Glob to find it across branch dirs) — open that spec and update
  it; do NOT create a new file.

## Procedure

### Step 0 — Minimal codebase discovery

Before writing the spec, call the codebase MCP to identify which modules the
feature will touch. Do NOT hardcode module names — discover at runtime.
Search 1-2 important keywords from the feature description (e.g. feature
"export daily activity report" → search `export`, `report`, `log`).

Purpose: the spec then cites real `path:line` references, not fabricated
structure.

### Step 1 — Generate the spec using this template

Compute the branch-scoped path:

```bash
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '_' | sed 's/^\.//')
branch=${branch:-_default}    # fallback if not in a git repo or detached
```

Write to `<workspace>/.agent-toolkit/specs/<branch>/<feature-slug>.md`
with frontmatter:

```yaml
---
spec: <feature-slug>
status: draft
phase: plan
created: <YYYY-MM-DD>
last_updated: <YYYY-MM-DD>
owner: <dev-name>
related_adr: <ADR-NNN if any>
related_jira: <ticket-id if any>
# feature_kind drives Step 1.8 of /verify (mandatory Real-Data Proof
# for classifier features). Set ONLY when keyword detection matches:
#   - classification: classify/phân loại/gán nhãn/tag each/BLOCK vs ASYNC/severity low|med|high
#   - aggregation:    count/đếm/distribution/phân bố/aggregate/gom nhóm
#   - contract:       atomic/idempotent/cached/deterministic/retries + contract|guarantee|invariant
# Omit the field entirely for generic features — don't ship `feature_kind: generic`.
feature_kind: <classification | aggregation | contract>  # OPTIONAL
---
```

Body has 8 sections (keep the order for cross-spec consistency):

```markdown
## 1. Problem Statement
<1 paragraph, from the user/dev viewpoint: what hurts today, what is wasted,
what is wrong. Do NOT mention the solution here.>

## 2. Solution (high-level)
<1 paragraph, still from the user viewpoint: after the feature ships, what
does the user see differently. Observable behaviour, NOT code, NOT models.>

## 3. Affected Modules / Files
<List the modules / files discovered in Step 0. Each line:
- `<path>` — role + expected change (new / extend / refactor / read-only).
If unknown → write "TBD — discover during GRILL phase".>

## 4. User Stories (numbered list)
1. As a <role>, I want <action>, so that <benefit>.
2. ...
<The longer the better — each story becomes an acceptance criterion later.>

## 5. Implementation Decisions
<Technical decisions at module/interface level, NO code snippet unless the
snippet is clearer than prose (state machine, schema, type shape).
Examples:
- Add field `flag_x` (boolean, default False) to model `res.partner`.
- Cron `_cron_export_daily` runs at 02:00, lock via `with_lock`.
- API contract: POST /export returns JSON {status, file_url}.>

## 6. Testing Decisions
<Describe important tests:
- Unit: file `tests/test_<name>.py`, uses `TransactionCase` or equivalent.
- Integration: end-to-end ORM probe via `<stack>-data-verification`.
- Manual smoke: where the user clicks, what they see.
Reference sibling tests if fixtures can be reused.>

## 7. Out of Scope
<List explicitly what is NOT in this PR — guards against scope creep.>

## 8. Open Questions (input for GRILL)
<3-7 questions the user must answer during GRILL before implement. Each
question is a decision not yet settled. Examples:
- Email validator for field `partner_email`: strict or lenient?
- Cron processes each partner serially or in batch?
- When export is empty → return empty file or HTTP 204?>
```

### Step 2 — Print summary for user review (do NOT implement)

Print a 5-10-line summary so the user sees what was written. The path to the
spec file is included. The final line MUST be one of:

- `→ Next: run /grill to stress-test the Open Questions above.`
- `→ To skip clarify, run /tasks <slug> --no-evals (rare; evals stay draft).`

### Step 3 — STOP

After writing the spec, stop. Do NOT call Edit/Write on source files. Do NOT
implement. Wait for the user to type `/clarify <slug>`.

## Module-agnostic — no hardcoding

The spec must not hardcode any module name from the current project.
Discover via MCP. If a name must appear (because the user spelled it out),
keep the name the user typed — do not auto-rename.

## Anti-rationalizations

| Temptation | Counter |
|---|---|
| "The feature is simple, no spec needed" | A 6-section spec takes 3-5 minutes; throw-away code costs hours. The spec threshold is lower than you think. |
| "I can guess the Open Questions" | No. That is the CLARIFY phase — the user decides, you don't guess. |
| "Spec and code in parallel for speed" | Spec Kit flow is sequential: PLAN → CLARIFY → TASKS → IMPLEMENT → VERIFY. Parallel = drift. |
| "What if the user changes requirements after the spec?" | Update the spec file (bump `last_updated`, add a change-log section). The spec is a contract — change the contract before changing the code. |

## Red flags — the skill is failing if

- The spec file lacks any of the 8 sections.
- "Affected Modules" is all TBD (Step 0 was skipped).
- "User Stories" has fewer than 3 items (not enough detail).
- "Open Questions" is empty (everything was assumed — make sure that is not the case).
- You called Edit/Write on a source file in the same turn (violates STOP).
- The spec was written to the wrong location (not `.agent-toolkit/specs/<branch>/`).

## Sibling skills

- `clarification-gate` — runs BEFORE, ensures the request is understood.
- `clarify` — Phase 2, refines Open Questions + acceptance_evals.
- `tasks-breakdown` — Phase 3, emits tasks.md (auto-fired by clarify).
- `analyze-artifacts` — Phase 3.5, cross-artifact lint (auto-fired by implement).
- `verify-feature` — Phase 5, real-data validation after implement.
- `<stack>-codebase-discovery` — discovers modules in Step 0
  (version-aware: Step 0 reads `__manifest__.py` and loads matching
  references — same folder works for Odoo 12 → 20+).
- `<stack>-tdd` — TDD loop during implement (version-aware).
- `<stack>-debug-troubleshoot` — debugger when implement hits errors
  (version-aware).

## Reference

Inspired by:
- [mattpocock/skills/engineering/to-prd](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-prd/SKILL.md) (MIT).
- [mattpocock/skills/engineering/zoom-out](https://github.com/mattpocock/skills/tree/main/skills/engineering/zoom-out) (MIT).
- GitHub Spec Kit (https://github.com/github/spec-kit) — SPECIFY phase concept.
