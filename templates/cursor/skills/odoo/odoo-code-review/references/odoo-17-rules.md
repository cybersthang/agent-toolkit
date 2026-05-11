# Odoo 17 — Code Review Reference (Version-Specific Deltas)

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **17** (or 16 with caveat, or 18+ with caveat). Combine with the
shared dimensions in the parent SKILL.md and the cross-version checklists
under `_common/code-review/references/`.

## A. ORM / API decorators (Odoo 17 — different from 12/13/14)

- `@api.multi` is **removed** in 17. Importing `from odoo.api import multi` will fail. Decorating a method with `@api.multi` is import-time error in 17.
- Methods are **recordset by default** — `for record in self:` is the canonical loop, no decorator needed.
- `@api.model` on class-level methods that don't need a recordset.
- **`@api.model_create_multi(vals_list)` is required** to override `create()`. A single-record `@api.model create(self, vals)` override **silently breaks batch creates** in 17 — the base class calls the override per-record one at a time, losing batch semantics.
- `@api.depends`, `@api.constrains`, `@api.onchange`, `@api.depends_context` as in earlier versions.
- `ensure_one()` whenever a method assumes a single record.

### Severity calibration

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | Override `create()` declared with `@api.model` instead of `@api.model_create_multi(vals_list)` → batch creates silently apply only to the first record |
| BLOCKER  | `from odoo.api import multi` import → ImportError, blocks module load |
| BLOCKER  | `@api.multi` decorator on a method → import-time AttributeError |
| MEDIUM   | `@api.depends` missing a field that the compute reads → stale cached values |
| LOW      | Extra `@api.model` on a method that operates on a recordset — works but is style noise |

## B. Loops + N+1 (Odoo 17 specifics)

- No `search()` / `browse(id)` inside Python loops.
- `search_count()` over `len(search())`.
- Computed fields with `store=False` referenced repeatedly in a loop — flag as Medium perf.
- Compute method calls `search()` inside `for record in self` loop → N+1 explosion, often BLOCKER on large recordsets.

## C. Views (Odoo 17 syntax — DIFFERENT from 12)

- `attrs="{...}"` and `states="..."` are **removed** in 17. Any new file shipping them: MEDIUM (install raises ValidationError, blocks upgrade) — escalate to BLOCKER if the file is in scope of an active deploy.
- Use `invisible="<py expr>"`, `readonly="<py expr>"`, `required="<py expr>"` directly with Python expressions on `<field>`:
  ```xml
  <field name="custom_field" invisible="state == 'done'"/>
  ```
- Inheritance: `<xpath expr position="after|before|inside|replace|attributes">`.
- XML IDs stable across releases — rename without migration = LOW.
- View arch validates field references at install time — flag any view that references a field the model doesn't declare.

## D. Frontend (OWL — no jQuery in 17)

- New jQuery selectors → MEDIUM (legacy debt) or BLOCKER if they target a node the OWL render no longer produces (UI silently broken).
- OWL components: `static template = "<module>.<Name>"`, `setup()` calls `useService("orm" | "notification" | "action" | "user")`.
- Templates use OWL XML with `t-*` directives — legacy 12.x widget classes are gone.
- `/** @odoo-module **/` header required at the top of every `.js` file in `static/src/`.
- `registry.category("actions").add("<name>", <Component>)` to wire components.
- `useService("rpc")` exists but `useService("orm")` is preferred for ORM ops (`searchRead`, `read`, `write`, `unlink`).

## E. Security / multi-company (Odoo 17 nuances)

- Every new `models.Model` has at least one `ir.model.access.csv` row.
- Multi-company models inherit `mail.thread` only when chatter is needed — otherwise it bloats tables.
- Record rules align with the parent's `_inherit` chain — verify before adding new ones.
- CSRF policy unchanged from 12: `type='json'` conventionally `csrf=False`, `type='http'` with state change MUST stay `csrf=True`.
- `_check_company` is more strict in 17 — verify it's invoked before write on cross-company records.

## F. Monkey-patches / install-uninstall symmetry (Odoo 17)

- Registry hooks: `_register_hook` paired with a teardown path so uninstall restores originals.
- Patching base classes in 17 still goes through `setattr` — but verify the addon doesn't rely on import-order side effects.

## G. Manifest hygiene (Odoo 17)

- `version`: `17.0.<major>.<minor>.<patch>` — flag if different shape.
- `data` order: `security/` → `data/` → `views/` → menus.
- `depends` lists exactly what the module imports / inherits.
- `license`: matches project default (`LGPL-3` or `OEEL-1` for Enterprise modules).
- `installable: True`; `application` only when the module is a top-level app.

## H. SQL + persisted JSON (Odoo 17)

- ILIKE on `additional_info`-style columns that may contain compressed blobs → MEDIUM, doesn't match inner JSON.
- Indexes: missing index for hot WHERE / ORDER BY → MEDIUM perf.
- JSON path through gzip wrappers → BLOCKER if it returns wrong rows.
- `Json` field type (introduced in 17): native PostgreSQL JSON, no manual `loads`/`dumps` — flag legacy `Text` fields holding JSON that should migrate.

## Severity anchors (Odoo-17)

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | Override `create()` declared with `@api.model` instead of `@api.model_create_multi(vals_list)` → batch creates silently apply only to the first record |
| BLOCKER  | Compute method calls `search()` inside the `for record in self` loop → N+1 that explodes on a large recordset |
| BLOCKER  | OWL component reads a payload key the backend stopped writing — UI silently shows blanks |
| BLOCKER  | View ships `attrs="{...}"` or `states="…"` (removed in 17) — install raises ValidationError on upgrade |
| MEDIUM   | Controller missing CSRF policy on a state-changing endpoint |
| MEDIUM   | `json.dumps(payload)` without `ensure_ascii=False` — non-ASCII identifiers mangled |
| MEDIUM   | Default value drift: Python field default ≠ XML data record default |
| MEDIUM   | Memory dict that only grows (no prune in a cron / on `_unregister_hook`) |
| MEDIUM   | New jQuery selector introduced in 17 codebase (legacy debt) |
| LOW      | Hard-coded `base.user_admin` in `security.xml` |
| LOW      | OWL component uses `useService("rpc")` instead of `useService("orm")` |
| LOW      | Capped list `[:1000]` with no `truncated` flag |

## Live-verify recipes (Odoo 17 + realdata_test MCP)

```python
# Confirm `@api.model_create_multi` is in effect (signature accepts list)
type(env['<model>'].create).__name__  # check decorator

# Drift between Python default and DB-stored values
env['<model>'].search_count([('<field>', '=', <python_default>)])

# Determinism of an aggregation
sum(env['<model>'].search([(<domain>)]).mapped('<field>'))
# consistency_check_eval (runs=3); fingerprints must match.

# OWL consumer / backend producer cross-check
env['<model>'].search([], limit=10).mapped(lambda r: r._read_format(['field_a', 'field_b']))
```

Raw SQL (when JSON / index suspicion) goes through `postgres.run_select` —
`realdata_test` accepts only single ORM expressions.

## Anti-patterns specific to Odoo-17 review

- Flagging missing `@api.multi` — it is correctly absent in 17.
- Suggesting `attrs="..."` / `states="..."` "for backwards compatibility" — they are removed.
- Treating OWL like QWeb-only or jQuery-based — different runtimes.
- Applying 12-style single-record `create(self, vals)` override — that silently breaks batch creates in 17.
- Re-running an audit without consulting `.codex/audit_findings_*_locked.md` first — that is how counts drift across sessions.
