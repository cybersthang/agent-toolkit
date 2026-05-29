> odoo-14 reference (drafted v0.29). Deltas vs odoo-12-pitfalls.md web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

# Odoo 14 — debug pitfalls (standalone)

| Symptom | Root cause | Fix |
|---|---|---|
| `ImportError`/`AttributeError` on `from odoo.api import multi` (or `@api.multi`) | `@api.multi` was removed in Odoo 13 — code is pre-13 and never migrated | Remove the decorator; methods iterate `self` (recordset) by default in 14 |
| `@api.one` not found | Removed in 13 | Remove decorator; loop `for r in self` and return per-record yourself |
| `create()` post-process runs only on first record of a batch | Override uses single-record `@api.model create(self, vals)` | Switch to `@api.model_create_multi` with `create(self, vals_list)` |
| Deprecation warning "Context key 'force_company' is no longer supported" | `with_context(force_company=...)` — that 12-era key is dead in 14 | Use `recordset.with_company(company)` (verified `odoo/models.py` 14.0) |
| Deprecation warning on `_company_default_get` | `res.company._company_default_get` is deprecated in 14 | Use `default=lambda s: s.env.company` |
| `invisible="state == 'done'"` on a `<field>` does nothing / parse error | Direct expression view syntax is 17+; 14 uses `attrs` | Use `attrs="{'invisible': [('state','=','done')]}"` |
| Manifest `'assets': {...}` dict silently ignored | Manifest assets dict is 15+; 14 declares assets via XML | Add a `<template inherit_id="web.assets_backend">` record with `<script>`/`<link>` |
| `@api.ondelete(...)` not found | `@api.ondelete` is 15+ | Override `unlink()` with your guard, or add an SQL `_sql_constraints` |
| Cron `_method_direct_trigger()` not found | Method name has no leading underscore | Call `method_direct_trigger()` on the `ir.cron` record (verified `ir_cron.py` 14.0) |
| Mock partner `email` rejected | Default email validator strict | Use `<prefix>.test@example.com`, not `mock@mock` |
| `attrs="{...}"` not parsing | View XML syntax error (missing quote on a domain value) | `attrs="{'invisible': [('state','=','done')]}"` — quote string domain values |

## What changed vs v12 (web-verified deltas)

- `@api.multi` / `@api.one` **gone** since 13 — verified `odoo/odoo` 14.0
  `odoo/api.py` has no such decorators.
- `@api.model_create_multi` **present** — verified api.py 14.0; base
  `create(self, vals_list)`.
- Multi-company is the `with_company()` era — `force_company` context key
  is dead (verified models.py 14.0 deprecation log line).

## What is unchanged from v12 (cascade — see odoo-12-pitfalls.md)

- `@api.depends` citing a wrong field path → compute never re-runs.
- `_constrains` vs wizard-create ordering (force a `write()` after create).
- View `attrs="{...}"` is still the conditional-visibility idiom.

## Patterns to expect in v14 traceback

- `odoo.api.model_create_multi` in the create call chain.
- `odoo.fields.Many2one._inherits_check` (delegation issue) — unchanged.
- `odoo.addons.base.models.ir_ui_view._validate_attrs` for malformed `attrs`.
- A `force_company`/`_company_default_get` deprecation warning in the log
  (not an exception) — signals legacy multi-company code surviving into 14.
- OWL is present in 14; an OWL stack frame (`owl.`) in a frontend traceback
  is legitimate. <!-- VERIFY(odoo-14): exact OWL module/runtime namespace in
  14 frontend tracebacks before asserting a specific OWL frame shape. -->
