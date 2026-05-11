# Odoo 12 — Code Review Reference (Version-Specific Deltas)

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **12**. Combine with the shared dimensions in the parent SKILL.md
and the cross-version checklists under `_common/code-review/references/`.

## A. ORM / API decorators (Odoo 12)

- `@api.multi` on **every** recordset-bound method — this is the default in 12.
- `@api.one` is **forbidden** (deprecated; introduces silent per-record iteration with surprising return shape).
- `@api.model` on class-level methods that don't need a recordset.
- `@api.depends(...)` complete on every computed field; missing fields cause stale values.
- Override `create(self, vals)` is the **single-record** form. Odoo 12 does not require `@api.model_create_multi` (that arrived in 14). If the project mixes 12-style and 17-style overrides on the same class, flag inconsistency (LOW unless a bug actually fires).
- `ensure_one()` whenever a method assumes a single record.

### Severity calibration

| Severity | Concrete example (anchored in NAKIVO audit history) |
|----------|------------------------------------------------------|
| BLOCKER  | Override `create()` declared without `@api.multi` returning a recordset with the wrong dimensionality |
| BLOCKER  | `@api.one` used on a method called from a batch context — silently returns a list of returns instead of the recordset |
| MEDIUM   | `@api.depends` missing a field that the compute reads → stale cached values |
| LOW      | `@api.multi` decorator omitted on a method that happens to work because `self` is always one record in practice (style fix) |

## B. Loops + N+1 (Odoo 12 specifics)

- `search()` / `browse(id)` inside a Python loop → batch via domain or `mapped`.
- `len(search(...))` → must be `search_count`.
- Compute fields with `@api.depends(...)` but `store=False`, called inside another loop, will re-trigger per record — N+1 catastrophe.
- In QWeb reports / templates, `t-foreach` over a 1000+ recordset without pagination is a render-perf hit.

## C. Views (Odoo 12 syntax — DIFFERENT from 17)

- View attribute conditions: `attrs="{'invisible': [('state', '=', 'done')]}"` and `states="draft,confirmed"` — these are the **correct** Odoo-12 idioms. **Do NOT flag them as bugs.**
- Flag instead:
  - Malformed `attrs` JSON (`'invisible': []` with empty leaf).
  - `attrs` referencing a field not declared on the model.
  - `<xpath>` without `position=` attribute.
  - Inheritance edit that replaces an entire root tag (breaks downstream inheritances).
- XML IDs stable across releases. Renaming a published XML ID without a `<delete>` + migration step = LOW.

## D. Frontend (QWeb + jQuery — Odoo 12 default)

- jQuery selectors are **legal** in 12. Flag only if:
  - The selector targets a DOM node that was removed in a recent commit (dead selector).
  - An OWL component was introduced — OWL is not part of Odoo 12; that's importing 17-era code.
- QWeb templates: `t-foreach`, `t-if`, `t-esc`, `t-raw`. `t-raw` is XSS-risk; verify upstream escaping.
- Asset bundles: new JS / SCSS files must be registered in `assets.xml` (template inheritance of `web.assets_backend` / `web.assets_frontend`).
- No `static/src/*.js` with `/** @odoo-module **/` header in 12 — that's an OWL module marker, only valid in 15+.

## E. Security / multi-company (Odoo 12 nuances)

- Every new `models.Model` has at least one `ir.model.access.csv` row. `TransientModel` and `AbstractModel` don't need ACL rows.
- Models touched by multi-company workflows have an `ir.rule` that filters by `company_id` (or follows the parent's rule chain).
- `sudo()` documented with a one-line "why we bypass record rules here" comment.
- CSRF: `type='json'` endpoints in 12 conventionally set `csrf=False` (JSON-RPC frames don't accept form-encoded cross-site POSTs). LOW finding only if no `Content-Type` enforcement; do NOT escalate to MEDIUM by default.
- CSRF: `type='http'` endpoints with state-changing form-POSTs MUST keep `csrf=True`. Flag MEDIUM if `csrf=False` on such endpoint.

## F. Monkey-patches / install-uninstall symmetry (Odoo 12)

- Registry patches via `setattr(BaseModel, ...)` work; verify there's an uninstall path that restores the original.
- `_register_hook` and `_post_init_hook` are common patterns in 12; make sure they're paired with a teardown.
- `_original_methods.clear()` (or equivalent) must run unconditionally on uninstall — otherwise ghost behaviour after a `--uninstall`.

## G. Manifest hygiene (Odoo 12)

- `version`: `12.0.<major>.<minor>.<patch>` — flag if different shape.
- `data` order: `security/` first, then `data/`, then `views/`, then menus.
- `depends`: lists exactly what the module imports / inherits. No "transitive" dependencies (don't list `mail` if only `base` is imported).
- `installable: True`; `application` only when the module is a top-level app.

## H. NAKIVO-specific notes (Odoo-12 NAKIVO workspace only)

- Addon roots (canonical): `nakivo/`, `nakivo-server/addons/`, `nakivo-server/odoo/addons/`, `nakivooca/`, `base_addons/`, `OCA/`, `odoo-12-enterprise-master/addons/`, `odoo-12-enterprise-master/odoo/addons/`.
- Always pass `root_hint` to `discover_modules` / `search_text` to avoid scanning all roots.
- Before answering "is there anything else to fix in `<module>`?", read `.codex/audit_findings_locked.md` (or `.codex/audit_findings_<module>_locked.md`) and cite the locked count.
- JIRA: production at `10.170.180.181:8080`, preproduction at `10.170.179.41`. Use `jira_production` MCP / `jira_preproduction` MCP for ticket context — never hard-code credentials.

## Severity anchors (Odoo-12, from NAKIVO REV-4 audit)

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | Daemon worker thread inside `controllers/<name>.py` raises in the `except` branch with no outer try → thread exits, queue stuck forever (real case: profiler `_log_worker_loop`) |
| BLOCKER  | `additional_info::json -> 'bottleneck_summary'` returns NULL on 50 % of rows because rows are gzip+b64 wrapped and the SQL view doesn't peek through |
| BLOCKER  | `if abs(drift_pct) < 5.0 or abs(signed_drift_ms) < 200.0` (should be AND) — a 56 % drift on a 100 ms trace passes the check |
| MEDIUM   | `csrf=False` on a `type='json'` state-changing endpoint with only `auth='user'` — JSON-RPC limits exploit but admin-victim CSRF still plausible |
| MEDIUM   | `gzip.decompress(b64decode(...))` with no size cap → decompression bomb (insider-only since `auth='user'`) |
| MEDIUM   | `json.dumps(payload)` without `ensure_ascii=False` mangling Vietnamese function/field names in stored JSON |
| MEDIUM   | Field default in Python = 1, fresh-install XML data = 7 — programmatic `create()` produces drift |
| MEDIUM   | `_entries[key] = entry` on register but `unregister()` is the only popper — verify the `finally` actually runs on every path |
| LOW      | `tottime` / `cumtime` cProfile-style keys alongside `_ns` keys — cognitive load, no bug |
| LOW      | Hard-coded `base.user_admin` in `security.xml` — fragile across DBs |
| LOW      | No multi-company `ir.rule` on a model that should be company-scoped |
| LOW      | Capped list `[:1200]` with no `truncated` flag in payload — consumer can't tell |

## Live-verify recipes (Odoo 12 + realdata_test MCP)

```python
# Drift between Python default and DB-stored values
env['<model>'].search_count([('<field>', '=', <python_default>)])
env['<model>'].search_count([('<field>', '=', <xml_default>)])

# Determinism of an aggregation
sum(env['<model>'].search([(<domain>)]).mapped('<field>'))
# Run via consistency_check_eval (runs=3); fingerprints must match.

# Producer-consumer mismatch on persisted JSON
env['<model>'].search([], limit=10).mapped(lambda r: r.additional_info)
```

When raw SQL is needed (e.g. ILIKE on a gzip-wrapped JSON blob), route
through `nakivo_postgres.run_select` — `realdata_test` accepts only single
ORM expressions, no statements.

## Anti-patterns specific to Odoo-12 review

- Flagging `@api.multi` or `attrs="..."` as bugs — they are correct in 12.
- Treating jQuery as deprecated — it is fine in 12; OWL is 17+.
- Suggesting `@api.model_create_multi` — that's 14+. Odoo 12 uses single-record `create(vals)` override.
- Re-deriving "what to fix" without consulting `.codex/audit_findings_*_locked.md` and `canonical_decisions.json` first — that is how counts drift across sessions.
