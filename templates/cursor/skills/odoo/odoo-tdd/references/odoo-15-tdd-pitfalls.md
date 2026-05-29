# Odoo 15 — TDD pitfalls (standalone, transitional)

> odoo-15 reference (drafted v0.29). Deltas vs odoo-12 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load when Step 0 detected major = **15**. Test-framework classes are
largely the v12 set; the ORM-side pitfalls shift because `@api.multi` is
gone and `create()` is batch.

| Pitfall | Detection | Fix |
|---|---|---|
| Test passes locally but fails in CI | Test depends on DB state from a prior run | Use `TransactionCase`/`SavepointCase` (auto-rollback) — unchanged from v12 |
| `KeyError: 'ir.model.access'` | New model has no access row | Add `security/ir.model.access.csv` row — unchanged from v12 |
| `AttributeError: module 'odoo.api' has no attribute 'multi'` at test import | Test (or tested model) carries leftover `@api.multi` | Remove it — gone since v13 (web-verified) |
| Batch-create test asserts wrong record count | Tested `create()` is single-record while test passes a `vals_list` | Override with `@api.model_create_multi`; pass/assert on the list form (v14+) |
| Constraint test silently passes | `_constrains` fires on write not pre-validated create | Force a `record.write({...})` after create — unchanged from v12 |
| Mock partner `email` rejected | Default email validator | Use `<prefix>.test@example.com` — unchanged from v12 |
| `@api.depends` test never recomputes | Reading a stored compute on a non-flushed record | Flush before reading; verify the exact 15.0 flush method name (see below) |
| OWL component test fails to mount in a tour | Missing `/** @odoo-module **/` header or `owl="1"` template attr | Add the v15 header / attr (web-verified) |

## Test framework classes (Odoo 15)

- `TransactionCase` — rolls back after each test method.
- `SavepointCase` — opens once per class (`setUpClass`), savepoints per
  method. STILL available in v15; merged INTO `TransactionCase` in v16
  and `SavepointCase` import raises in v17+ (web-verified). Prefer
  `TransactionCase` in new v15 tests to ease the v16/17 migration.
- `HttpCase` — controller / tour tests (`self.url_open`). OWL tours work
  in v15.
- No async test helpers — Odoo 15 ORM is sync.

<!-- VERIFY(odoo-15): exact flush API on the test recordset in 15.0 (record.flush() vs env.flush_all()/flush_recordset() — the rename spans 13–16). Confirm against 15.0 models.py before asserting a name in test docs. -->

## Hard rules (Odoo 15 TDD)

- DELTA from v12: do NOT add `@api.multi` to test or model methods —
  removed v13; leftover usage is an import-time `AttributeError`.
- DELTA from v12: `create()` overrides are batch — test the `vals_list`
  (list) form with `@api.model_create_multi`, not a single `vals` dict.
- Translation-drift assertion rule (compare `.id`, not `.name`) and
  constraint-on-create timing are unchanged from v12 — see
  odoo-12-tdd-pitfalls.md.
