# Odoo 13 — TDD pitfalls (standalone)

> odoo-13 reference (drafted v0.29). Deltas vs odoo-12-tdd-pitfalls.md web-verified where cited; `<!-- VERIFY -->` items need DEV confirmation.

Load when Step 0 detected major = **13**. The test framework classes are
the same as v12; the deltas are the removed `@api.multi`, the
multi-record `create()`, and the `account.move` merge in accounting
fixtures.

## 13-specific pitfalls

| Pitfall | Detection | Fix |
|---|---|---|
| Test fixture builds an invoice via `env['account.invoice']` and errors | `account.invoice` removed in 13 (merged into `account.move`) | Create `env['account.move']` with `type='out_invoice'` and `invoice_line_ids` |
| Fixture sets `move_type` on `account.move` and field is rejected | 13 uses `type`, not `move_type` (that is v14) | Use `type` on 13 |
| Test method decorated `@api.multi` / `@api.one` fails at import | Both removed in 13 | Delete the decorator; loop `for rec in self:` |
| Test for a `create()` override only exercises the single-record path | 13 `create()` is multi-record (`@api.model_create_multi`) | Test BOTH a single dict and a list of dicts; assert override logic runs per record |
| Cross-company test reads stale company-dependent value | Active company not switched, or compute missing `@api.depends_context('force_company')` | Switch via `allowed_company_ids` / `force_company` context; add the context-depends |

## Pitfalls UNCHANGED from v12

See odoo-12-tdd-pitfalls.md — identical in 13 (only drop `@api.multi`
from example code):
- DB state bleed between runs → use `SavepointCase` / `tearDown`.
- `KeyError: 'ir.model.access'` → add the access CSV row.
- `_constrains` fires on write not on pre-validated create → force a
  `record.write({...})`.
- `ir.cron` job never runs in test → call `method_direct_trigger()` on
  the `ir.cron` record.
- Email validator rejecting `mock@mock` → use `<prefix>.test@example.com`.
- Stored compute read on a non-flushed record → `record.flush()` first.
- Asserting on `Many2one.name` under translation drift → compare `.id`.

## Test framework classes (Odoo 13)

Verified against 13.0 `odoo/tests/common.py`:
- `TransactionCase` — opens per method, rolls back after each.
- `SingleTransactionCase` — one transaction for the whole class.
- `SavepointCase` — opens once per class (`setUpClass`), savepoints
  around each method. Faster for shared fixtures.
- `HttpCase` — controller tests (`self.url_open`).
- `Form` — the in-test `Form(...)` view-emulation helper (present in 13;
  NOT a 13 delta — it already existed in v12).
- No async test helpers — Odoo 13 is sync.

## Hard rules (Odoo 13 TDD)

- Override of `create()` is multi-record `@api.model_create_multi` —
  test the wrapping with BOTH a single vals dict and a list of dicts.
- NO `@api.multi` on recordset methods (removed in 13) — a test calling a
  method that still carries it will fail at import, not silently degrade.
- Accounting fixtures use `account.move` (field `type`,
  `invoice_line_ids`, `action_post()`), never `account.invoice`.
