---
name: odoo-17-data-verification
description: Verify Odoo 17 algorithms against real or staging data using the realdata_test MCP. Use when the question is "is this calculation correct?" or "is this method deterministic?". Module-agnostic.
---

# Odoo 17 — Data Verification on Real Data

The `realdata_test` MCP runs read-only ORM expressions against the configured DB through `odoo-bin shell`. Mutation tokens (`write`, `create`, `unlink`, `commit`, `=`, `import`, dunders, etc.) are statically rejected.

## When to use this skill

- A computed field's stored values look suspicious.
- An algorithm produces different totals between two reports.
- You changed a method and need to compare old vs. new behaviour against real records.
- A spec says "the rule is deterministic" and you must prove it.

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
