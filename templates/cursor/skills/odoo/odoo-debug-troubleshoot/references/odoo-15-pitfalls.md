# Odoo 15 — debug pitfalls (standalone, transitional)

> odoo-15 reference (drafted v0.29). Deltas vs odoo-12 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load this when Step 0 detected major = **15**. v15 mixes v17-style ORM
with v12-style views and a half-migrated frontend — pitfalls cluster
around that seam.

| Symptom | Root cause | Fix |
|---|---|---|
| `AttributeError: module 'odoo.api' has no attribute 'multi'` | Leftover `@api.multi`/`@api.one` from a v12 module | Remove the decorator — recordset is default since v13 (web-verified) |
| Batch `create()` only processes first record | `create()` overridden single-record (`@api.model`, `vals`) | Use `@api.model_create_multi` + iterate `vals_list` (v14+, web-verified) |
| Compute không re-run khi field con thay đổi | `@api.depends` cite sai path | Sửa depends string đúng theo field name — unchanged from v12 |
| `attrs="{...}"` raises "no longer used" | Pasted v17 expectation onto v15 OR malformed JSON | In v15 `attrs`/`states` ARE valid (removed only v17). Fix the JSON quoting, do NOT convert to `invisible="<expr>"` |
| OWL component never mounts / `import` fails | Missing `/** @odoo-module **/` header → ES6 `import` not transpiled | Add the header as line 1 (NEW in v15; transpiled by `js_transpiler.py`, web-verified) |
| `Cannot read properties of undefined` from `@odoo/owl` import | Used the OWL 2 / v16+ package import in v15 | Use the global `owl` (`const { Component } = owl;`) — v15 is OWL 1.x era |
| OWL template ignored / rendered as plain QWeb | Template root missing `owl="1"` attribute | Add `owl="1"` on the `<templates>`/root node (web-verified, 15.0 docs) |
| JS/SCSS file 404 / not loaded | Registered via legacy `<template inherit_id="web.assets_backend">` XML | Move to the manifest `assets` dict (NEW in v15, web-verified) |
| Mock partner `email` bị reject | Default email validator strict | Dùng `<prefix>.test@example.com` style — unchanged from v12 |

## Patterns to expect in a v15 traceback

- `odoo.tools.js_transpiler` lines when an `@odoo-module` JS file has a
  construct the transpiler can't handle (web-verified: it is NOT Babel,
  has documented limitations).
- `web.assets_qweb` bundle references — valid in v15, removed in v16.
- OWL 1.x stack frames on the global `owl` namespace (not `@odoo/owl`).
- `_check_company_auto` consistency errors — multi-company validation
  that does NOT exist in v12 (see odoo-15-multicompany.md).
- NO `@api.multi`/`@api.one` deprecation warnings — those are v12-era;
  in v15 they are hard `AttributeError`s instead.

## Unchanged-from-v12 pitfalls

Constraint-on-create timing, cron `method_direct_trigger()` naming, and
the `Many2one._inherits_check` delegation traceback are unchanged from
v12 — see odoo-12-pitfalls.md.
