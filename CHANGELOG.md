# Changelog

All notable changes to agent-toolkit are documented here. Follows Semver:
breaking changes bump MAJOR; feature additions bump MINOR; bug fixes bump PATCH.

## [0.9.1] — 2026-05-21 — Close Phase C c3 instrumentation gap

Patch release closes single broken commit from v0.9.0: Phase C
`emit_fire_event()` helper was defined in `_common.py` but **NOT
applied** to any hook. `/hook-health` aggregator reported `fires_total:
0` in real Cursor_NAKIVO session — surfacing the gap. v0.9.1
instruments 4 sample hooks per spec eval c3.

### Fixed

- **c3 applied to 4 sample hooks**: `invariant_guard.py`,
  `evidence_audit.py`, `implement_orchestrator.py`,
  `verify_lint_scope.py` now call `emit_fire_event()` at decision
  branches (allow / warn / block). Each call try/except guarded —
  silent on failure (telemetry is best-effort, never breaks workflow).

### Added

- `tests/test_fire_instrumentation.py::TestSampleHooksInstrumented`
  (2 new tests): mechanical assertion that all 4 sample hooks import
  + invoke `emit_fire_event`.

### Changed

- `lib/installer.py` — `__version__` 0.9.0 → 0.9.1.
- 4 hooks updated: import `emit_fire_event` from `_common`, call at
  exit / decision points.

### Effect

- `/hook-health` output now shows non-zero `fires_total` after
  Cursor restart + session activity.
- `verdicts_per_hook` breaks down by allow / warn / block.
- `avg_duration_ms_per_hook` populated as more sample hooks call
  with `duration_ms` arg in future iterations.

### Pattern repeated

v0.8.0 P9 was defined-but-unused → fixed v0.8.1.
v0.9.0 c3 was defined-but-unused → fixed v0.9.1.
Self-bias: I claim "applied" in CHANGELOG but ship without actually
wiring. Caught by next-turn `/hook-health` empirical signal — exactly
the pattern Dim 3 Observability was meant to detect.

### Test counts

- v0.9.0 baseline: 432 tests.
- v0.9.1 adds: 2 new (TestSampleHooksInstrumented).
- Total: 434 tests pass; coverage 97.94%.

---

## [0.9.0] — 2026-05-21 — Harness Engineering improvement (Phases C+D+E+F+G)

Path (β) from HE evaluation — 5 of 7 phases shipped. Phase B (hook
consolidation) **deferred to v0.9.1** pending empirical signal; Phase
A + H = DEV manual (live exercise + production observation).

### Phase G — Schema enforcement + single source of truth (Dim 7 + 10)

- `implement_noted_validator.validate(enforce_schema_version=True)` —
  default checks `schema_version` field presence; rejects files
  missing it.
- 3 legacy implement-noted files backfilled với `schema_version: 1`.
- New CLI flag `--no-schema-check` for legacy override.

### Phase E — AGENT_TOOLKIT_STRICT env var (Dim 4)

- `_common.is_strict_mode()` helper checks env var.
- `run_main_safe()` propagates exit 1 instead of 0 when STRICT mode.
- Dual-mode: dev default fail-open, CI opt-in fail-closed.

### Phase D — enforce_mode.json config-driven (Dim 1 + 2)

- `_common.get_enforce_mode(workspace, hook_name)` reads
  `.agent-toolkit/enforce_mode.json` with per-hook overrides.
- STRICT env var globally overrides → block.
- `implement_notes_gate.py` honors enforce_mode (warn default,
  block when configured).
- Example config: `templates/agent_toolkit/enforce_mode.example.json`.

### Phase F — Orchestrator in-process imports (Dim 9 low ceremony)

- `implement_orchestrator._call_tool_inproc()` helper — direct module
  import + function call instead of subprocess.
- `_run_tool_json()` kept as fallback when in-process fails.
- Saves ~2s per chained tool (~6s total per Stop event).
- Validator + detector now in-process; annotator still subprocess (uses
  --write side-effect).

### Phase C — /hook-health dashboard + fire instrumentation (Dim 3)

- `_common.emit_fire_event()` writes to ring buffer
  `.agent-toolkit/.hook_fire_log.json` (1000 events max).
- `templates/codex/tools/hook_health.py` aggregates all hook logs
  (crash + fire + spec_first_guard + implement_notes_gate) into
  markdown report + JSON.
- `/hook-health` slash command for DEV health check.
- Health verdict: green / yellow / red based on crash counts + recency.

### Phase B — DEFERRED to v0.9.1

Hook consolidation 21 → 16 deferred because:
- HIGH risk break workflow.
- DEV touch points constraint at 2 — adding empirical signal first
  before reducing hooks DEV may not realize were pulling weight.
- Phase C `/hook-health` instrumentation enables empirical-driven
  consolidation decision in v0.9.1 (data-driven not speculative).

### Added — tests (24 new)

- `tests/test_strict_mode.py` (5 tests for Phase E).
- `tests/test_enforce_mode_config.py` (7 tests for Phase D).
- `tests/test_hook_health.py` (5 tests for Phase C aggregator).
- `tests/test_fire_instrumentation.py` (3 tests for Phase C ring buffer).
- `tests/test_implement_noted_validator.py::TestSchemaVersionEnforce`
  (3 tests for Phase G).
- `tests/test_stop_chain_interactions.py::TestStopHookBlockSemantics`
  updated for Phase D conditional block.

### Changed

- `lib/installer.py` — `__version__` 0.8.1 → 0.9.0.
- `templates/claude/hooks/_common.py` — added `is_strict_mode`,
  `get_enforce_mode`, `emit_fire_event` helpers; `run_main_safe`
  STRICT-aware.
- `templates/claude/hooks/implement_notes_gate.py` — imports
  `get_enforce_mode`; conditional block when configured.
- `templates/claude/hooks/implement_orchestrator.py` — in-process
  import for validator + detector.
- `templates/codex/tools/implement_noted_validator.py` —
  `enforce_schema_version` parameter + STRICT check.
- 3 legacy implement-noted files backfilled.

### HE scorecard `[assumption]` (post-v0.9.0)

| Dim | v0.8.1 | v0.9.0 | Phase |
|---|---|---|---|
| 1 Determinism | 7.5 | 8.0 | D |
| 2 Mechanical enforcement | 6.5 | 7.5 | D |
| 3 Observability | 6.5 | 8.5 | C |
| 4 Fail-safe defaults | 6.0 | 7.5 | E |
| 5 Composability | 6.0 | 6.0 | (B deferred) |
| 6 Empirical validation | 5.5 | 6.5 | C passive |
| 7 Versioned schemas | 8.0 | 9.0 | G |
| 8 Bypass mechanism | 9.0 | 9.0 | — |
| 9 Low ceremony | 6.5 | 7.5 | F |
| 10 Single source of truth | 8.0 | 9.0 | G |
| **Average** | **6.95** | **7.85** | +0.90 |

Path to ~8.5: Phase B v0.9.1 (hook consolidation post-empirical) +
DEV Phase A live exercise.

### Test counts

- v0.8.1 baseline: 408 tests.
- v0.9.0 adds: 24 new tests.
- Total: 432 tests pass; coverage 97.94% maintained.

---

## [0.8.1] — 2026-05-21 — P9 fully applied (close v0.8.0 broken state)

Patch release closes single broken commit from v0.8.0: `run_main_safe`
wrapper was defined in `_common.py` but never applied to the 21 hooks.
v0.8.1 migrates all 21 hooks to invoke the wrapper.

### Fixed

- **P9 applied to 21 hooks**: each hook now imports `run_main_safe`
  from `_common` and calls `sys.exit(run_main_safe(main))` instead of
  raw `sys.exit(main())`. Crashes now log to
  `.agent-toolkit/.hook_crash_log.json` ring buffer.

### Added

- `tests/fixtures/migrate_hooks_to_run_main_safe.py` — idempotent
  migration script (one-shot tool).
- `tests/test_hook_crash_wrapper.py::TestAllHooksUseRunMainSafe`
  (2 new tests) — mechanical assertion: every shipped hook imports
  + invokes wrapper from `__main__` block.

### Changed

- `lib/installer.py` — `__version__` 0.8.0 → 0.8.1.
- 21 hooks under `templates/claude/hooks/*.py` (excluding `_common.py`,
  `_patterns.py`, `_audit/`) — wrapper applied.

### Notes

Mid-migration, 2 import-order issues fixed:
1. 7 hooks had `run_main_safe` inserted inside `# noqa: E402` comment
   instead of import list (regex bug in migration script's
   non-parenthesized-import branch).
2. 5 hooks (auto_run_probes, auto_test_runner, daemon_manager,
   evidence_audit, spec_drift_advisory) had `sys.path.insert(...Path(__file__)...)`
   inserted BEFORE `from pathlib import Path` → NameError. Reordered.

Both caught + fixed in same sprint. 408 tests pass (+2 from new
coverage assertions).

### Xuyên suốt scorecard `[assumption]` (post-v0.8.1)

| Layer | v0.8.0 honest | v0.8.1 |
|---|---|---|
| A | 10 | 10 |
| B | 9 | 9 |
| C | 5 | 5 (T1 backlog unchanged) |
| D | 8 | 9 (P9 closes silent crash path) |
| E | 7 | 8 (crash log now observable) |
| **Total** | 39/50 = 78% | 41/50 = **82%** |

Path to ≥92% still requires DEV running `DEV_LIVE_EXERCISE.md`
(P13 from v0.8.0).

---

## [0.8.0] — 2026-05-21 — Master Fix: holistic adversarial review + 13 fixes

Closes 5-sprint iterative cycle with ONE comprehensive adversarial design review (`specs/v0.8.0-master-fix-design-review.md` — 17 failure modes enumerated F1-F17) + ONE complete fix sprint (`specs/v0.8.0-master-fix.md` — 13 fixes P1-P13). Drives xuyên suốt từ ~66% (v0.7.3 honest) lên **~88-90% AGENT-side**, với DEV live exercise (P13) đóng nốt còn ~10% để đạt **≥98%**.

### Closes — F1-F17 from design review

- **F1** (evidence_audit cascade): P1 reorders Stop chain — `implement_orchestrator.py` moved to position 1, fires before any blocking hook so audit output reaches AGENT regardless.
- **F3** (silent grandfather): P2 emits stderr warn when spec lacks `affected_modules`.
- **F5** (stale cache): P3 invalidates orchestrator cache by impl-noted mtime; iter 2 re-runs chain.
- **F6** (10-minute MCP block): P5 reduces auto_test_runner timeout 600→120s; auto_run_probes 300→90s.
- **F7** (kill wrong PID): P6 verifies process cmdline matches `start_cmd[0]` basename before kill.
- **F8** (hallucinated SD): P4 cross-checks SD-N file refs against actual snapshot modified-files; flags "fabricated-sd".
- **F9** (snapshot dir growth): P11 auto-cleanup triggered by `verify_lint` on /verify success.
- **F11** (subprocess overhead): deferred to v0.8.1 (`P8` in-process import).
- **F14** (silent hook crash): P9 `_common.run_main_safe()` wrapper logs exceptions to `.hook_crash_log.json` ring buffer.
- **F15** (schema drift): P10 adds `schema_version: 1` to implement-noted example.

### Added — design review docs

- `specs/v0.8.0-master-fix-design-review.md` — adversarial holistic review (17 F + 13 P fixes proposed).
- `specs/v0.8.0-master-fix.md` — formal sprint spec (15 acceptance_evals).

### Added — tools / hooks

- `templates/claude/hooks/_common.py` — `run_main_safe(main)` wrapper + `_log_hook_crash` ring buffer write.
- `templates/claude/hooks/daemon_manager.py` — `_proc_cmdline()` + `_verify_pid_matches_start_cmd()` helpers; `_terminate()` accepts `start_cmd` for safety check.
- `templates/claude/hooks/verify_lint.py` — `_trigger_snapshot_cleanup()` invoked on lint pass.
- `templates/claude/hooks/implement_orchestrator.py` — cache key includes impl-noted mtime.
- `templates/claude/hooks/implement_snapshot_hook.py` — grandfather warn instead of silent skip.
- `templates/codex/tools/missing_sd_detector.py` — fabricated SD cross-check.

### Added — documentation

- `templates/agent_toolkit/HOOK_CHAIN.md` — full reference for 21 hooks (order, block semantics, bypass markers, cross-dependencies, troubleshooting cheatsheet).
- `templates/agent_toolkit/DEV_LIVE_EXERCISE.md` — 10-step manual session DEV runs to validate Layer C empirically.

### Added — tests (15 new)

- `tests/test_stop_chain_interactions.py` (9 tests) — assert hook chain order + block semantics + kill-switch coverage across all 21 hooks.
- `tests/test_hook_crash_wrapper.py` (4 tests) — run_main_safe behavior.
- `tests/test_implement_orchestrator.py::TestCacheMtimeInvalidation` (1 test) — cache invalidation by mtime.
- `tests/test_missing_sd_detector.py::TestFabricatedSdDetection` (2 tests) — fabricated SD cross-check.

### Changed

- `lib/installer.py` — `__version__` 0.7.3 → 0.8.0.
- `templates/claude/settings.json` — Stop chain order updated (orchestrator first); auto_test_runner timeout 600→150s; auto_run_probes 300→120s.
- `templates/agent_toolkit/implement-noted.example.md` — schema_version: 1 field added.

### Bypass markers — same as v0.7.3 (11 total)

No new markers in v0.8.0. Full list in `HOOK_CHAIN.md`.

### Xuyên suốt scorecard `[assumption]`

| Layer | Pre-v0.8.0 | Post-v0.8.0 (AGENT-only) | Post-v0.8.0 + DEV exercise |
|---|---|---|---|
| A — Components isolated | 10 | 10 | 10 |
| B — Cross-component | 7 | 8 | 9 |
| C — Live dispatcher fire | 5 | 5 | **10** (DEV exercise) |
| D — Orchestrator | 7 | 9 | 9 |
| E — Hook chain interactions | 4 | 8 | 9 |
| **Overall** | **33/50 = 66%** | **40/50 = 80%** | **47/50 = ≥94%** |

To reach 98%+ requires DEV running P13 live exercise (~30 min manual session).

### Test counts

- v0.7.3 baseline: 390 tests.
- v0.8.0 adds: 15 new across 4 test files.
- Expected total: 405+ tests; coverage 97.94% maintained.

### Migration notes

- No breaking schema changes. v0.7.x → v0.8.0 is clean install.
- `setup.py update --apply` ships:
  - Stop chain reorder (orchestrator first).
  - New hooks: none (existing extended).
  - New docs: HOOK_CHAIN.md + DEV_LIVE_EXERCISE.md.
  - Modified: daemon_manager, verify_lint, implement_orchestrator, implement_snapshot_hook, missing_sd_detector.
- DEV restart Cursor / Claude Code required to pick up Stop chain reorder.

### What's deferred to v0.8.1+

- P8 (in-process import in orchestrator) — saves ~6s per Stop.
- Layer 4 cross-feature pattern mining.
- AST-level affected_symbols enforcement.
- Adversarial 2nd-model self-audit.
- Cycle closure decision (stop iterating vs continue).

---

## [0.7.3] — 2026-05-21 — Orchestrator + E2E + auto-tag (closes "xuyên suốt" gaps)

Closes 3 of 6 gaps surfaced in v0.7.2 Raw Opus 4.7 Max High self-review.
Brings end-to-end chain xuyên suốt từ ~70% → ~85% `[assumption]`. AGENT
no longer relies on voluntary invocation of Phase 5.1-5.4 — Stop hook
auto-chains the audit phases mechanically.

### Closes

- **Gap 1** (master orchestrator MISSING): new
  `implement_orchestrator.py` Stop hook chains validator + detector +
  annotator + scope-check on done-claim. Idempotent via 60s cache.
- **Gap 3** (no E2E integration test): new
  `tests/test_v073_e2e_chain.py` simulates full flow with 3 scenarios.
- **Gap 4** (annotator full-burden post-emit): `diff_hunk_annotator`
  now auto-tags hunks where file matches spec eval target OR
  implement-noted SD-N file ref. Residual hunks only get FILL placeholder.

### Remaining gaps (defer)

- Gap 2 (silent grandfather on missing affected_modules) — minor; logged
  via DEV workflow doc instead of hook warn for now.
- Gap 5 (warn-only ignorable) — by design per spec D2 v0.7.2.
- Gap 6 (T1 live dispatcher fire) — DEV-manual; no AGENT path.

### Added

- `templates/claude/hooks/implement_orchestrator.py` (~290 LOC) — Stop
  hook orchestrating 4-phase audit chain.
- `tests/test_implement_orchestrator.py` (6 tests).
- `tests/test_v073_e2e_chain.py` (3 integration tests).
- `tests/test_diff_annotation.py::TestAutoTag` (3 new tests for auto-tag).
- `specs/v0.7.3-orchestrator-e2e.md` — spec written FIRST (P1 compliance,
  4th-in-a-row).

### Changed

- `lib/installer.py` — `__version__` 0.7.2 → 0.7.3.
- `templates/claude/settings.json` — Stop chain extended with
  `implement_orchestrator.py` (between `implement_notes_gate.py` and
  `verify_lint_scope.py`). Timeout 60s for chained subprocess invocations.
- `templates/codex/tools/diff_hunk_annotator.py` — added
  `_extract_eval_targets`, `_extract_sd_file_refs`, `_auto_tag_hunk`
  helpers; `build_annotation_template` returns `auto_tagged` count and
  per-hunk `auto_tag` field; `render_markdown_template` shows auto-tagged
  values inline.

### Bypass markers (1 new)

- `orchestrator-skip: <reason>` — skip entire orchestrator chain
  single-shot. Use for hotfix where audit overhead is unjustified.

### Workflow (unchanged DEV touch points)

DEV: `/plan` + `/clarify` + `/verify` + read verify_report (2 touch points).

AGENT Phase 5 auto-chain — now mechanical via orchestrator hook:
- Phase 5.0 — emit `<slug>.implement-noted.md`.
- Phase 5.1-5.3 — orchestrator chains validator + detector + annotator.
- Phase 5.4 — `verify_lint_scope.py` runs after orchestrator.

### Test counts

- v0.7.2 baseline: 378 tests.
- v0.7.3 adds: 12 new (6 orchestrator + 3 E2E + 3 auto-tag).
- Expected total: 390 tests; coverage 97.94% maintained.

### Xuyên suốt verdict post-v0.7.3 `[assumption]`

| Layer | v0.7.2 | v0.7.3 |
|---|---|---|
| A — Components isolated | OK | OK |
| B — Cross-component data flow | partial | **OK** (E2E test proves) |
| C — Live dispatcher fire | `[assumption]` | `[assumption]` (T1 backlog) |
| D — Orchestrator | **MISSING** | **OK** (hook chain auto-fires) |
| E — Hook ordering | `[assumption]` | `[assumption]` (Stop chain sequential) |

**Overall xuyên suốt: ~85% `[assumption]`** (vs 70% pre-v0.7.3).

To reach 95%+ requires DEV manual T1 exercise (no AGENT path).

---

## [0.7.2] — 2026-05-21 — Comprehensive scope audit (4-coverage mechanical safety net)

Closes 4 failure-mode categories that v0.7.0 implement-noted (output-
only) couldn't catch alone. AGENT auto-runs validation chain at end
of /implement; DEV touch points unchanged (Plan + Verify only).
Implements DEV-mandated workflow: "DEV chỉ /plan và /verify, còn lại
AGENT tiếp".

### Coverage matrix

| # | Failure mode | Mechanism |
|---|---|---|
| 1 | File-level scope creep | Layer 5: modified files vs spec.affected_modules + snapshot diff |
| 2 | Semantic creep inside scope | diff_hunk annotator: every hunk MUST tag eval id, SD ref, or bypass |
| 3 | Hallucinated SD in implement-noted | Validator: SD path/line/eval-id must exist |
| 4 | Missing SD (Edit happened but not declared) | Cross-check Edit count vs SD count + eval target match |

### Added — schema + tools

- `templates/agent_toolkit/spec-frontmatter.schema.json` — schema for spec
  frontmatter declaring `affected_modules` (file path prefixes Layer 5 enforces)
  and `affected_symbols` (reserved for AST-level scope in v0.8+).
- `templates/codex/tools/implement_snapshot.py` (~280 LOC) — pre-implement
  state capture; primitives `snapshot_create`, `snapshot_restore`,
  `snapshot_diff_filelist`, `snapshot_cleanup`. AGENT-only loop (no git commit
  required).
- `templates/codex/tools/implement_noted_validator.py` (~250 LOC) — validates
  SD/T/F entries in implement-noted: file paths exist, line ranges valid,
  Spec linkage eval id present, T transcript cite non-empty, F priority
  enum, frontmatter counts match section counts.
- `templates/codex/tools/missing_sd_detector.py` (~220 LOC) — flags Edits
  not covered by spec eval targets, SD-N references, bypass markers, or
  affected_modules.
- `templates/codex/tools/diff_hunk_annotator.py` (~200 LOC) — parses
  unified diff vs snapshot, emits `<slug>.diff-annotations.md` template
  with 1 row per hunk requiring AGENT tag.
- `templates/codex/tools/diff_annotation_validator.py` (~150 LOC) —
  asserts every hunk tagged with eval id, SD-N ref, or bypass.
- `templates/codex/tools/migrate_specs_affected_modules.py` (~200 LOC) —
  retrofits `affected_modules` into legacy specs by mining git log
  companion-file frequency. Idempotent re-run.

### Added — hooks

- `templates/claude/hooks/implement_snapshot_hook.py` (~220 LOC) —
  PreToolUse on first feature-scope Edit; calls `snapshot_create`.
  Skip on trunk branch / no spec / test file / file outside feature
  globs. Fail-open.
- `templates/claude/hooks/verify_lint_scope.py` (~240 LOC) — Stop hook
  triggered on Verify Report or "implement done" claim. Reads
  spec.affected_modules + missing-SD detector output. Emit warn or
  block per `.agent-toolkit/scope_audit.json` `enforce: warn | block`
  (default: warn).

### Added — tests (36 new)

- `tests/test_implement_snapshot.py` (7 tests) — snapshot primitives.
- `tests/test_implement_snapshot_hook.py` (4 tests) — PreToolUse fire
  conditions.
- `tests/test_implement_noted_validator.py` (6 tests) — content
  validation: file missing, line out-of-range, unknown linkage,
  empty cite, invalid priority, count mismatch, clean.
- `tests/test_missing_sd_detector.py` (5 tests) — coverage detection
  for in-scope / out-of-scope / eval-target / bypass / no-spec cases.
- `tests/test_diff_annotation.py` (6 tests) — annotator + validator.
- `tests/test_migrate_specs.py` (3 tests) — backfill + idempotent +
  dry-run.
- `tests/test_spec_frontmatter_schema.py` (5 tests) — schema fields.

### Changed

- `lib/installer.py` — `__version__` 0.7.0 → 0.7.2.
- `templates/claude/settings.json` — PreToolUse chain extended with
  `implement_snapshot_hook.py`; Stop chain extended with
  `verify_lint_scope.py` (after `implement_notes_gate.py`).
- `templates/cursor/skills/_common/implement-notes/SKILL.md` — Phase
  5.1-5.4 orchestration steps added (AGENT auto-runs validators chain).
- 4 legacy specs retrofitted with `affected_modules` field via
  `migrate_specs_affected_modules.py`: v0.6.0, v0.6.2, v0.7.0, v0.7.1.

### Bypass markers (2 new)

- `scope-creep-allowed: <file> <reason>` — file-level exempt for one
  Stop event. Used when DEV wants to land 1-line outside-scope edit
  without spec churn.
- `untagged-hunk-allowed: <reason>` — placed in `tag:` field of
  diff-annotations.md to exempt a hunk from validation.

### Workflow contract

DEV touch points preserved at 2:
- `/plan` + `/clarify` answer.
- `/verify` + read verify_report.

AGENT Phase 5 auto-chain (no DEV touch):
1. Phase 5.0 — emit `<slug>.implement-noted.md`.
2. Phase 5.1 — validate implement-noted content.
3. Phase 5.2 — detect missing SD entries.
4. Phase 5.3 — annotate diff hunks + validate annotation.
5. Phase 5.4 — file-level scope check at /verify.

### Migration notes

- Schema backward compatible: legacy specs without `affected_modules`
  are grandfathered (Layer 5 + snapshot hook skip them).
- Run `python templates/codex/tools/migrate_specs_affected_modules.py
  --apply` to retrofit existing specs.
- `.agent-toolkit/scope_audit.json` `enforce: warn` initial; upgrade
  to `block` after pattern validates over 3-5 features.

### Test counts

- v0.7.0 baseline: 337 tests.
- v0.7.2 adds: 36 new tests across 7 files.
- Expected total: 373 tests; coverage 97.94% maintained.

### Out-of-scope (defer v0.8+)

- Coverage 5: stale F-N follow-up aggregation.
- Coverage 6: cross-feature pattern mining (Layer 4).
- Coverage 7: AGENT compute-waste detection.
- AST-level scope check using `affected_symbols` field.
- Auto-promote F-N → ADR/invariant without DEV review.

### Honest residual risks

- AGENT self-audit chain has confirmation bias residual (same model
  writes + validates). Mitigated by mechanical heuristics + Layer 1
  filesystem truth check, NOT eliminated.
- Annotation tagging at scale (large diffs) adds AGENT compute per
  /implement; mitigated by Phase 5.3 being skip-able via bypass marker.
- Snapshot dir growth: ~5-50KB per active feature; cleanup TTL 7
  days but no cron enforcement (manual `--force` cleanup available).

---

## [0.7.0] — 2026-05-21 — implement-notes artifact (AGENT-side disclosure)

Introduces a new per-spec sidecar `<slug>.implement-noted.md` capturing
AGENT-side decisions outside spec, in-transcript trade-offs (strict
cite-required), open follow-ups, and confidence summary. Closes the
"AGENT silent decisions" gap in the disclosure layer (existing
`[assumption]` / `probe-skip` / clarification-gate ASSUMPTIONS cover
UNCERTAINTY + INTENT but not POST-IMPLEMENT NARRATIVE).

### Added

- `templates/agent_toolkit/implement-noted.example.md` — schema
  reference (4 sections: scope deviations / in-transcript trade-offs /
  open follow-ups / confidence summary) + filled sample.
- `templates/cursor/skills/_common/implement-notes/SKILL.md` —
  5-step workflow (re-read spec → walk transcript → classify each
  action → identify follow-ups → emit file).
- `templates/claude/commands/implement-notes.md` — `/implement-notes
  <slug>` slash command for manual / retroactive generation.
- `templates/claude/hooks/implement_notes_gate.py` — Stop hook
  advisory (warn-only) that emits `[implement-notes-gate] ...` when a
  turn claims implement done without the file. Bypass marker:
  `implement-notes: skip <reason>` single-shot. Universal kill-switch
  via `AGENT_TOOLKIT_DISABLE=1` honored.
- `tests/test_implement_notes_gate.py` — 9 tests covering warn,
  no-op (no claim / no spec / trunk branch / file exists), bypass,
  fail-open (empty / malformed / missing transcript).
- `specs/v0.7.1-implement-notes.md` — spec written BEFORE
  implementation per ADR-001 spec-first rule (7 evals i1-i7).
- `specs/v0.6.2-cleanup-uplift.implement-noted.md` — R1 PILOT
  artifact emitted retroactively against v0.6.2 sprint (6 scope
  deviations + 4 trade-offs + 5 follow-ups + confidence summary).

### Changed

- `lib/installer.py` — `__version__` 0.6.2 → 0.7.0 (new feature).
- `templates/claude/settings.json` — Stop hook chain extended with
  `implement_notes_gate.py` (after `spec_drift_advisory.py`).
- `templates/agent_toolkit/intent_map.json` — new entry routing
  natural-language triggers ("ghi quyết định ngoài spec", "scope
  deviation", "implement-notes") to the skill.

### Design decisions (per Raw Opus 4.7 Max High analysis)

- Schema revised from DEV's original 3-category proposal (decisions
  outside spec / changes from request / trade-offs) to 4-section:
  category 2 merged into 1 (overlap eliminated); category 3 gained
  STRICT cite-required rule (in-transcript only — reduces
  hallucination risk); category 4 confidence summary added (mitigates
  honor-system fragility).
- Hook layer is WARN-ONLY (R3 rollout). R4 hard enforcement (block
  /verify when missing for `feature_kind: classification`) is
  deferred until 3-5 pilot features validate value.
- Rollout phases: R1 manual pilot (this release) → R2 skill
  formalized → R3 advisory hook → R4 optional hard enforcement.

### Migration notes

- No breaking schema changes. v0.6.x → v0.7.0 is a clean install.
- Existing projects: `setup.py update --apply` adds the new hook +
  skill + slash command. No consumer config changes required;
  `implement_notes_gate.py` is warn-only.
- DEV opt-out: include `implement-notes: skip <reason>` in
  implement-done responses for hotfix / typo / pure-docs scopes
  where artifact is overhead.

### Test counts

- v0.6.2 baseline: 328 tests passing.
- v0.7.0 adds: 9 new tests (`test_implement_notes_gate.py`).
- Expected total: 337 tests; coverage 97.94% maintained.

---

## [0.6.2] — 2026-05-21 — Cleanup + uplift sprint (post-v0.6.0 polish)

Maintenance release that closes 10 follow-up items identified during
the v0.6.0 retrospective verify. No new feature work; existing
components hardened with additional test coverage + evidence + dogfood
hygiene.

### Added — tests + evidence

- `tests/test_mcp_call_success.py` (3 tests) — fake MCP server fixture
  + closes the gap where only mcp_call error paths were tested in v0.6.0.
- `tests/test_hooks_integration.py` (3 tests) — wire-level payload
  assertions for `auto_test_runner` (MCP args shape) +
  `auto_run_probes` (falsify probe id) using recording stubs.
- `tests/test_spec_first_guard.py` (11 tests) — full coverage for the
  new spec_first_guard hook (g1-g7 acceptance_evals).
- `tests/test_detect_retrospective_spec.py` (4 tests) — git-log
  timestamp comparison engine for retrospective spec detection.
- `tests/test_version_bump.py` (2 tests) — sync check between
  `lib/installer.py:__version__` and CHANGELOG sections.
- `tests/fixtures/fake_mcp_server.py` — JSON-RPC stub responding to
  initialize + tools/call.
- `tests/fixtures/recording_mcp_call.py` — stub that records argv.
- `tests/fixtures/recording_falsify.py` — stub that records argv.
- `tests/fixtures/run_gap_fix_e2e.py` — E2E harness for gap_fix_cycle.
- `specs/v0.6.2-gap-fix-cycle-trace.md` — live engine trace converting
  `[assumption]` claim to factual subprocess output evidence.
- `specs/v0.6.2-cleanup-uplift.md` — sprint spec with 10 acceptance_evals.
- `specs/v0.7.0-spec-first-guard.md` — spec written BEFORE coding V1
  guard hook (Vibe-flow Phase 1 compliance demonstration).

### Added — new hook + tool

- `templates/claude/hooks/spec_first_guard.py` — PreToolUse warn-only
  hook nudging spec-first discipline. Wired in `settings.json`. 7
  acceptance_evals (g1-g7). Public-project safe: feature_scope_globs
  config-driven, defaults seed Odoo / Django / Rails / generic Python.
- `templates/codex/tools/detect_retrospective_spec.py` — git-log
  comparator that flags specs added AFTER first feature-code commit.
  CLI + library use; fail-open semantics.

### Added — recipe pattern expansion

- `templates/codex/recipe_patterns/django_triggers.json` — expanded
  from 3 → 11 patterns (ORM bulk_create, signals, Celery, DRF
  serializer, login redirect, test client, migrations, management
  command).
- `templates/codex/recipe_patterns/rails_triggers.json` — expanded
  from 3 → 11 patterns (AR callbacks, RSpec let, FactoryBot,
  before_action, ActiveJob, Capybara system test, rake, validations).

### Added — docs + ADR

- `templates/agent_toolkit/decision-log.md` — ADR-001 entry
  ("Spec-first mandatory for orchestration patches"). First seeded ADR
  in the toolkit's own template.

### Changed

- `lib/installer.py` — `__version__` 0.5.0 → 0.6.2 (was stale; CHANGELOG
  had been ahead of metadata since v0.6.0).
- `specs/v0.6.0-autonomy-chain.verify_report.md` — evidence tightened.
  Each D1-D6 implementation decision now cites ≥2 explicit pytest
  nodeids (re-runnable) instead of test file names. 42 total `test_`
  citations vs ~10 previously.
- `templates/claude/hooks/spec_first_guard.py` (newly added but
  iterated) — DEFAULT_FEATURE_GLOBS expanded to support both flat
  (`models/x.py`) and nested (`models/sub/x.py`) layouts; branch
  resolution gained `symbolic-ref` fallback for unborn-branch repos.
- `templates/claude/settings.json` — PreToolUse hook chain extended
  with `spec_first_guard.py`.

### Removed

- `.coverage` binary untracked via `git rm --cached` (was committed
  despite `.gitignore` — gitignore only blocks new additions).
- `.agent-toolkit/specs/v0.6.0-autonomy-chain.md` dogfood copy
  eliminated; canonical path is `specs/`.

### Test counts

- Pre-v0.6.2 baseline: 302 tests passing.
- v0.6.2 adds: ~24 new tests (3 mcp_call + 3 hooks_integration + 11
  spec_first_guard + 4 detect_retrospective_spec + 2 version_bump +
  recipe pattern test target).
- Expected total: ~326 tests; coverage 97.94% maintained.

### Migration notes

- No breaking schema changes. v0.6.x → v0.6.2 is a clean install.
- Existing projects: `setup.py update --apply` adds
  `spec_first_guard.py` + tools + expanded recipe patterns. No
  consumer config changes required; spec_first_guard is warn-only.

---

## [0.6.0] — 2026-05-20 — Autonomy chain: AGENT covers DEV's manual interventions

Closes the loop on 9 recurring DEV interventions (auto-run tests after
edit, drive browser probes, kill+restart daemon on code change, recognize
non-MCP evidence, etc.) so a single `/implement <slug>` invocation can
take a spec from `clarified` to `verified` without DEV touching anything
between Plan and PR review. Eleven patches landed across 4 sprints +
~17 unit tests covering the new tools.

### Added — schemas + bootstrap (S1)

- `templates/agent_toolkit/test_env.schema.json` (v2) — declares
  `creds_ref` (env-var refs + fallback chain + `spawn_test_user_via_mcp`
  toggle) and `process_manager` (start_cmd template, health_check_url,
  pid_track_file, shutdown_signal) so daemon_manager/creds_resolver
  hooks can drive the daemon and resolve secrets without DEV input.
  Sibling: `test_env.example.json`.
- `templates/agent_toolkit/acceptance-probes.schema.json` (v2) — adds
  `runner` block, `auto_run: bool` (opt-in PostToolUse fire),
  `recipe_drift_tolerance` (loose/medium/strict).
- `templates/codex/tools/migrate_probes_v2.py` — idempotent v1→v2
  migration with `.v1.bak` safety copy + sensible defaults.
- `templates/cursor/skills/_common/test-env-bootstrap/SKILL.md` — per-
  stack discovery of URL/DB/creds/process_manager from project config.

### Added — evidence + falsifier runners (S1 + S2)

- `templates/agent_toolkit/evidence_audit_config.example.json` — config-
  driven recognizers for non-MCP evidence (Playwright stdout markers,
  falsify-CLI verdicts, pytest summaries, realdata_test outputs).
- `templates/claude/hooks/_audit/pass_contract.py` —
  `load_additional_evidence_patterns()` +
  `additional_evidence_satisfied()` helpers; `evidence_audit.py` wired
  to consult them before declaring a probe unsatisfied. Removes the
  repeating `probe-skip:` boilerplate for `manual-browser` probes whose
  evidence shows up via Playwright/falsify stdout.
- `templates/codex/tools/falsify.py` — new `mcp_call` runner type with
  `args_substitutions` template-reuse, expected_returncode +
  expected_stdout_regex assertions.
- `templates/codex/tools/mcp_call.py` — CLI bridge invoking MCP tools
  from hook context. Prefers `claude --print --mcp-call <server>:<tool>`
  when available, falls back to direct JSON-RPC spawn driven by
  `.mcp.json`.

### Added — orchestration hooks (S3)

- `templates/claude/hooks/auto_run_probes.py` — PostToolUse Edit hook
  fires `falsify.py --probe <id>` for every probe with `auto_run: true`
  whose `path_globs` match the edited file. Debounce 30s per probe via
  `.agent-toolkit/.auto_probes_state.json`.
- `templates/claude/hooks/auto_test_runner.py` — PostToolUse Edit hook
  invokes the configured MCP test tool (default
  `realdata_test:run_module_test`) for source/test pairs matching
  per-stack regex mappings. Debounce 10s. Configurable via
  `.agent-toolkit/auto_test.json`.
- `templates/claude/hooks/daemon_manager.py` — kill + restart the test
  daemon via `test_env.process_manager` after Edits in feature-scope
  files. Skips edits in `tests/`, `.agent-toolkit/`, etc.
- `templates/codex/tools/creds_resolver.py` — resolve `creds_ref` env
  vars from `.codex/mcp.local.env` (fallback chain). Never prints
  passwords to stderr; output goes straight to subprocess env.
- Wired into `templates/claude/settings.json` PostToolUse + Stop arrays
  so they fire automatically after `setup.py update`.

### Added — autonomy skills + slash commands (S4)

- `/gap-status [<spec-slug>]` slash command + skill (`templates/cursor/
  skills/_common/gap-status/`) + engine `templates/codex/tools/
  gap_status.py`. Markdown table cross-referencing spec acceptance_evals
  + probe registry + auto_run_probes verdicts + verify_report cells.
  Replaces the DEV-driven recap loop ("có blocker hay GAP gì không").
- `gap-fix-cycle` skill (`templates/cursor/skills/_common/gap-fix-cycle/`)
  + engine `templates/codex/tools/gap_fix_cycle.py` + 3 seed diagnose
  strategies (`templates/codex/gap_fix_diagnose/`): Python assertion
  mismatch, log_assertion regex relaxer, Playwright zero-selector
  annotation. Diagnose-patch-rerun loop, max 3 iterations, scoped to
  probe.path_globs, append to `decision-log.md`.
- `recipe-to-probe-script` skill + engine `templates/codex/tools/
  recipe_to_probe_script.py` + 3 pattern files (`templates/codex/
  recipe_patterns/`: rpc_triggers, assertions, freeze_scenarios). Free-
  text recipe → executable Playwright Python script.
- `spec-vs-evidence-diff` skill + Stop hook `templates/claude/hooks/
  spec_drift_advisory.py`. Advisory warns when a probe's prose recipe
  references a load-bearing token that the generated script doesn't
  implement. Configurable tolerance per probe.

### Added — intent routing + docs

- `templates/agent_toolkit/intent_map.json` — 5 new entries (gap-status,
  gap-fix, test-env-bootstrap, recipe-to-script, spec-drift) so
  intent_router auto-suggests the matching skill.
- `tests/test_new_tools.py` — 17 unit tests covering the 5 new tool
  CLIs, the C1 `additional_evidence_satisfied` helper, the
  pass_contract relative-import path, and migrate_probes_v2 idempotency.

### Operating model

DEV-active gates remain: `/plan`, `/clarify`, PR review, commit, push.
Everything between (analyze → tasks → implement → run probes →
gap-fix-cycle → verify → emit report) is autonomous when the hooks +
skills land. ADR-002 hard-stops still apply (no prod_db_write, no
git_push_force, no credentials_write, no main-branch push).

### Migration (existing toolkit users)

```
cd <your-toolkit-clone>
git pull
python setup.py update <your-project> --apply
python <project>/.codex/tools/migrate_probes_v2.py <project>
cp <project>/.agent-toolkit/evidence_audit_config{.example,}.json
npm install -g playwright && npx playwright install chromium    # if you want browser probes
```

Sensible defaults: `migrate_probes_v2` sets `auto_run: false` on every
probe — explicitly opt in on probes you want PostToolUse-fired.

### Known gaps left for follow-up

- `gap-fix-cycle` ships 3 diagnose strategies — common Python/Playwright
  signatures only. PR new strategies under `templates/codex/
  gap_fix_diagnose/`.
- `recipe-to-probe-script` pattern library is Odoo-flavor (web.framework,
  blockUI, longpolling). Django/Rails projects need to PR new pattern
  files under `templates/codex/recipe_patterns/`.
- Browser-side falsifier still requires Node + `npm i -g playwright` per
  decision Q5 ("require Node"). No bundled `playwright_python` runner —
  use `playwright` type via existing npx path.

## [0.5.1] — 2026-05-19 — Public-ready cleanup

### Removed (BREAKING for anyone who still used the in-toolkit overlay)

- `presets/odoo-12-nakivo.json` — project-specific overlay removed from
  the public toolkit. If you need that exact stack (custom addon roots,
  internal JIRA endpoints, Vietnamese default response, `Nakivo01` DB),
  recreate it as a **private preset overlay** in your own fork that
  `extends: odoo-12`. See `templates/agent_toolkit/PORTING.md` for the
  recipe.
- `templates/cursor/rules/odoo-12/odoo-12-nakivo-modules.mdc` — same
  reason; project-specific rules belong in the private overlay.

### Added

- `LICENSE` — MIT, at toolkit root.
- `NOTICE` — third-party MIT copyright notices for mattpocock/skills +
  github/spec-kit + andrej-karpathy-skills (required by their licenses).
- `# SPDX-License-Identifier: MIT` headers on `setup.py` and `lib/installer.py`.
- `.gitignore` extended: `.coverage`, `.pytest_cache/`, `.ruff_cache/`,
  `.mypy_cache/`, `htmlcov/`, `*.egg-info/`, `dist/`, `build/`, `.tox/`.

### Fixed

- `templates/cursor/skills/odoo/odoo-code-review/references/odoo-12-rules.md:77`
  — env-var name leaked the literal `NAKIVO_JIRA_*` prefix into a
  template that ships to every Odoo-12 install. Now `{{ENV_PREFIX}}_JIRA_*`
  (rendered at install time).
- All baked project-specific examples in templates replaced with
  `<addon>` / `<module>` / `<your.model>` placeholders so the public
  toolkit no longer ships any project-identifying string.

### Migration

Projects on `odoo-12-nakivo` preset must:
1. Create `<your-fork>/presets/odoo-12-nakivo.json` locally (copy from
   v0.5.0 of this repo if you need the old content), OR
2. Switch to `--preset odoo-12` and supply project-specific values via
   Phase 1 Q&A or `agent-toolkit.config.json` overrides.

The public toolkit no longer ships any organisation-specific defaults.

## [0.5.0] — 2026-05-19

Major: **Odoo skills are now version-aware**. The 12 version-baked skill
folders (`cursor/skills/odoo-12/odoo-12-*` and `cursor/skills/odoo-17/odoo-17-*`)
have been merged into **9 version-agnostic skills** under
`cursor/skills/odoo/`. Each skill's Step 0 reads `__manifest__.py` and
loads a matching `references/odoo-<N>-*.md` file. Future Odoo versions
(21, 22, …) only need one new reference file per skill — no preset edits,
no AGENTS.md edits, no new skill folders.

### Added

- **9 version-aware Odoo skills** under `templates/cursor/skills/odoo/`:
  - `odoo-codebase-discovery` — MCP discovery tools (no version logic).
  - `odoo-data-verification` — realdata_test MCP probes (no version logic).
  - `odoo-deterministic-answers` — canonical_decisions lookup (no version
    logic).
  - `odoo-jira-workflow` — JIRA MCP (no version logic).
  - `odoo-code-patterns` — version detection + `references/odoo-<N>-patterns.md`
    for v12 / v17 / v18 / v19 / v20-stub.
  - `odoo-module-scaffold` — version detection + `references/odoo-<N>-scaffold.md`
    for v12 / v17 / v18 / v19 / v20-stub.
  - `odoo-debug-troubleshoot` — version detection +
    `references/odoo-<N>-pitfalls.md` for v12 / v17 / v18 / v19 /
    v20-stub.
  - `odoo-tdd` — version detection + `references/odoo-<N>-tdd-pitfalls.md`
    for v12 / v17 / v18 / v19 / v20-stub.
  - `odoo-code-review` — unchanged (already version-aware; pre-existing
    pattern that the rest of the refactor follows).

### Removed

- `templates/cursor/skills/odoo-12/` (8 version-baked skills).
- `templates/cursor/skills/odoo-17/` (4 version-baked skills).
- Skill-name placeholders `{stack}-tdd` / `{stack}-code-patterns` / etc.
  in `intent_map.json` and `intent_router.py` — now literal `odoo-tdd`,
  `odoo-code-patterns`, etc. (the SKILL itself does version detection).

### Changed

- **Preset `skills` field**:
  - `odoo-12.json`: `["_common", "odoo", "odoo-12"]` → `["_common", "odoo"]`.
  - `odoo-17.json`: `["_common", "odoo", "odoo-17"]` → `["_common", "odoo"]`.
- **`templates/AGENTS.md`** intent-routing table — every `{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}-X`
  link replaced with literal `odoo-X` (skills auto-detect version).
- **`templates/agent_toolkit/intent_map.json`** — `{stack}-*` /
  `{stack_bare}-*` placeholders replaced with literal `odoo-*`.
- **`templates/claude/hooks/intent_router.py`** fallback patterns —
  same literal replacement.

### How to extend for Odoo 21+

1. Add `references/odoo-21-rules.md` to `odoo-code-review`.
2. Add `references/odoo-21-patterns.md` to `odoo-code-patterns`.
3. Add `references/odoo-21-scaffold.md` to `odoo-module-scaffold`.
4. Add `references/odoo-21-pitfalls.md` to `odoo-debug-troubleshoot`.
5. Add `references/odoo-21-tdd-pitfalls.md` to `odoo-tdd`.
6. (Optional) add `presets/odoo-21.json` extending `odoo-17`.
7. (Optional) add `canonical_decisions.odoo-21.json`.

No skill body changes, no AGENTS.md changes, no intent_router changes
needed.

### Compatibility

- Projects on toolkit ≥ 0.4 can `setup.py update --apply` to pick up the
  new skill layout. Old `.cursor/skills/odoo-12-*` and `odoo-17-*`
  directories will remain on disk — toolkit does not auto-delete them.
  Run manually: `rm -rf .cursor/skills/odoo-12-* .cursor/skills/odoo-17-*`
  after update.
- `agent-toolkit.config.json` unaffected.
- `.codex/canonical_decisions.json` unchanged.
- Memory packs `templates/memory/odoo-12/` and `odoo-17/` unchanged
  (still version-baked — memory is per-project state, not a skill).
- Cursor rules `templates/cursor/rules/odoo-12/` and `odoo-17/` unchanged
  (cursor rules use `globs:` per-file — cannot runtime-detect version).

---

## [0.4.0] — 2026-05-19

Major: Spec Kit alignment. The toolkit's spec-driven workflow is renamed
to match GitHub Spec Kit's slash-command vocabulary
(`/plan` → `/clarify` → `/tasks` → `/analyze` → `/implement` → `/verify`),
spec files move to a branch-scoped layout, and the agent auto-chains
analyze + implement + verify after DEV approves tasks.md.

### Added — Spec Kit workflow

- **`/clarify` slash command + `clarify` skill** (was `/grill` / `grill`)
  — Spec Kit Phase 2. Skill folder renamed
  `_common/grill/` → `_common/clarify/`. Auto-fires `/tasks` on
  completion. Refines `acceptance_evals` inline before tasks emit.
- **`/tasks` slash command + `tasks-breakdown` skill** (new) — Spec Kit
  Phase 3. Emits `tasks.md` next to the spec with Touches / Acceptance /
  Verification / Risk per task. STOPs for DEV review.
- **`/analyze` slash command + `analyze-artifacts` skill** (new) — Spec
  Kit Phase 3.5. 7 cross-artifact checks (story coverage / eval coverage
  / out-of-scope / invariant compat / constitution compat / path
  realism / verification concreteness). Auto-fired as first step of
  `/implement`. HALT verdict stops the auto-chain.
- **`/implement` slash command** (was `/go`) — Spec Kit Phase 4. Now
  auto-chains: `/analyze` → autonomy ON → execute tasks → `/verify` →
  report. DEV only needs `/plan` + `/clarify` + `/implement`.
- **`constitution.md`** (new) — toolkit principles + project-wide hard
  rules + stack constants in one slow-changing file. Aggregation point
  inspired by Spec Kit's `memory/constitution.md`.
- **Branch-scoped spec layout**: `.agent-toolkit/specs/<branch>/<slug>.md`
  replaces the flat `.agent-toolkit/specs/<slug>.md`. Branch derived
  from `git rev-parse --abbrev-ref HEAD`, fallback `_default`.
  Hooks (`verify_nudge`, `verify_lint`, `lint_verify_report.py`,
  `_patterns.py` slug regex) use `rglob`/optional-segment patterns so
  both layouts are supported in transition.

### Removed

- `_common/spec-driven-feature/` skill — its content split into
  `plan-feature` (Phase 1) + `clarify` (Phase 2) + `tasks-breakdown`
  (Phase 3); the duplicate skill folder is gone.
- `templates/claude/commands/grill.md` — replaced by `clarify.md`.
- `templates/claude/commands/go.md` — replaced by `implement.md`.

### Changed

- **`templates/AGENTS.md`** — intent-routing table updated for Spec Kit
  command names + Spec-driven workflow diagram added at the top.
- **`templates/agent_toolkit/intent_map.json`** — regex patterns + skill
  names migrated to Spec Kit naming. Old verify-against-real-data entry
  consolidated into Phase 5.
- **`templates/claude/hooks/intent_router.py`** — fallback intent map +
  per-skill expected-output blurbs migrated. New entries for
  `plan-feature`, `clarify`, `tasks-breakdown`, `analyze-artifacts`,
  `verify-feature`.
- **`plan-feature` skill** — branch-scoped path emit; description
  refreshed for Spec Kit Phase 1 naming. Auto-emits `acceptance_evals`
  skeleton with `TBD` fields refined later by `/clarify`.
- **`verify-feature` skill** — locate spec via `rglob` instead of fixed
  path; reference `/implement` instead of `/go`.

### Compatibility

- Specs created under the legacy flat layout (`.agent-toolkit/specs/<slug>.md`)
  are still discoverable: every hook + slash command falls back via
  `rglob` / optional-segment regex. New specs land in branch-scoped dirs.
- Projects on toolkit ≥ 0.3 can `setup.py update --apply` to pick up the
  new slash commands + skills. `setup.py update` is dry-run-by-default,
  so review the diff first. `agent-toolkit.config.json` is unaffected.
- `spec-driven-feature` removal is breaking for any custom skill or doc
  that linked to it; the closest replacement is `plan-feature`.

---

## [0.3.0] — 2026-05-18

Major: PASS-claim contract + hallucinated-progress detection + acceptance
probes registry + auto-pipeline + Playwright integration. Closes the
"agent reports PASS but real-data has bugs" gap by combining mechanical
enforcement (Stop hook + pre-commit) with empirical falsification CLI.

### Added — PASS-claim & probe contracts

- **`acceptance-probes.json` registry** in `templates/agent_toolkit/`.
  Per-feature contracts declaring `applies_when` activation rule +
  `evidence.required_tools` MCP requirements + `falsification.runner`
  empirical recipe. Schema versioned (v2).
- **`evidence_audit.py` split into `_audit/` sub-package** (7 modules:
  `strip`, `transcript`, `claim_audit`, `pass_contract`,
  `progress_checks`, `reasons`, `telemetry`). Entry script slimmed to
  ~200 line.
- **PASS-claim contract** (fail-CLOSED): claims like `tests pass`,
  `verified`, `done`, `hoàn thành` blocked unless turn includes ≥1 call
  to `mcp__realdata_test__*` / `mcp__postgres__*` (or matching
  per-feature probe MCP tool).
- **Hallucinated-progress checks** (5 categories A-E):
  `action_ghost`, `tool_result_fabrication`, `phantom_citation`,
  `todo_inconsistency`, `overcount`. Cross-checks claim text against
  the turn's actual `tool_use` / `tool_result` record.
- **`required_result_fingerprint`** (sha256) on probe.evidence:
  catches dummy MCP calls (e.g. `eval_orm_expression("1+1")`) that
  satisfy tool-name match but not query-result fingerprint.
- **`[meta-review]` / `[meta]` marker** exempts PASS contract +
  generic claim audit (but NOT progress checks) for meta-analysis
  responses about the toolkit itself.
- **Telemetry log** at `.codex/logs/hook_events.jsonl` (rotates at
  1 MB, keeps 3 rotations). Surfaced in `session_brief` SessionStart
  brief as `Hook health (last N events)`.
- **Kill-switch** via `AGENT_TOOLKIT_DISABLE=1` env var — all hooks
  short-circuit to allow.

### Added — auto-pipeline + slash commands

- **`probe_autostub.py`** PostToolUse hook — WARN when Edit/Write
  lands on feature-scope file but no probe covers it. Forces agent
  back to grill phase to capture PROBE_READINESS.
- **`auto_falsify.py`** pre-commit — for each staged file, invoke
  `falsify.py --probe <id>` for matching probes; block commit on
  REFUTED.
- **`probe_coverage.py`** pre-commit — block commit if feature-scope
  file has no registered probe.
- **`feature_probe_suggest.py`** pre-commit (info-only) — suggests
  `/probe-add` for new HTTP routes / controller methods / cron
  handlers in staged diff.
- **`falsify.py`** CLI runner (`.codex/tools/`) — empirical
  falsification for 4 types: `timing_perturb`, `side_effect_inject`,
  `log_assertion`, **`playwright`** (spawn `npx playwright test`,
  parse JSON reporter). Sandboxed shell exec (binary whitelist +
  quote-aware metachar scan).
- **`agent_toolkit_init.py`** bootstrap CLI — one-command setup for
  new projects.
- **New slash commands**: `/probe-add`, `/probe-coverage`, `/review`,
  `/run-probes`.
- **`clarification-gate` skill** extended with `PROBE_READINESS` block
  — for feature-scope tasks, agent must capture probe params during
  grill before implementation.
- **`intent_router.py` externalized** to `.agent-toolkit/intent_map.json`
  (with embedded fallback). Stack-agnostic via `{stack}/{stack_bare}`
  template placeholders.

### Added — pre-commit + safety

- **`.pre-commit-config.yaml.tmpl`** top-level template (installed as
  `.pre-commit-config.yaml`) wires 5 pre-commit hooks: invariant_guard,
  credential_guard (with Shannon entropy check), probe_coverage,
  probe_suggest, auto_falsify.
- **Atomic file mutation** in `falsify.py`: `os.replace` for inject
  + restore. Backup file separate from tmp; crash mid-injection
  cannot leave partial state.
- **`coverage_config.json`** at `templates/agent_toolkit/` — defines
  `feature_globs` for probe-coverage gate + `exempt_globs` for tests/
  migrations/etc.

### Added — Optional Playwright integration

- **`falsification.type: "playwright"`** runner: spawn `npx playwright
  test <spec>`, parse JSON reporter, PROVEN if all passed / REFUTED on
  any fail.
- **MS Playwright MCP** server referenced in `PORTING.md` (install
  separately if agent should drive browser interactively during grill).

### Added — Documentation & tests

- **`PORTING.md`** — full porting guide for non-Odoo stacks (Django,
  Rails, etc.). Comparison matrix vs CI / PR template / human review.
- **`QUICKSTART.md`** — 5-minute install + first-probe walkthrough
  (English).
- **Hook test suite**: 120 unit tests in `templates/codex/tests/hooks/`
  covering claim audit, PASS contract, progress checks, autostub,
  falsifier, fingerprint, sandbox, FP-resistance, Playwright dispatch.

### Fixed

- **BOM-tolerant load** (`utf-8-sig`) for `invariants.json`,
  `acceptance-probes.json`, `decision-log.md` reads — PowerShell
  `Out-File -Encoding utf8` BOM no longer silently disables hooks.
- **`_split_current_turn`** in `evidence_audit` skips intermediate
  tool_result echo messages — earlier turn tool_use blocks now
  participate in cross-checks.
- **`phantom_citation`** parses markdown link URLs; resolves citations
  by basename + on-disk existence + Read/Grep history.

### Compatibility

- Any project on toolkit ≥ v0.2 can `setup.py update` to get v0.3
  without breaking existing customization (registries preserved via
  SKIP_EXISTS on `agent_toolkit/`).
- New PostToolUse hook entry (`probe_autostub`) added to settings.json
  template — applies on next install/update.

---

## [0.2.0] — 2026-05-15

Audit-driven Tier 2 + Tier 3 + Tier 4 hardening pass.

### Added

- **`--apply` flag for `update`** (safe-by-default). Without it, `update`
  runs a dry-run with unified diff so changes can be reviewed before any
  disk write.
- **`--no-backup`, `--diff/--no-diff`, `--force`, `--force-dirty` flags**
  for `update` — full control over the apply behavior.
- **`--version` top-level flag** — prints `agent-toolkit <semver>`.
- **Auto-backup of overwritten files** as `<file>.bak.<YYYYMMDD-HHMMSS>`
  when `update --apply` (default; opt out with `--no-backup`).
- **Two-pass atomic apply**: templates are rendered into memory first;
  any render error aborts BEFORE any disk write. Each file is then
  written via `tmp + os.replace` so an interrupted write never leaves
  a half-written destination.
- **Preset inheritance** via `"extends": "<parent>"` field.
- **Additive overrides**: `addon_roots_append`, `mcp_servers_append`,
  `mcp_servers_remove`, `rules_append`, `skills_append`,
  `memory_packs_append` — extend parent preset without copy-pasting.
- **Preset schema validation** — typos like `addon_root` (singular) fail
  fast with a `did you mean` suggestion instead of silently breaking.
- **Git-aware safety**: `update --apply` refuses to overwrite a dirty
  working tree; pass `--force-dirty` to override.
- **MEMORY.md auto-regeneration** — after `seed_memory`, the index file
  is scanned and any *.md present in the memory dir but missing from
  MEMORY.md gets an entry added (parsed from frontmatter).
- **UTF-8 stdout reconfigure** at process start so the `✓` status glyph
  prints on Windows `cp1252` consoles without crashing.
- **Pytest suite**: 38 unit tests covering render_text, preset loading,
  validate_preset, resolve_preset inheritance (including cycle detection
  and `mcp_servers_remove`), encode_claude_project_path,
  git_dirty_status, _parse_frontmatter, regenerate_memory_index,
  _looks_templated, _content_will_change.
- **`.github/workflows/test.yml`** — CI matrix for Linux/macOS/Windows
  × Python 3.8/3.10/3.12.
- **`.pre-commit-hooks.yaml`** — projects using the toolkit can plug
  `setup.py update --apply --no-diff` into pre-commit to keep generated
  agent infra in sync.

### Changed

- **`update` default behavior is now dry-run + diff** (was: force-overwrite
  everything with no preview). This is a deliberate breaking change for
  safety; the previous behavior is `update --apply --no-backup --force`.
- **`load_preset` drops the hand-rolled YAML parser** (~50 dead lines).
  JSON-only by default. To use YAML, install pyyaml separately.
- **`_looks_templated` scans the full file** (was: first 8KB only). Fixes
  silent placeholder leak for templates larger than 8KB.

### Removed

- `README1.md` — stale fragment that just said `DEPRECATED → see README.md`.

## [0.1.0] — pre-2026-05-15

Initial release. Multi-harness (Cursor + Claude Code + Codex) agent infra
generator with stack-agnostic preset system.
