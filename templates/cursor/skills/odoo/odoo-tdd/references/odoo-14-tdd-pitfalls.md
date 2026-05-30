> odoo-14 reference (drafted v0.29). Deltas vs odoo-12-tdd-pitfalls.md web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

# Odoo 14 — TDD pitfalls (standalone)

| Pitfall | Detection | Fix |
|---|---|---|
| Test of `create()` override only fires once for a batch | Override uses single-record `@api.model create(self, vals)` | Switch to `@api.model_create_multi(vals_list)`; test by passing a list of ≥2 dicts and asserting both records get post-processed |
| Test adds `@api.multi` to a helper and import fails | `@api.multi` removed in 13 (verified `odoo/api.py` 14.0) | Drop the decorator; methods iterate `self` by default |
| Test switches company with `env(company=...)` and gets `TypeError` | `Environment.__call__` in 14 takes only `cr, user, context, su` (verified api.py 14.0) — no `company` kwarg | Use `recordset.with_company(company)` instead |
| Test relies on `with_context(force_company=...)` and company never switches | `force_company` is dead in 14 (warns + ignored) | Use `.with_company(company)` |
| `KeyError: 'ir.model.access'` | New model has no access row | Add `security/ir.model.access.csv` row before re-running |
| Constraint test silently passes | `_constrains` fires on write but compute not yet populated on wizard-create | Force `record.write({...})` after create to trigger |
| Cron test never executes the job | Wrong trigger method name | Call `method_direct_trigger()` (no leading underscore) on the `ir.cron` record (verified `ir_cron.py` 14.0) |
| Mock partner `email` rejected | Default email validator blocks placeholders | Use `<prefix>.test@example.com`, not `mock@mock` |
| `@api.depends` test never recomputes | Reading a stored compute on a non-flushed record | Add `record.flush()` before reading |
| Test asserts on `Many2one.name` and breaks under translation | DB language drift | Compare `record.partner_id.id`, not `.name` |
| View-load test fails on `invisible="<expr>"` | Direct expression view syntax is 17+; 14 uses `attrs` | Use `attrs="{'invisible': [...]}"` in the test view |

## Test framework classes (Odoo 14)

Verified `odoo/tests/common.py` 14.0:

- `TransactionCase` — open by default, rolls back after each test method.
- `SavepointCase` — opens once per class (`setUpClass`), savepoints around
  each test. NOT yet merged into `TransactionCase` (that is 17+). Faster
  for shared fixtures.
- `HttpCase` — controller tests (`self.url_open`).
- `Form` — in-memory onchange-driven record builder (present in 14).
- `tagged(*tags)` — filter test runs (present in 14).
- No async test helpers — 14 backend is sync.

## Hard rules (Odoo 14 TDD)

- `create()` override is `@api.model_create_multi(vals_list)`. Test with a
  list of ≥2 vals dicts to catch single-record-only bugs (delta vs v12,
  where the override was single-record `@api.model`).
- **Never `@api.multi` / `@api.one`** in test helpers — removed in 13;
  import-time failure.
- Switch company in tests with `.with_company()` — the `env(company=...)`
  kwarg and merged-`SavepointCase` are 17+, not in 14.
- Don't assert on `name_get()`-derived display strings if a translation may
  differ; compare ids. `name_get()` is still the override point in 14
  (deprecated only in 16.4) — do NOT replace it with `_compute_display_name`
  expectations for a 14 module.
