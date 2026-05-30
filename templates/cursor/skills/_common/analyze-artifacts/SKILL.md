---
name: analyze-artifacts
description: Spec Kit Phase 3.5 — ANALYZE. Cross-artifact consistency check between spec.md ↔ tasks.md ↔ acceptance_evals ↔ constitution BEFORE implement. Catches drift early so the agent doesn't burn token implementing the wrong thing. Auto-fired as the first step of `/implement`; also invokable manually via `/analyze <slug>`. Reports PASS / WARN / BLOCK. On BLOCK the auto-chain halts and reports to DEV.
---

# Analyze Artifacts — Spec Kit Phase 3.5 (ANALYZE)

> Purpose: pre-flight lint that compares the spec, the task breakdown,
> the acceptance evals, and the toolkit constitution. A drift between
> any pair is a future bug; catching it BEFORE implement saves the
> implement+verify+re-implement loop.

## When to apply

- The `/implement` skill calls this as its first inline step (auto).
- The user types `/analyze <slug>` to lint manually.

## When to SKIP

- Spec status is `draft` (not yet clarified) → refuse.
- `tasks.md` is missing → refuse, tell DEV to run `/tasks <slug>` first.
- `tasks.md` has `status: done` → no-op (analysis was already passed
  before implement started).

## Procedure

### Step 0 — Locate artifacts

```
Glob: .agent-toolkit/specs/**/<slug>.md       → spec
Glob: .agent-toolkit/specs/**/<slug>/tasks.md → tasks (canonical)
```

If tasks.md is absent but a legacy flat `<slug>.tasks.md` exists → BLOCK
with the migration hint from `tasks-breakdown/SKILL.md` Step 2. New
runs never emit the legacy form.

If spec absent → BLOCK.

### Step 1 — Load all artifacts (parallel reads)

- The spec file (frontmatter + body).
- The tasks file.
- `.agent-toolkit/constitution.md` — toolkit principles.
- `.agent-toolkit/decision-log.md` — ADRs.
- `.agent-toolkit/invariants.json` — enforced invariants.
- `.codex/canonical_decisions.json` — stack conventions.

### Step 2 — Run 7 checks; emit `analyze-report.md`

Each check returns one of: ✅ PASS / 🟡 WARN / 🔴 BLOCK.

| # | Check | BLOCK condition | WARN condition |
|---|---|---|---|
| C1 | **Story coverage** | ≥1 User Story has zero covering tasks | A task touches a file not listed in spec §3 |
| C2 | **Eval coverage** | An `acceptance_evals` entry has no task citing it | An eval has `grader: TBD` or `expected.assertion: TBD` |
| C3 | **Out-of-scope guard** | A task touches a file the spec §7 Out-of-Scope forbids | A task verb matches "refactor"/"cleanup" but spec didn't ask for that |
| C4 | **Invariant compatibility** | A task description proposes stripping a `severity: blocker` `must_keep_regex` pattern | A task could violate a `severity: warn` pattern |
| C5 | **Constitution compatibility** | A task violates a core principle in `constitution.md` (e.g. proposes hard-coded module name, bypasses canonical_decisions) | Style hint from constitution unaddressed in task |
| C6 | **Path realism** | A task cites `<path>` that doesn't exist AND isn't marked `(new)` | A task spans 3+ files (likely too coarse — should split) |
| C7 | **Verification concreteness** | A task's Verification step says "tests pass" / "code compiles" / "looks right" — non-mechanical | Verification cites an MCP tool name that isn't in `.mcp.json` |

### Step 3 — Emit `analyze-report.md` next to tasks.md

```markdown
## Analyze Report — <slug> · <ISO datetime>
Spec: <path> · status=<status>
Tasks: <path> · <N> tasks

| # | Check | Status | Detail |
|---|---|---|---|
| C1 | Story coverage | ✅ PASS | 4/4 stories covered |
| C2 | Eval coverage | 🟡 WARN | 1 eval `us3-…` has grader=TBD |
| C3 | Out-of-scope | ✅ PASS | — |
| C4 | Invariant compat | ✅ PASS | — |
| C5 | Constitution | ✅ PASS | — |
| C6 | Path realism | 🔴 BLOCK | T4 cites `addons/foo/bar.py` — file not on disk, no (new) marker |
| C7 | Verif concreteness | ✅ PASS | — |

### Verdict
- ✅ PASS: 5
- 🟡 WARN: 1
- 🔴 BLOCK: 1
- **Verdict:** BLOCK — fix T4 before /implement.
```

### Step 4 — Decide auto-chain continuation

- **All PASS** (no WARN, no BLOCK) → return verdict `READY`. If invoked
  from `/implement`, the auto-chain continues to the implement phase.
- **WARN only** → return verdict `READY-with-warnings`. Auto-chain
  continues but the warnings are surfaced in the implement banner.
- **Any BLOCK** → return verdict `HALT`. Auto-chain stops here. The
  agent prints the analyze-report and waits for DEV to fix the listed
  blockers + re-run `/analyze <slug>` (or `/clarify <slug>` if blockers
  are spec-level).

> **HALT is enforced — not honor-system.** The PreToolUse hook
> `.claude/hooks/analyze_halt_gate.py` scans every
> `.agent-toolkit/specs/**/analyze-report.md` on each Edit / Write /
> MultiEdit / NotebookEdit. If the LAST verdict line says HALT (or BLOCK
> count > 0), the tool call is **blocked** with the slug + blockers + 3
> resolution paths. Toolkit-managed paths (`.agent-toolkit/`, `.codex/`,
> `.claude/`, `.cursor/`) are allow-listed so the agent can still emit
> the corrected report. DEV emergency bypass:
> `touch .agent-toolkit/.analyze-bypass` (does NOT auto-expire — delete
> after use).

## Anti-rationalizations

| Temptation | Counter |
|---|---|
| "Tasks.md and spec.md agree — skip the check" | The whole point: agents agree with themselves. The 7 checks force friction against an outside reference (invariants, canonical_decisions, on-disk reality). |
| "Just demote BLOCK to WARN to continue" | A BLOCK means downstream verify will catch it after token-expensive implement. Cheaper now. |
| "C6 path-doesn't-exist is fine, I'll create it" | Then mark it `(new)` in the spec. The marker exists so the check distinguishes "going to create" from "fabricated path". |

## Red flags — skill is failing if

- Returned `READY` while a BLOCK condition was present.
- Did not emit `analyze-report.md` to disk (verify_lint hook will see no
  artifact, and the analyze_halt_gate hook can't enforce a verdict that
  was never written).
- Ran any Edit/Write on source files (analyze is read-only on code).
- BLOCK condition reported but auto-chain still triggered `/implement` —
  this is now caught by the analyze_halt_gate hook, but a working agent
  shouldn't rely on the hook to stop it.

## Sibling skills

- `plan-feature` — Phase 1.
- `clarify` — Phase 2 (refines so analyze passes).
- `tasks-breakdown` — Phase 3 (emits the tasks.md this skill lints).
- `verify-feature` — Phase 5 (post-implement real-data check).
