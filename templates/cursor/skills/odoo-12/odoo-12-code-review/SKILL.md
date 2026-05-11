---
name: odoo-12-code-review
description: Exhaustive code review for Odoo 12 modules — applies the shared `code-review` workflow plus Odoo-12-specific checklist (api decorators, attrs/states, jQuery/QWeb, monkey-patches, multi-company). Open this skill whenever the user asks "review", "audit", "phân tích sâu", "tìm bug", or "còn gì cần fix?" against Odoo 12 code. Module-agnostic.
---

# Odoo 12 — Code Review Overlay

Read `_common/code-review` first — it owns the workflow, severity rubric,
PROOF contract, and reporting format. This file only adds the Odoo-12-specific
checklist and tool routing.

## 0. Tool routing (Odoo 12 stack)

| Need                              | MCP                              | Tool                                                            |
|-----------------------------------|----------------------------------|-----------------------------------------------------------------|
| Confirm addon roots in scope      | `nakivo_codebase`                | `workspace_status`, `discover_modules({root_hint})`             |
| Identify the model + extensions   | `nakivo_codebase`                | `find_inheritance_chain({model})`                               |
| List tests + check coverage gaps  | `nakivo_codebase`                | `list_test_targets`                                             |
| Cross-check XML IDs               | `nakivo_codebase`                | `search_xml_ids`                                                |
| Static text search (cite path:line) | `nakivo_codebase`              | `search_text({pattern, root_hint})`                             |
| Live-verify a Medium against DB   | `nakivo_realdata_test`           | `eval_orm_expression`, `consistency_check_eval`                 |
| Inspect raw SQL state             | `nakivo_postgres`                | `run_select`                                                    |
| Lock + cite results               | `nakivo_codebase`                | `lookup_canonical_decision({topic: "audit findings <module>"})` |

## 1. Severity examples grounded in Odoo 12 (mirror the shared rubric)

Use these as calibration anchors when you assign a level. They come from real
NAKIVO audit history.

| Severity | Concrete Odoo-12 example |
|----------|--------------------------|
| BLOCKER | Daemon worker thread inside `controllers/<name>.py` raises in the `except` branch with no outer try → thread exits, queue stuck forever |
| BLOCKER | `additional_info::json -> 'bottleneck_summary'` returns NULL on 50 % of rows because rows are gzip+b64 wrapped and the SQL view doesn't peek through |
| BLOCKER | `if abs(drift_pct) < 5.0 or abs(signed_drift_ms) < 200.0` (should be AND) — a 56 % drift on a 100 ms trace passes the check |
| MEDIUM  | `csrf=False` on a `type='json'` state-changing endpoint with only `auth='user'` — JSON-RPC limits exploit, but admin-victim CSRF still plausible |
| MEDIUM  | `gzip.decompress(b64decode(...))` with no size cap → 1 KB → GB decompression bomb (insider-only since `auth='user'`) |
| MEDIUM  | `json.dumps(payload)` without `ensure_ascii=False` mangling Vietnamese function/field names in stored JSON |
| MEDIUM  | Field default in Python = 1, fresh-install XML data = 7 — programmatic `create()` produces drift |
| MEDIUM  | `_entries[key] = entry` on register but `unregister()` is the only popper — verify the `finally` actually runs on every path |
| LOW     | `tottime`/`cumtime` cProfile-style keys alongside `_ns` keys — cognitive load, no bug |
| LOW     | Hard-coded `base.user_admin` in `security.xml` — fragile across DBs |
| LOW     | No multi-company `ir.rule` on a model that should be company-scoped |
| LOW     | Capped list `[:1200]` with no `truncated` flag in payload — consumer can't tell |

## 2. Odoo-12-specific dimensions (additions to the shared matrix)

When walking the dimensions matrix in `_common/code-review`, add these
Odoo-12-only probes:

### A. ORM / API decorators
- `@api.multi` present on every method that touches recordsets — `@api.one`
  is **forbidden** in Odoo 12.
- `@api.model` on class-level methods that don't need a recordset.
- `@api.depends(...)` complete on every computed field; missing fields cause stale values.
- Override `create()` accepts a single-record `vals` dict — Odoo 12 does not
  yet require `@api.model_create_multi`. If the codebase mixes batch and
  single-record overrides, flag inconsistency.
- `ensure_one()` everywhere a method assumes a single record.

### B. Loops + N+1
- `search()` / `browse(id)` inside Python loops → batch via `mapped` / domain.
- `len(search(...))` → must be `search_count`.
- Computed field with `@api.depends(...)` but unstored, called inside another
  loop — N+1 catastrophe.

### C. Views
- Odoo-12 view syntax uses `attrs="{...}"` and `states="..."` — **expected**
  in 12, not a bug. (In 17 they would be removed.) Flag only when the
  attrs JSON is malformed, or when the field referenced doesn't exist.
- `<xpath expr="..." position="...">` used for every inheritance edit.
- XML IDs stable across releases; renaming without a migration step is a LOW.

### D. Frontend (QWeb + jQuery)
- jQuery selectors are still legal in 12 — flag only when the selector matches
  a removed DOM node, or when an OWL component is mistakenly introduced.
- QWeb templates: `t-foreach`, `t-if`, `t-esc` vs `t-raw` (XSS risk on `t-raw`).
- Asset bundles: new JS / SCSS file must be registered in `assets.xml`.

### E. Security / multi-company
- Every new model has a row in `ir.model.access.csv`.
- Models touched by multi-company workflows have an `ir.rule` aligned with
  the parent chain.
- `sudo()` calls have a one-line comment explaining why.

### F. Monkey-patches / install/uninstall symmetry
- `setattr(BaseModel, ...)` or similar registry patches: verify
  `_register_hook` and `_post_init_hook` mirror an uninstall path that
  restores the original. Missing teardown → ghost behaviour after uninstall.

### G. Manifest hygiene
- `data` order: `security/` first, then `data/`, then `views/`, then menus.
- `depends` lists exactly the modules referenced by imports + inherits.
- `version` matches `12.0.x.y.z` pattern.
- `installable: True`; `application` only when the module is a top-level app.

### H. NAKIVO-specific (only when the module lives under NAKIVO addon roots)
- Discover module via `nakivo_codebase.discover_modules({root_hint: "nakivo"})`
  before assuming a NAKIVO convention applies.
- Check `.codex/canonical_decisions.json` for `audit findings <module>` first —
  the count may already be locked.

## 3. Live-verify recipes (Odoo 12 + `nakivo_realdata_test`)

Use these expression patterns when verifying Mediums on real data:

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

When a Medium needs raw SQL (e.g. ILIKE on encoded blob), route through
`nakivo_postgres.run_select` — `realdata_test` is for ORM expressions only.

## 4. Reporting (Odoo 12 specifics)

Per-finding block adds two optional fields beyond the shared contract:

```
- Module: <addon-root>/<module-name>
- Odoo version touchpoints: <e.g. "core override of mail.thread", "registry patch", "controller">
```

The lock file path convention for NAKIVO is
`.codex/audit_findings_<module>_locked.md`. If you create the first
revision, header must include the methodology lock paragraph from
`_common/code-review` Step 3 (BLOCKER / MEDIUM / LOW criteria) so future
sessions can self-audit.

## 5. Anti-patterns specific to Odoo 12 review

- Flagging `@api.multi` or `attrs="..."` as bugs — they are correct in 12.
- Treating jQuery as deprecated — it is fine in 12; OWL is 17+.
- Re-deriving "what to fix" without consulting `.codex/audit_findings_*_locked.md` and `canonical_decisions.json` first — that is how counts drift across sessions.
- Skipping NAKIVO modules under different addon roots because they "look similar" — every module gets the dimensions matrix from scratch.

## 6. Final self-check (run BEFORE sending the report)

In addition to the four from `_common/code-review` Step 9, also verify:

5. Did I check the JIRA workflow (via `jira_production` or `jira_preproduction`) for any open ticket against this module that may already document a finding? If yes, cite the ticket.
6. Did I look at every Odoo-12-specific dimension (A–H above), not just the generic 16?
7. Did I open `_common/code-review/references/security-checklist.md` when walking Dimension 4 / 9, and `performance-checklist.md` when walking Dimension 2 / 3 / 13 / 15? They contain Odoo-specific items not duplicated here.
