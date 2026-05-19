# Odoo 12 — TDD pitfalls (standalone)

| Pitfall | Detection | Fix |
|---|---|---|
| Test passes locally but fails in CI | Test depends on database state from a previous run | Use `SavepointCase` (auto-rollback) or `tearDown` cleanup |
| `KeyError: 'ir.model.access'` | New model has no access row | Add `security/ir.model.access.csv` row before re-running |
| Constraint test silently passes | `_constrains` only fires on write, not on `create()` of pre-validated records | Force a `record.write({...})` after create to trigger |
| Cron test never executes the job | `model.with_context(cron_method=...)` not used | Call `_method_direct_trigger()` on the `ir.cron` record, not the model method |
| Mock partner `email` rejected | Default email validator blocks placeholder strings | Use a real-shaped placeholder like `<prefix>.test@example.com`, not `mock@mock` |
| `@api.depends` test never recomputes | Reading a stored compute on a non-flushed record | Add `record.flush()` before reading |
| Test asserts on `Many2one.name` and breaks under translation | Test DB language drift | Compare `record.partner_id.id`, not `.name` |

## Test framework classes (Odoo 12)

- `TransactionCase` — open by default, rolls back after each test method.
- `SavepointCase` — opens once per class (`setUpClass`), savepoints around each test method. Faster for shared fixtures.
- `HttpCase` — for controller tests (uses `self.url_open`).
- No async test helpers — Odoo 12 is sync.

## Hard rules (Odoo 12 TDD)

- Override of `create()` is single-record `@api.model` — test the wrapping (passing one vals dict).
- `@api.multi` is required on recordset methods — if the test calls a method without `@api.multi`, the framework silently turns it into `@api.one` behaviour.
