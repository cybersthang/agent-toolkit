# Odoo 16 — Code Review Reference (Version-Specific Deltas)

> odoo-16 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **16**. Neighbour template is `odoo-17-rules.md` — combine with
the shared dimensions in the parent SKILL.md and the cross-version
checklists under `_common/code-review/references/`. This file records
only where 16 review rules diverge from 17.

## A. ORM / API decorators (Odoo 16)

- `@api.multi` is **removed** (since v14) — recordset is default.
  Identical to v17 — see `odoo-17-rules.md` §A.
- `@api.model_create_multi(vals_list)` required for `create()`
  overrides; single-record `@api.model create(self, vals)` silently
  breaks batch creates. Identical to v17.
- **`name_get()` is the display-label override on 16.0** (DELTA vs 17).
  Reviewing a 16.0 module: an override of `name_get()` is CORRECT — do
  NOT flag it as legacy. **Minor-version nuance**: `name_get()` is
  **deprecated in saas-16.4** in favour of `_compute_display_name`
  (verified: odoo/odoo PR #122085 on saas-16.4) and **removed in 17.0**
  (commit 3c62ca1). So on a 16.4+ SaaS target, `_compute_display_name`
  is correct and `name_get` is legacy-but-working; on 16.0 stable,
  `name_get` is the canonical form. Establish the exact 16 minor before
  flagging either way.

### Severity calibration

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | Override `create()` with `@api.model` instead of `@api.model_create_multi(vals_list)` → batch creates apply only to first record |
| BLOCKER  | `@api.multi` decorator on a method → import-time AttributeError (gone since 14) |
| MEDIUM   | `@api.depends` missing a field the compute reads → stale cached values |
| LOW      | Flagging a `name_get()` override as "should be `_compute_display_name`" on a 16.0 target — that conversion only applies from saas-16.4 / 17.0 |

## B. Loops + N+1

Unchanged from v17 — see `odoo-17-rules.md` §B. (No `search()`/`browse(id)`
in loops; `search_count()` over `len(search())`; compute calling
`search()` inside `for record in self` is N+1, often BLOCKER.)

Note: `search_count()` honours a `limit` argument in 16 (verified:
odoo/odoo #95589, landed for 16.0) — flag `len(search(..., limit=N))`
where `search_count(domain, limit=N)` would short-circuit.

## C. Views (Odoo 16 syntax — DELTA vs 17, matches v12 era)

- **`attrs="{...}"` and `states="..."` are VALID in 16.** A new 16 view
  shipping `attrs` is CORRECT — do NOT flag. Conversely, inline
  `invisible="<py expr>"` on a `<field>` does NOT work in 16 → if a 16
  file ships `invisible="state == 'done'"`, that is written-for-17 and
  fails to evaluate as intended: MEDIUM (escalate to BLOCKER if in an
  active deploy). (Verified: inline-expr replacement is "since 17.0".)
  ```xml
  <field name="custom_field"
         attrs="{'invisible': [('state','=','done')]}"/>
  ```
- **`<tree>` is the list tag in 16**; `<list>` is the v17 rename. A 16
  view using `<list>` → flag.
- Inheritance `<xpath expr position="after|before|inside|replace|attributes">`
  — unchanged from v17.
- `groups` attribute directly on view elements works in 16 without the
  separate-view workaround older versions needed (verified: OCA v16
  migration notes) — do not flag a `groups="..."` element as needing a
  dedicated group view.
- View arch validates field references at install — flag any view
  referencing an undeclared field. Same as v17.

## D. Frontend (OWL 2.x — SAME as v17)

Unchanged from v17 — see `odoo-17-rules.md` §D. OWL 2.x component
authoring is identical: `static template`, `setup()`,
`useService("orm"|"notification"|"action"|"user")`, `/** @odoo-module **/`
header, `registry.category("actions").add(...)`. New jQuery selectors in
new 16 code → MEDIUM (legacy debt).

Caveat for 16: the *webclient* is only partially migrated to OWL in 16
(the full view/field OWL rewrite lands in 17), so more legacy
`web.Widget`/jQuery survives in 16 core than in 17 — weight "legacy
debt" findings accordingly; matching an existing legacy widget is not
automatically wrong on a 16 target.

## E. Security / multi-company (Odoo 16)

Unchanged from v17 — see `odoo-17-rules.md` §E. `_check_company` /
`_check_company_auto = True` + `check_company=True` are mature in 16
(introduced v13/v14). CSRF policy unchanged from 12.

## F. Monkey-patches / install-uninstall symmetry

Unchanged from v17 — see `odoo-17-rules.md` §F.

## G. Manifest hygiene (Odoo 16)

- `version`: `16.0.<major>.<minor>.<patch>` — flag if different shape.
- `'assets'` declared as a dict in the manifest (the v15+ form) — same
  as v17. Do NOT expect the v12-era XML `<template>` asset-bundle
  records.
- `data` order, `depends`, `license`, `installable`/`application` —
  unchanged from v17 §G.

## H. SQL + persisted JSON (Odoo 16)

- Index types in 16: `index='btree'` (or `True`), `index='btree_not_null'`,
  `index='trigram'` (verified: Odoo 16 ORM fields reference). Missing
  index on a hot WHERE/ORDER BY → MEDIUM. Same set as v17.
- **Translated fields are stored as JSONB in 16** (verified: odoo/odoo
  #97692, #101115 — landed for 16.0; `ir.translation` no longer holds
  field translations). A 16 module that still reads/writes
  `ir.translation` rows for model field translations → MEDIUM (wrong
  storage model). This migration is NEW in 16 vs 15.
- **`fields.Json` IS exposed as a public author-facing field type in 16.0**
  — `class Json(Field)` with `type = 'json'`,
  `column_type = ('jsonb', 'jsonb')` (verified: odoo/odoo 16.0
  `odoo/fields.py` line 3207). It is marked *"still in beta"* in 16.0, with
  searching, indexing and in-place value mutation explicitly NOT
  implemented (per the class docstring). So the v17 "Json field type
  introduced in 17" claim is WRONG for 16 — do NOT flag a `fields.Json`
  declaration in a 16 module as "17-only". Treat it instead as a
  beta-storage field: reliance on `search()`/`index=`/in-place mutation
  over a `fields.Json` column (all unimplemented on 16) → MEDIUM.

## Severity anchors (Odoo-16)

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | Override `create()` with `@api.model` instead of `@api.model_create_multi(vals_list)` |
| BLOCKER  | Compute method calls `search()` inside `for record in self` loop → N+1 |
| BLOCKER  | OWL component reads a payload key the backend stopped writing — UI silently blank |
| MEDIUM   | 16 view ships inline `invisible="<expr>"` (only works 17+) — condition silently ineffective |
| MEDIUM   | 16 view ships `<list>` instead of `<tree>` |
| MEDIUM   | Module reads `ir.translation` for field translations (JSONB-backed since 16) |
| MEDIUM   | Controller missing CSRF policy on a state-changing endpoint |
| LOW      | Flagging `name_get()` override as needing `_compute_display_name` (that is a 17 rule) |
| LOW      | OWL component uses `useService("rpc")` instead of `useService("orm")` |

## Live-verify recipes (Odoo 16 + realdata_test MCP)

```python
# Confirm @api.model_create_multi is in effect (signature accepts list)
type(env['<model>'].create).__name__

# Confirm name_get path (16 display label)
env['<model>'].browse(<id>).name_get()

# Determinism of an aggregation
sum(env['<model>'].search([(<domain>)]).mapped('<field>'))
# consistency_check_eval (runs=3); fingerprints must match.
```

Raw SQL (JSON/index suspicion) goes through `postgres.run_select`.

## Anti-patterns specific to Odoo-16 review

- Flagging `attrs="..."` / `states="..."` as "removed" — they are valid
  in 16; removal is 17.
- Flagging `<tree>` as "should be `<list>`" — the rename is 17.
- Flagging a `name_get()` override on 16.0 — correct there; the
  `_compute_display_name` form applies from saas-16.4 onward (removal 17.0).
- Flagging missing `@api.multi` — correctly absent (gone since 14).
- Re-running an audit without consulting `.codex/audit_findings_*_locked.md`.
