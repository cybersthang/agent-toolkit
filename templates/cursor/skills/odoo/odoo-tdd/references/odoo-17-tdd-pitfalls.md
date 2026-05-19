# Odoo 17 — TDD pitfalls (head of 17→18→19→20 cascade)

| Pitfall | Detection | Fix |
|---|---|---|
| Test of `create()` override only fires once for a batch | Override still uses `@api.model` (single-record) | Switch to `@api.model_create_multi(vals_list)`; test by passing list of 2+ dicts and asserting both records get post-process |
| Mocked view loads with `attrs="..."` | Removed in 17 → parse error at view load | Convert to `invisible="<expr>"` etc., or skip view test |
| Compute test reads stale value | Recordset auto-flush trigger missed | Same `record.flush()` pattern works |
| Cron test never executes | Use `cron._method_direct_trigger()` on the `ir.cron` record (same name) — but check the field on the cron record is `model_id` not `model` | Read `ir.cron` schema for current version |
| OWL component test missing assets | Component declared in `static/src/` but `'assets'` block in manifest doesn't reference it | Add the JS path to `'assets': {'web.assets_backend': [...]}` |

## Test framework classes (Odoo 17)

- `TransactionCase` — still available, sub-transaction per test.
- `SavepointCase` — **renamed/merged** into `TransactionCase` with savepoint by default in some 17 setups. Check the version's `odoo/tests/common.py` for the exact class.
- `HttpCase` — controller tests; `self.url_open` still works.
- `tagged()` decorator used to filter test runs.

## Hard rules (Odoo 17 TDD)

- `create()` override MUST be `@api.model_create_multi(vals_list)`. Test with a list of ≥2 vals to catch single-record-only bugs.
- Never assert on `name_get()` — deprecated, may not be called by display logic.
- For OWL component tests, run via `HttpCase` browser session (or skip if visual-only).
