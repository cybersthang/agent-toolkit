---
description: Run all acceptance probes that match files changed in the current diff. One-command empirical verification across modified features — eliminates the friction of running probes manually one-by-one.
allowed-tools: Bash, Read
argument-hint: "[scope: 'staged' | 'branch' | <probe-id>]"
---

# /run-probes — Empirical verification for the diff

## Goal

Address dev's root-cause concern: running real-data verification was
HIGH-friction, so agents (and devs) skipped it and shipped bugs. This
command makes empirical verification a **single command**.

## What it does

1. Resolve scope:
   - `staged` (default): `git diff --cached --name-only`
   - `branch`: `git diff --name-only origin/main...HEAD`
   - `<probe-id>`: run just that one probe
2. For each changed file, find probes in `acceptance-probes.json`
   whose `applies_when.path_globs` match.
3. For each matched probe, invoke the appropriate falsifier runner:
   - `timing_perturb` → `python .codex/tools/falsify.py --probe <id>`
   - `side_effect_inject` → same CLI, dispatches by type
   - `log_assertion` → same CLI
4. Aggregate results: PROVEN / REFUTED / ERROR per probe.
5. Exit:
   - 0 if all PROVEN (or no probes matched)
   - 1 if any REFUTED
   - 2 if any ERROR (network, missing config, etc.)

## When to run

- **Before claiming PASS in conversation** — fastest way to make
  PASS-claim contract happy.
- **Before pushing a feature branch** — verifies all changed features
  empirically, not just statically.
- **In CI pipeline** — drop-in `python .codex/tools/falsify.py --probe X`
  per matched probe; aggregate via GitHub Actions matrix.

## Step-by-step

1. `Bash git diff --cached --name-only` (or branch variant).
2. `Read .agent-toolkit/acceptance-probes.json`.
3. For each file in diff:
   - Match against each probe's `applies_when.path_globs`.
   - If match → add probe id to "to-run" set.
4. For each probe id:
   - `Bash python .codex/tools/falsify.py --probe <id> --dry-run`
     first → preview the recipe.
   - Wait for user confirmation OR `--yes` flag to auto-proceed.
   - `Bash python .codex/tools/falsify.py --probe <id>` for real.
   - Parse exit code → PROVEN (0) / REFUTED (1) / ERROR (2).
5. Render summary table:
   ```
   | Probe | Type | Verdict | Time |
   |-------|------|---------|------|
   | load-views-blocking | timing_perturb | PROVEN | 4.2s |
   | items-no-sql-injection | log_assertion | REFUTED — pattern matched | 0.3s |
   ```
6. If any REFUTED: cite the falsifier's stderr output verbatim so dev
   sees the exact mismatch.

## Refuse / clarify when

- Scope is `branch` but `origin/main` not configured → ask which
  remote/branch to diff against.
- No probes match any changed file → confirm "0 probes ran" and
  suggest running `/probe-coverage` to see if it's expected.
- Falsifier sandbox rejects a probe's `measurement_command` → surface
  the rejection (security feature, not a bug); ask user to fix probe
  config and retry.

## Limitations

- Live measurements need a running service (e.g. Odoo at localhost:8069).
  If service unreachable, falsifier returns ERROR — that's not a
  refutation, it's a infrastructure issue. Surface clearly.
- `timing_perturb` mutates source files. If a probe is mid-run when
  the user interrupts, the `_restore` may not execute. Atomic-write
  + backup mitigates but isn't bulletproof. Always verify `git status`
  after an interrupted run.

## What NOT to do

- Do NOT chain `/run-probes` into auto-commit. Probes are verification
  steps, not gating logic — dev should review verdicts before commit.
- Do NOT silently skip probes whose `falsification.runner` is missing.
  Surface "probe X has no runner — register one via /probe-add".
