---
name: odoo-data-verification
description: Verify Odoo algorithms against real or staging data using the realdata_test MCP. Use when the question is "is this calculation correct?" or "is this method deterministic?". Works for any Odoo major version (12, 17, 18, 19, 20, future) — the `realdata_test` MCP wraps `odoo-bin shell` which is version-agnostic. Module-agnostic.
---

# Odoo — Data Verification on Real Data (version-agnostic)

The `realdata_test` MCP runs read-only ORM expressions against the configured DB through `odoo-bin shell`. Mutation tokens (`write`, `create`, `unlink`, `commit`, `=`, `import`, dunders, etc.) are statically rejected.

The same surface works for Odoo 12 → 20. Differences across versions (e.g. `@api.multi` decorator on the method being probed, `name_get` vs `_compute_display_name`, `aggregator=` vs `group_operator=`) only affect how you *write* the expression — they don't change how to verify it.

## 0. Version detection (MANDATORY before composing the expression)

Even though the *verification mechanism* is version-agnostic, the
*expression you write* is highly version-specific. Quick model/field
mismatches that silently return wrong data:

- `account.invoice` (v12-13) vs `account.move` (v14+)
- `state='open'` (v12-13 invoice) vs `state='posted'` (v14+ move)
- `name_get()` (≤16) vs `_compute_display_name` (17+)
- `aggregator='sum'` (v18+) vs `group_operator='sum'` (≤17) on field declarations
- `payment.acquirer` (≤v15) vs `payment.provider` (v16+) model name

**Protocol:** read `__manifest__.py` via `codebase.read_manifest` and
parse `version` field with regex `^(\d+)\.0\.`. If detection is
ambiguous (mixed monorepo), call `codebase.search_model_definitions`
for the model your expression references to confirm it exists on the
target version. State the detected version + which models you assumed
in the report header.

Routing table:

| Detected major | Expression style |
|---|---|
| 12 | `account.invoice`, `state='open'`, `name_get()`. v12 ORM eval works the same way; just match the symbols. |
| 13 | Mixed — both `account.invoice` and `account.move` exist; verify which is in use via `search_count` before composing the aggregate. |
| 14-16 | `account.move`, `state='posted'`, `name_get()` still standard. |
| 17+ | `account.move`, `_compute_display_name`. v18+ adds `aggregator='sum'`. v17 renames `mail.channel`→`discuss.channel`; verify `mail.message`/`discuss.channel` schema against installed source before aggregating thread data. |

## When to use this skill

- A computed field's stored values look suspicious.
- An algorithm produces different totals between two reports.
- You changed a method and need to compare old vs. new behaviour against real records.
- A spec says "the rule is deterministic" and you must prove it.
- `/verify <slug>` (Spec Kit Phase 5) is running probes and you need ORM/DB layer evidence.

## Three primary tools

| Tool                     | Purpose                                                                                  |
|--------------------------|------------------------------------------------------------------------------------------|
| `eval_orm_expression`    | One-shot read-only ORM expression. Returns value + sha256 fingerprint.                   |
| `consistency_check_eval` | Runs the same expression N times and asserts identical fingerprints. Proves determinism. |
| `compare_with_expected`  | Runs an expression and compares against a caller-supplied expected JSON value.           |

## Workflow

1. **Frame the question as one expression.** Examples:
   - `env['sale.order'].search_count([('state','=','done')])`
   - `sum(env['account.move'].search([('date','=','2026-04-30')]).mapped('amount_total'))`
   - `[(o.id, o.amount_total) for o in env['sale.order'].search([('partner_id','=',42)])][:10]`
2. **Run once with `eval_orm_expression`.** Inspect the value and fingerprint.
3. **Prove determinism with `consistency_check_eval` (runs=2 or 3).** If `deterministic: false`, the algorithm depends on hidden state (clock, random, ordering) — flag and fix.
4. **Compare against ground truth with `compare_with_expected`.** Useful when the user gives you the number from a UI report.

## Hard rules

- The expression must be a **single Python expression**, not a statement. No `=`, no `;`, no newlines.
- Never bypass the sandbox by chaining unrelated calls. If you need state, ask the user; do not write a wizard / cron / migration through this tool.
- For module install/update tests, use `run_module_test` with explicit `allow_db_write=true` on a staging DB only.
- `database_looks_production=true` means stop and ask.

## Anti-patterns

- "Just run the cron and see what happens." → use a sandboxed expression first.
- Comparing aggregates with `==` in your head. → use `compare_with_expected`.
- Running once and declaring "looks deterministic." → always use `consistency_check_eval`.
