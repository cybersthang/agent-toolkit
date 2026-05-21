# DEV Live Exercise — Validate Layer C "xuyên suốt"

**Purpose**: only DEV can prove that hooks actually fire in Claude Code's
real dispatcher (not just subprocess simulation). This 30-minute manual
session closes the **Layer C** gap that AGENT cannot reach independently.

After completing this exercise:
- Layer C score moves from 5/10 (`[assumption]`) → 10/10 (empirical).
- Overall xuyên suốt: ~90% → **≥98%**.

---

## Prerequisites

1. agent-toolkit installed (v0.8.0+) in target project.
2. `setup.py update --apply` propagated all hooks to project.
3. `.agent-toolkit/` contains: invariants.json, coverage_config.json
   (with feature_scope_globs), acceptance-probes.json.
4. Project has at least 1 git branch != main.

---

## Step-by-step

### Step 1 — Restart Cursor / Claude Code

Close all Cursor windows / Claude Code sessions. Re-open.

**Why**: Claude Code dispatcher loads `.claude/settings.json` on
session start. Existing sessions keep old hook config.

Verify via Claude Code "skills" surface — should show
`implement-notes`, `gap-status`, etc. (v0.8.0 ships these).

### Step 2 — Create feature branch + spec

```bash
git checkout -b feature-live-exercise
```

Have AGENT run `/plan live-exercise`. Confirm spec emitted at
`.agent-toolkit/specs/**/live-exercise.md` with:
- `acceptance_evals: [...]` non-empty.
- `affected_modules: ['<some path>']` declared.

**Observe SessionStart event**: AGENT's first turn should reference
active invariants + recent ADRs (injected by `session_brief.py`).

### Step 3 — Trigger PreToolUse chain

Ask AGENT to Edit a file inside one of `affected_modules`.

**Expected hook fire (in order)**:
1. `invariant_guard.py` — silent unless invariant violation.
2. `analyze_halt_gate.py` — silent unless analyze BLOCK active.
3. `spec_first_guard.py` — silent (spec exists with evals).
4. `implement_snapshot_hook.py` — silent capture into
   `.agent-toolkit/.implement_snapshots/live-exercise/`.

**Verify** after Edit:
```bash
ls .agent-toolkit/.implement_snapshots/live-exercise/
cat .agent-toolkit/.implement_snapshots/live-exercise/_manifest.json
```

Should show file path captured. If missing → snapshot hook didn't
fire → Layer C failure.

### Step 4 — Trigger PostToolUse chain

AGENT continues with more Edits in feature scope.

**Expected hook fire (in order)** per Edit:
1. `probe_autostub.py` — may emit `[probe_autostub]` warn if no probe
   covers the file.
2. `tdd_runner.py` — may emit `[tdd-runner]` nudge.
3. `verification_loop.py` — may emit `[verification-loop]` nudge.
4. `verify_nudge.py` — may emit `[verify-nudge]`.
5. `auto_test_runner.py` — invokes MCP test if mapping matches.
6. `auto_run_probes.py` — invokes falsify if auto_run probe matches.
7. `daemon_manager.py` — restarts daemon if config present.

**Verify** state files updated:
```bash
ls -la .agent-toolkit/.tdd_runner_last.json
ls -la .agent-toolkit/.auto_test_state.json
ls -la .agent-toolkit/.auto_probes_state.json
```

Timestamps should reflect Edit time (within 30s).

### Step 5 — Trigger Stop chain (8 hooks)

Have AGENT emit a response claiming "Sprint hoàn tất. Implement done."
WITHOUT running an MCP probe call in same turn.

**Expected (after P1 reorder in v0.8.0)**:
1. `implement_orchestrator.py` fires FIRST — emits aggregated
   Phase 5.1-5.4 verdict via additionalContext.
2. `evidence_audit.py` then fires — likely **BLOCKs** because no MCP
   call.
3. Hooks #3-#8 skipped due to block.

**This is correct behavior**. AGENT receives:
- Orchestrator audit (informational).
- Evidence audit block (re-prompt with MCP call).

**If orchestrator output appears in AGENT's next response** → Layer
C verified. Phase 5.1-5.4 audit truly fires.

**If orchestrator output NOT received** → Layer C broken. Stop hook
ordering or block cascade has issue. Report to toolkit maintainer.

### Step 6 — Verify block cascade is correct

Have AGENT re-emit with `probe-skip: all live-exercise-no-mcp`
marker. Expected:
1. `implement_orchestrator.py` fires (idempotent — may use cache from
   step 5).
2. `evidence_audit.py` allows (probe-skip honored).
3. `verify_lint.py` allows (no Verify Report claim yet).
4. `post_edit_verify_gate.py` allows.
5. `debug_sentry.py` allows.
6. `spec_drift_advisory.py` allows.
7. `implement_notes_gate.py` may warn if `.implement-noted.md` missing.
8. `verify_lint_scope.py` may warn if files outside `affected_modules`.

### Step 7 — Trigger `/verify` + verify lint pass

Have AGENT emit `verify_report.md` with full coverage. Run `/verify`.

**Expected**:
- `verify_lint.py` returns 0 (all evals covered).
- P11 cleanup triggers: snapshot dir removed.

**Verify**:
```bash
ls .agent-toolkit/.implement_snapshots/live-exercise/  # should not exist
```

### Step 8 — Trigger emergency kill-switch

```bash
export AGENT_TOOLKIT_DISABLE=1
# (PowerShell: $env:AGENT_TOOLKIT_DISABLE = "1")
```

Have AGENT do any Edit. Expected: zero hook output (all 21 hooks
silent exit).

```bash
unset AGENT_TOOLKIT_DISABLE
```

Hooks back online.

### Step 9 — Check crash log

```bash
ls -la .agent-toolkit/.hook_crash_log.json
```

If any hook crashed during exercise (rare), this file exists with
ring buffer of last 50 crashes. Empty/missing = no crashes.

### Step 10 — Report findings

Write `specs/v0.8.0-master-fix.live-exercise-evidence.md` with:
- Date of exercise.
- Each step observation (PASS / FAIL).
- Any unexpected behavior.

Update spec `eval_status: defined` → `eval_status: verified` after
all 9 steps PASS.

---

## Common failure modes during exercise

| Failure | Likely cause | Fix |
|---|---|---|
| No hook stderr output anywhere | Cursor didn't reload settings.json | Fully quit Cursor (not just close window) and re-open |
| `[snapshot-hook] grandfather` warn appears | Spec has no `affected_modules` | Run `migrate_specs_affected_modules.py --apply` or add manually |
| auto_test_runner times out | MCP server hung | Reduce timeout in `.agent-toolkit/auto_test.json` or skip via `AGENT_TOOLKIT_DISABLE=1` |
| `[implement-orchestrator]` never appears in Stop | Either (a) impl-noted missing, (b) spec no affected_modules, (c) orchestrator subprocess error logged in `.hook_crash_log.json` | Inspect crash log; verify spec + impl-noted both present |
| daemon_manager refuses kill | P6 cmdline mismatch | `test_env.json: process_manager.start_cmd[0]` should match process binary basename |

---

## What this exercise validates

| Layer | Pre-exercise | Post-exercise (success) |
|---|---|---|
| A — Components isolated | OK (unit tests) | OK |
| B — Cross-component flow | OK (E2E test) | OK |
| **C — Live dispatcher fire** | `[assumption]` | **VERIFIED empirical** |
| D — Orchestrator | OK | OK (proven in real Stop) |
| E — Hook ordering | `[assumption]` | **VERIFIED empirical** |

**Result**: xuyên suốt 90% → **≥98%** after successful exercise.

---

## When to re-run

- Every minor version bump (v0.8.0 → v0.8.1 etc).
- After any change to `.claude/settings.json`.
- After Cursor / Claude Code update.
- Before declaring toolkit "production-ready" for new project.

Recommend: 30-minute quarterly exercise per active project.
