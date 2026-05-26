---
title: Agent-Toolkit Hook Fail-Mode Reference
version: 0.22
audience: agent-toolkit operators
last_updated: 2026-05-26
---

# Hook Fail-Mode Reference

27 hook scripts in `templates/claude/hooks/*.py` (excluding shared `_common.py`
and `_patterns.py` library modules). This document records the fail-mode
policy for each — what the hook does in the happy path, what it does when
its own Python code crashes, whether it honors the global kill-switch, and
which JSON config file (if any) tunes its behavior.

> **Note**: Earlier task framing referenced "29 hooks". The actual count of
> hook scripts wired into `templates/claude/settings.json` is **27**; the
> two excluded files (`_common.py`, `_patterns.py`) are shared libraries,
> not hooks themselves.

## Default crash policy (v0.21+)

Every hook wraps `main()` via `run_main_safe()` defined in
`templates/claude/hooks/_common.py:429`. That wrapper catches any uncaught
exception, logs it to `.agent-toolkit/.hook_crash_log.json`, emits a fire
event tagged `crash`, then exits according to the crash-policy gate
(`is_fail_closed_mode()`, `_common.py:303`):

- **Default**: fail-CLOSED — `exit 1`. Hook crash blocks the response (or
  for PreToolUse, blocks the tool call). The conservative posture: if the
  guard itself broke, don't silently let the action through.
- **Override**: set `AGENT_TOOLKIT_NO_STRICT=1` to revert to legacy
  fail-open (`exit 0`). Useful when iterating on a buggy hook locally.

This crash policy is **independent** of per-hook `enforce_mode.json`. The
latter controls what the hook does in the *happy path* when it detects a
violation (`warn` vs `block` vs `off`); the former controls only what
happens when the hook's own Python raises.

## Universal kill-switch

Every hook checks `AGENT_TOOLKIT_DISABLE=1` at the top of `main()` and
exits early with a permissive verdict (allow / silent / banner). This is
the emergency override when the toolkit itself is misbehaving — DEV sets
the env var, all enforcement falls silent until unset. `session_brief.py`
still fires (and only that) to surface a loud banner reminding DEV the
toolkit is off.

Verified by `grep AGENT_TOOLKIT_DISABLE` across `templates/claude/hooks/`:
**all 27 hooks honor the kill-switch.**

## Per-hook table

| Hook | Event | Normal | Fail mode (crash) | Kill-switch | Config file |
|------|-------|--------|-------------------|-------------|-------------|
| `session_brief.py` | SessionStart | inject brief (invariants + ADRs + autonomy + kill-switch banner) | fail-closed (exit 1) | yes | `invariants.json`, `decision-log.md` |
| `intent_router.py` | UserPromptSubmit | inject skill suggestions + reminders | fail-closed (exit 1) | yes | `intent_map.json` |
| `invariant_guard.py` | PreToolUse(Edit/Write/MultiEdit/NotebookEdit) | deny if `must_keep_regex` stripped (blocker) / warn / allow | fail-closed (exit 1) | yes | `invariants.json` |
| `analyze_halt_gate.py` | PreToolUse(Edit/Write/MultiEdit/NotebookEdit) | block edit on source files when any `analyze-report.md` has HALT verdict | fail-closed (exit 1) | yes | none (reads `.agent-toolkit/specs/**/analyze-report.md`) |
| `spec_first_guard.py` | PreToolUse(Edit/Write/MultiEdit/NotebookEdit) | warn-only on feature-scope edits without spec | fail-closed (exit 1) | yes | `coverage_config.json` |
| `reuse_probe.py` | PreToolUse(Edit/Write/MultiEdit/NotebookEdit) | soft-warn when new `def`/`class` collides with existing symbols | fail-closed (exit 1) | yes | `reuse_probe.json` |
| `implement_snapshot_hook.py` | PreToolUse(Edit/Write/MultiEdit/NotebookEdit) | snapshot file once per slug (silent on subsequent edits) | fail-closed (exit 1) | yes | `coverage_config.json` |
| `git_guardrails.py` | PreToolUse(Bash) | deny destructive git ops (commit/push/add/reset --hard/etc.); allow on bypass token | fail-closed (exit 1) | yes | `enforce_mode.json` (per_hook), `.skip_git_guard_next.json` |
| `probe_autostub.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | silent OK if probe exists, else stern warn (no auto-stub) | fail-closed (exit 1) | yes | `acceptance-probes.json`, `coverage_config.json` |
| `tdd_runner.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | nudge pytest on source/test edits (mode `nudge` or `run`) | fail-closed (exit 1) | yes | `tdd.json` |
| `verification_loop.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | nudge `python_syntax_check` + `python_import_check` + `xml_validate` MCPs | fail-closed (exit 1) | yes | `verification.json` |
| `verify_nudge.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | nudge `/verify <slug>` when edit touches spec-tracked file (60s TTL) | fail-closed (exit 1) | yes | none (uses `.verify_nudge_last.json`, `.verify_nudge_cache.json` state) |
| `auto_test_runner.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | mechanical test run via MCP `realdata_test` (fails open per docstring) | fail-closed (exit 1) | yes | `auto_test.json` |
| `auto_run_probes.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | run acceptance probes matching edited path (debounced) | fail-closed (exit 1) | yes | `auto_probes.json` |
| `daemon_manager.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | kill+restart configured test daemon on feature-scope edit | fail-closed (exit 1) | yes | `test_env.json`, `coverage_config.json` |
| `loc_delta_tracker.py` | PostToolUse(Edit/Write/MultiEdit/NotebookEdit) | track LOC delta per turn, soft warn on overflow | fail-closed (exit 1) | yes | `loc_budget.json` |
| `implement_orchestrator.py` | Stop | run Phase 5.1-5.4 audit chain (cached 60s); emit aggregated context | fail-closed (exit 1) | yes | none (uses `.orchestrator_state.json` cache) |
| `evidence_audit.py` | Stop | block stop on PASS-claim without probes / hallucinated-progress / unbacked claims | fail-closed (exit 1) | yes | `evidence_audit_config.json` (in `_audit/`) |
| `clarification_gate_enforcer.py` | Stop | block when intent_router suggested clarification-gate but response lacks 4 markers (default `block`) | fail-closed (exit 1) | yes | `enforce_mode.json` (per_hook); state in `.last_intent_suggested.json`, `.skip_clarification_next.json`, `.autonomy_active.json` |
| `gap_completeness_gate.py` | Stop | block done-claim while `.open_gaps.json` has open entries; bypass markers per-gap or whole-gate | fail-closed (exit 1) | yes | `enforce_mode.json` (per_hook); state in `.open_gaps.json`, `.autonomy_active.json` |
| `verify_lint.py` | Stop | block on Verify Report missing required sections / acceptance_eval coverage (delegates to `.codex/lint_verify_report.py`) | fail-closed (exit 1) | yes | none (delegates to lint script) |
| `post_edit_verify_gate.py` | Stop | block "done" claim after Edit on spec-tracked file without `/verify` run in same turn | fail-closed (exit 1) | yes | none |
| `debug_sentry.py` | Stop | block stop on traceback/exception in tool output without fix attempt; warn-only if `block_on_match=false` | fail-closed (exit 1) | yes | `debug.json` |
| `spec_drift_advisory.py` | Stop | warn-only when recipe-vs-script drift detected across acceptance probes | fail-closed (exit 1) | yes | `recipe_drift.json`, `acceptance-probes.json` |
| `implement_notes_gate.py` | Stop | warn-only on done-claim without `<slug>.implement-noted.{md,html}` sidecar (default `warn`; promote to `block` via config) | fail-closed (exit 1) | yes | `implement_notes.json` |
| `complexity_sentinel.py` | Stop | warn-only AST scan for loop-nest / func-LOC / branch-count overflow on `.py` edits | fail-closed (exit 1) | yes | `complexity_budget.json` |
| `verify_lint_scope.py` | Stop | Layer 5 scope-creep audit: warn / block files outside `affected_modules` (default `warn`) | fail-closed (exit 1) | yes | `scope_audit.json` |

## Reading the table

- **Event**: Claude Code hook event name from `templates/claude/settings.json`.
  Matcher (e.g. `Edit|Write|MultiEdit|NotebookEdit`, `Bash`) shown when not
  obvious.
- **Normal**: behavior when no Python exception is raised. Vocabulary:
  - `allow` / `silent` — exit 0 with no surface output.
  - `inject context` — emit `additionalContext` for the next turn (no block).
  - `nudge` — emit a reminder string but never block.
  - `warn` — stderr message + soft surface; the agent sees the warning but
    the tool/stop proceeds.
  - `deny` / `block` — explicit block (`permissionDecision: "deny"` for
    PreToolUse, `decision: "block"` for Stop, or `exit 2`).
- **Fail mode (crash)**: behavior when an uncaught Python exception bubbles
  out of `main()`. Per `run_main_safe()` v0.21+, fail-CLOSED (exit 1) is
  the default for all hooks. `AGENT_TOOLKIT_NO_STRICT=1` reverts globally
  to legacy fail-open (exit 0).
- **Kill-switch**: whether the hook honors `AGENT_TOOLKIT_DISABLE=1`
  (verified `yes` for all 27 hooks via grep).
- **Config file**: JSON file under `.agent-toolkit/` the hook reads to
  tune its behavior. State / ring-buffer files (e.g. `.hook_loc_log.json`)
  are noted where load-bearing for the operator.

## Per-hook enforce-mode override

Beyond the crash-policy global switch, individual hooks consult
`get_enforce_mode(workspace, hook_name)` (`_common.py:327`) which reads
`.agent-toolkit/enforce_mode.json`:

```json
{
  "default": "warn",
  "per_hook": {
    "clarification_gate_enforcer": "warn",
    "gap_completeness_gate": "off",
    "git_guardrails": "block"
  }
}
```

Valid modes:
- `block` — hook escalates findings to a hard block.
- `warn` — hook surfaces findings but does not block.
- `off` — hook becomes silent (used only by hooks that explicitly support it,
  e.g. `gap_completeness_gate`).

Setting `AGENT_TOOLKIT_STRICT=1` globally forces all per-hook modes to
`block` (CI safety net).

## Operational guidance

- **Production / CI**: keep fail-closed default (no `AGENT_TOOLKIT_NO_STRICT`).
  A crashing guard should block the action it was guarding — the alternative
  is silently shipping broken code through a broken safety net.
- **Local development on a hook**: set `AGENT_TOOLKIT_NO_STRICT=1` in your
  shell to debug a misbehaving hook without it jamming your workflow.
  Inspect `.agent-toolkit/.hook_crash_log.json` for the traceback.
- **Per-hook disable**: prefer editing `.agent-toolkit/enforce_mode.json`
  over patching the hook script. Setting `per_hook.<hook_name>` to `off`
  / `warn` is the supported tuning surface.
- **Emergency stop**: `export AGENT_TOOLKIT_DISABLE=1` silences the entire
  enforcement layer; `session_brief.py` will emit a banner on every new
  session so DEV can't forget the kill-switch is active.

## Hooks worth flagging for behavioral complexity

These three hooks have the most non-obvious control flow and are the most
likely to surprise an operator reading logs:

1. **`evidence_audit.py`** — three independent enforcement layers (PASS-claim
   contract, hallucinated-progress contract, generic claim audit) run in
   priority order, each with its own pass/fail semantics. Adds a recursion
   backup guard (`.stop_audit_count.json`, 60s rolling cap of 3) on top of
   Claude Code's native `stop_hook_active` flag. Docstring explicitly notes
   "fails open on any unexpected error — better to under-block than to
   permanently jam the workflow" — note this is the *internal* layer-level
   fail-open, distinct from the wrapper-level fail-closed crash policy.

2. **`implement_orchestrator.py`** — chains four sub-validators (Phase 5.1
   hallucinated-SD check, 5.2 omitted-SD check, 5.3 diff-hunk annotation,
   5.4 scope creep delegate) at Stop time. Trigger requires five
   simultaneous conditions (non-trunk branch, spec exists, frontmatter
   present, implement-noted file present, done-claim in text). Results
   cached 60s in `.orchestrator_state.json` so the chain doesn't re-run on
   re-Stop within the same response.

3. **`gap_completeness_gate.py`** — three independent resolution mechanisms
   (per-gap `gap-defer: G<N>`, per-gap `gap-cant-fix: G<N>`, whole-gate
   `bypass-gap-gate:` in *prior* prompt). State spans turns via
   `.open_gaps.json` and `.autonomy_active.json`. Skips when autonomy is
   active (auto-chain mid-fix) so /implement can iterate without false
   blocks. Default `block` mode is the strictest hook in the Stop chain.

## Cross-reference

- Hook event registration: `templates/claude/settings.json`.
- Crash log: `.agent-toolkit/.hook_crash_log.json` (ring buffer, ~50 events).
- Fire log (telemetry): `.agent-toolkit/.hook_fire_log.json` (ring buffer,
  1000 events) — feeds `/hook-health`.
- Wrapper source: `templates/claude/hooks/_common.py:429` (`run_main_safe`).
- Per-hook mode reader: `templates/claude/hooks/_common.py:327`
  (`get_enforce_mode`).
- Crash policy gate: `templates/claude/hooks/_common.py:303`
  (`is_fail_closed_mode`).
