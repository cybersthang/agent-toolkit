---
name: gap-status
description: Compose a status table cross-referencing spec acceptance_evals, probe registry, and recent verdicts (auto_run_probes / verify_report). Project-agnostic — driven by `acceptance-probes.schema.json` v2 fields. Triggered explicitly via `/gap-status [<spec-slug>]` or implicitly when invoked by `gap-fix-cycle` and `verify-feature`.
---

# gap-status

## Purpose

Mechanical recap of "what probes are within-predicate vs failing vs unknown" for a spec. Reads-only — never re-runs probes, never edits state. Output is markdown-table-ready for verify_report or PR description.

## Inputs

- Arg: optional `<spec-slug>`.
- Project files: see `/gap-status` command page for the full list.

## Resolution priority for each probe's "last evidence"

1. `.agent-toolkit/.auto_probes_state.json[probe_id]` → `(status, ts)` from auto_run_probes hook.
2. `verify_report.md` table cell for the matching US (regex over predicate/probe id).
3. `.agent-toolkit/.auto_test_state.json[module]` if probe is unit-test-tied (heuristic: probe id contains module name or path_glob points to test).
4. None → "unknown".

## Status classification

| Verdict | Source | Status label |
|---|---|---|
| `proven` / `passed` | auto_run_probes / auto_test_runner | `within-predicate` |
| `refuted` / `failed` | auto_run_probes / auto_test_runner | `failing` |
| any with `ts < now - 7d` AND probe.auto_run=True | auto_run_probes | `stale` |
| verify_report cell shows PASS/proven | verify_report.md | `within-predicate` (manual) |
| verify_report cell shows FAIL/refuted | verify_report.md | `failing` (manual) |
| No verdict source | — | `unknown` |

## Output

Markdown table per the command page schema, plus aggregate counts +
recommended-next-action heuristic:

| Outstanding count | Suggested next |
|---|---|
| ≥ 1 blocker failing | `/implement <slug>` (autonomous gap-fix loop will engage) |
| only warn failing | `/run-probes --probe <id>` (DEV-driven targeted) |
| only unknown probes | `/run-probes` (full diff run) |
| all within-predicate | `/verify <slug>` to finalize report |

## Refuse / clarify when

- See `/gap-status` command page.

## Public extension

- Add new verdict sources by registering `.agent-toolkit/gap_status_sources.json` with regex extractors. Skill auto-merges them with priority order = file order.
- Per-stack mapping (e.g. Django pytest output → `module_name`) plugged via `templates/agent_toolkit/test_mapping/<stack>.json`.

## What this skill MUST NOT do

- Re-run probes (read-only contract).
- Edit spec or verify_report.
- Print real credentials sniffed from any state file.
