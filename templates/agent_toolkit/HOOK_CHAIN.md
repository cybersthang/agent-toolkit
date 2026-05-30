# Hook Chain Reference

Reference for the 21 hooks shipped by agent-toolkit. Use this to
understand:

1. Fire order per event.
2. Block semantics (which hooks can stop the chain).
3. Bypass markers for emergency exits.
4. Cross-hook dependencies + cascade risks.

Generated from `templates/claude/settings.json` (v0.8.0). For canonical
spec see `specs/v0.8.0-master-fix-design-review.md`.

---

## SessionStart (1 hook)

| Order | Hook | Block? | Purpose |
|---|---|---|---|
| 1 | `session_brief.py` | no | Inject active invariants + ADRs into first turn |

Timeout: 5s.

---

## UserPromptSubmit (1 hook)

| Order | Hook | Block? | Purpose |
|---|---|---|---|
| 1 | `intent_router.py` | no | Match prompt regex → suggest skills |

Timeout: 5s.

---

## PreToolUse — matcher `Edit|Write|MultiEdit|NotebookEdit` (4 hooks, sequential)

| Order | Hook | Block? | Block mechanism | Purpose |
|---|---|---|---|---|
| 1 | `invariant_guard.py` | **YES** | `permissionDecision: "deny"` | Block Edit stripping must_keep_regex |
| 2 | `analyze_halt_gate.py` | **YES** | `permissionDecision: "deny"` | Halt if `/analyze` returned BLOCK |
| 3 | `spec_first_guard.py` | no | warn stderr | Nudge spec before feature Edit |
| 4 | `implement_snapshot_hook.py` | no | silent capture | Snapshot pre-state for Layer 5 |

**Cascade**: if hook #1 or #2 denies → hooks #3, #4 skip. Snapshot NOT
taken for that Edit.

---

## PostToolUse — matcher `Edit|Write|MultiEdit|NotebookEdit` (7 hooks, sequential)

| Order | Hook | Block? | Timeout | Purpose |
|---|---|---|---|---|
| 1 | `probe_autostub.py` | no | 5s | Warn missing probe entry |
| 2 | `tdd_runner.py` | no | 35s | Nudge pytest after edit |
| 3 | `verification_loop.py` | no | 8s | Nudge MCP probes |
| 4 | `verify_nudge.py` | no | 5s | Nudge `/verify` for spec-tracked file |
| 5 | `auto_test_runner.py` | no | 150s `[P5]` | Invoke MCP test runner |
| 6 | `auto_run_probes.py` | no | 120s `[P5]` | Run falsify probes |
| 7 | `daemon_manager.py` | no | 90s | Kill+restart daemon on feature edit |

All non-blocking (warn or invoke). No cascade.

---

## Stop (8 hooks, sequential — P1 v0.8.0 reordered)

> **v0.27 cognitive-load cut**: the 3 completeness gates that previously
> hard-blocked by default (gap, scope, post-edit-verify) now WARN by
> default. Hard blockers reduced to 3 (evidence_audit + verify_lint +
> debug_sentry) so the model isn't paralyzed by stacked Stop hooks.
> DEV opts back into strict mode via `enforce_mode.strict.example.json`
> or `AGENT_TOOLKIT_STRICT=1`.

| Order | Hook | Block? (default) | Timeout | Purpose |
|---|---|---|---|---|
| 1 | `implement_orchestrator.py` | no | 30s | **Phase 5.1-5.4 audit chain** (moved to position 1 per P1 to fire before blocking hooks) |
| 2 | `evidence_audit.py` | **YES** | 8s | Block PASS/DONE without MCP backing — the only "claims without proof" gate |
| 3 | `verify_lint.py` | **YES** | 15s | Block if Verify Report missing eval coverage |
| 4 | `independent_review_gate.py` | warn (config) | 15s | v0.31: WARN-default. Block done-claim on a `verified` spec without a fresh-context independent review (strict→block). Jam-escape + 2-counter cap. |
| 5 | `post_edit_verify_gate.py` | warn (config) | 6s | v0.27: warn-by-default. Promote to block via `enforce_mode.json` |
| 6 | `debug_sentry.py` | **YES** | 8s | Block traceback without fix attempt |
| 7 | `spec_drift_advisory.py` | no | 5s | Warn probe recipe vs script drift |
| 8 | `implement_notes_gate.py` | no | 5s | Warn implement-noted missing |
| 9 | `verify_lint_scope.py` | warn (config) | 15s | Layer 5 file-level scope check (block via `scope_audit.json`) |
| — | `gap_completeness_gate.py` | warn (config) | 5s | v0.27: warn-by-default. Auto-downgrades if `scope-*` markers present (dedup with scope gate) |
| — | `scope_completeness_gate.py` | warn (config) | 5s | v0.27: warn-by-default. Silent when no manifest exists |
| — | `clarification_gate_enforcer.py` | **YES** (default) | 5s | Skips on autonomy active. Stays block in v0.27 — different category from "claim-done" gates; asking-before-acting is a healthy behavior, not paralysis. |

**Cascade post-P1**: orchestrator fires FIRST. Subsequent blocker
firing doesn't suppress audit output to AGENT.

**Pre-P1 cascade (v0.7.3 and earlier)**: evidence_audit blocked first
→ orchestrator never fired → silent Phase 5.1-5.4 skip.

---

## Bypass markers — full reference

Single-shot bypass tokens that AGENT (or DEV) places in response text:

| Marker | Tắt hook | Use case |
|---|---|---|
| `spec-first-guard: skip <reason>` | spec_first_guard | Hotfix without spec |
| `bypass-invariant: <id>` | invariant_guard | Override 1 invariant for 1 Edit |
| `debug-sentry: skip <reason>` | debug_sentry | Expected traceback (test demo) |
| `probe-skip: <id|all> <reason>` | evidence_audit | Probe N/A or DB down |
| `progress-skip: <category|all> <reason>` | progress-checks | Hallucinated-progress FP |
| `evidence-audit: skip <reason>` | evidence_audit | Honor-only |
| `verify-gate: skip <reason>` | post_edit_verify_gate | Done without /verify |
| `implement-notes: skip <reason>` | implement_notes_gate | No implement-noted needed |
| `orchestrator-skip: <reason>` | implement_orchestrator | Skip Phase 5.1-5.4 chain |
| `scope-creep-allowed: <file> <reason>` | verify_lint_scope | File outside affected_modules |
| `untagged-hunk-allowed: <reason>` | diff_annotation_validator | Hunk no tag needed |

**Universal kill-switch** (env var, not per-response):
- `AGENT_TOOLKIT_DISABLE=1` — every hook exits silent at top.

---

## Cross-hook dependencies

```
spec.md (DEV)
  ↑ read by
  ├── spec_first_guard         (PreToolUse #3)
  ├── implement_snapshot_hook  (PreToolUse #4 — needs affected_modules)
  ├── implement_notes_gate     (Stop #7)
  ├── implement_orchestrator   (Stop #1 — needs affected_modules)
  ├── verify_lint              (Stop #3 — acceptance_evals)
  ├── verify_lint_scope        (Stop #8 — affected_modules)
  ├── post_edit_verify_gate    (Stop #4 — status check)
  └── spec_drift_advisory      (Stop #6)

implement-noted.md (AGENT Phase 5.0)
  ↑ read by
  ├── implement_notes_gate
  ├── implement_orchestrator (via validator + detector)
  └── verify_lint_scope      (SD refs for bypass)

.implement_snapshots/<slug>/_manifest.json (snapshot_hook write)
  ↑ read by
  ├── missing_sd_detector
  ├── verify_lint_scope
  └── implement_orchestrator (via subprocess to detector)

acceptance-probes.json (DEV+toolkit)
  ↑ read by
  ├── auto_run_probes
  ├── probe_autostub
  ├── evidence_audit
  ├── falsify.py
  └── gap_status / gap_fix_cycle
```

---

## Cascade scenarios — known failure modes

| F# | Scenario | Impact | Mitigation in v0.8.0 |
|---|---|---|---|
| F1 | Stop hook #2 evidence_audit blocks → hooks #3-#8 skip | Phase 5.1-5.4 audit lost | P1 moves orchestrator to #1 |
| F2 | PreToolUse #1 invariant_guard denies → snapshot not taken | Layer 5 missing baseline for that Edit | Acceptable — invariant violation rare |
| F3 | Spec lacks affected_modules → snapshot hook silent skip | Entire Layer 5 dysfunctional | P2 emits warn instead of silent |
| F4 | implement-noted missing → orchestrator silent skip | Phase 5.1-5.4 never runs | implement_notes_gate warns separately |
| F5 | Multi-Stop iteration → orchestrator cache stale | Outdated verdict cached | P3 mtime invalidation |
| F6 | auto_test_runner 600s timeout → 10-min PostToolUse block | DEV waits | P5 reduces to 120s default |
| F7 | daemon_manager kills wrong PID | Production process killed | P6 cmdline match before kill |
| F8 | Hallucinated SD validates ok (file exists, not actually modified) | Honor-system gap | P4 cross-check against snapshot modified-list |
| F9 | Snapshot dir accumulates | Disk growth | P11 auto-cleanup post-verify |
| F11 | Orchestrator subprocess chain ~6s overhead | Slow Stop event | (deferred) P8 in-process import |
| F14 | Hook script Python crash silent | DEV blind to bugs | P9 crash wrapper logs to ring buffer |
| F15 | implement-noted schema drift across versions | Validator fails on old artifacts | P10 schema_version field |

See `specs/v0.8.0-master-fix-design-review.md` for full enumeration.

---

## DEV troubleshooting cheatsheet

| Symptom | Likely cause | Action |
|---|---|---|
| Edit blocked unexpectedly | invariant_guard or analyze_halt_gate | Read stderr; add `bypass-invariant: <id>` if intentional |
| Stop blocked "PASS/DONE detected" | evidence_audit | Add MCP probe call OR `probe-skip:` marker |
| "Phase 5.1-5.4 audit" never appears | orchestrator skipped (impl-noted missing OR spec no affected_modules) | Check `[implement-notes-gate]` warn / `[snapshot-hook] grandfather` warn |
| auto_test_runner times out | MCP server hung | Lower timeout in `.agent-toolkit/auto_test.json` OR kill MCP |
| daemon_manager refuses kill | PID safety mismatch (P6) | Check `test_env.json:process_manager.start_cmd` first token matches process basename |
| Hook crashes silent | P9 wrapper logged it | `cat .agent-toolkit/.hook_crash_log.json` |

---

## Emergency disable

To temporarily disable ALL 21 hooks:

```bash
export AGENT_TOOLKIT_DISABLE=1   # POSIX
$env:AGENT_TOOLKIT_DISABLE=1     # PowerShell
```

Each hook checks this env var at top of `main()` → silent exit 0.
