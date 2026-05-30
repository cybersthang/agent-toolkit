---
description: Emit a concise GAP/BLOCKER status table for one spec — reads probes registry + last verify_report + last auto_run_probes verdicts. Replaces the DEV-driven "có blocker hay GAP gì không" recap loop.
allowed-tools: Bash, Read, Glob
argument-hint: "[<spec-slug>]"
---

# /gap-status — Concise probe-status summary

## Goal

Replace the manual DEV-driven recap ("còn blocker không?") with one
mechanical command. Outputs ≤ 1-page table mapping each probe in the
spec to its most recent evidence + current status.

## What it reads

1. `.agent-toolkit/specs/**/<slug>.md` — spec frontmatter + acceptance_evals.
2. `.agent-toolkit/acceptance-probes.json` — probe registry (predicate, severity).
3. `.agent-toolkit/.auto_probes_state.json` — most recent auto_run_probes verdict per probe id.
4. `.agent-toolkit/.auto_test_state.json` — most recent auto_test_runner verdict per module.
5. `.agent-toolkit/specs/<branch>/verify_report.md` — last manual `/verify` evidence cell.

## Output (markdown)

```
## Gap status — <spec-slug>

| Probe | Severity | Predicate | Last evidence | Status |
|---|---|---|---|---|
| <id> | blocker | <truncated description> | proven 2026-05-20 03:14 (auto) | within-predicate |
| <id> | warn    | ... | refuted 2026-05-20 02:55 (auto) | failing |
| <id> | blocker | ... | (none) | unknown |

Total: <N> within-predicate · <M> failing · <K> unknown
Blockers outstanding: <list>
GAP probes outstanding: <list>
Next action recommended: <one-line, derived from outstanding>
```

## Step-by-step

1. Resolve `<spec-slug>` from arg or pick the most recently-modified
   `.agent-toolkit/specs/**/*.md`.
2. Load the spec; read `feature_kind`, `acceptance_evals` ids.
3. For each `acceptance_evals[i].id`, look up matching probe in
   `acceptance-probes.json` (by id, prefix, or path_glob overlap).
4. For each probe, find most recent verdict source (priority):
   `.auto_probes_state.json` > `verify_report.md` cell > "(none)".
5. Classify status:
   - `within-predicate`: verdict is `proven` / `passed`.
   - `failing`: verdict is `refuted` / `failed`.
   - `unknown`: no verdict recorded.
   - `stale`: verdict > 7d old + probe.auto_run=true (suggest re-run).
6. Aggregate: count by status, list blocker-severity outstanding.
7. Print markdown table.

## Refuse / clarify when

- No spec found → list candidate slugs + ask DEV to pick.
- Spec has zero probes mapped → recommend `/probe-add` first.
- verify_report.md missing → still emits table using auto_run_probes state only; flags missing report in summary.

## Inputs the command MUST NOT do

- Trigger any probe run (read-only by contract).
- Modify spec frontmatter (read-only by contract).
- Print real credentials or evidence content beyond what verify_report already exposes.

## Linked skills

- `gap-fix-cycle` — DEV may chain `/gap-status <slug>` → `/implement <slug>` to auto-fix outstanding probes.
- `spec-vs-evidence-diff` — sibling: surfaces recipe-vs-script drift; complementary signal.
