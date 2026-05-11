# Odoo 18 — Code Review Reference (Version-Specific Deltas)

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **18**. Combine with the shared dimensions in the parent SKILL.md
and the cross-version checklists under `_common/code-review/references/`.

Odoo 18 was released in **October 2024**. The shape is closer to 17 than to
12: recordset-default ORM, `@api.model_create_multi`, OWL frontend, no
`attrs/states`. The 18-specific deltas are mostly ORM API renames and
removals.

## A. ORM / API decorators (Odoo 18)

Same as 17:
- `@api.multi` is **removed**. Importing it → ImportError.
- Methods are **recordset by default**.
- `@api.model_create_multi(vals_list)` is **required** for `create()` overrides.
- `@api.depends`, `@api.constrains`, `@api.onchange`, `@api.depends_context` unchanged.
- `ensure_one()` whenever a method assumes a single record.

## B. ORM API renames + removals (NEW in 18 — most common 17→18 break)

### Renamed

| Old (v17 or earlier) | New (v18+) | Impact |
|----------------------|------------|--------|
| `search(args=...)` / `search_count(args=...)` / `_search(args=...)` | `search(domain=...)` / `search_count(domain=...)` / `_search(domain=...)` | Calls using `args=` keyword raise TypeError. Positional calls still work. |
| `group_operator='sum'` on Field declaration | `aggregator='sum'` | Field declarations with `group_operator=` will warn / fail. |
| `name_get()` model override | `_compute_display_name()` + read `display_name` | `name_get()` is **deprecated** (since 16.4). Still works in 18 but flag as MEDIUM cleanup. |

### Removed

| Symbol | Version removed | Alternative |
|--------|-----------------|-------------|
| `inselect` operator (internal) | 17.4 | Use `in` with a `Query` or `SQL` object. |
| `_flush_search()` method | 17.1 | Automatic field flushing handled by `execute_query()`. |
| `_mapped_cache()` method | 18.0 | Use `mapped()` directly. |
| `limit` attribute on `One2many` / `Many2many` field | 18.0 | Apply limit at the search level instead. |
| `_sequence` Model attribute | 18.0 | Odoo lets PostgreSQL use the default sequence of the primary key. |
| `fields_get_keys()` on Model | deprecated | Use `_fields.keys()` or `fields_get().keys()`. |
| `get_xml_id()` on Model | deprecated | Use `_BaseModel.get_external_id()`. |

### Added (use these in new 18+ code)

| Symbol | Purpose |
|--------|---------|
| `SQL` wrapper object (`from odoo.tools import SQL`) | Safe SQL composition. Prevents injection. Replaces manual `%s` formatting in raw SQL. |
| `check_access(operation)` on recordset | Combines access rights + record rules check. Use over manual `check_access_rights` + `check_access_rule`. |
| `has_access(operation)` on recordset | Boolean version of `check_access`. |
| `_filtered_access(operation)` on recordset | Returns the subset the user can access. |
| `_search_display_name()` | Name searching now consistent with other fields. |
| `Environment.translation` accessor | Translations now accessible from `Environment`. |

### Severity calibration (NEW in 18)

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | Call uses `search(args=domain)` with keyword `args=` → TypeError on every call in 18 |
| BLOCKER  | Code imports / uses `inselect` operator → AttributeError, no fallback |
| BLOCKER  | Field declares `limit=10` on `One2many('child.model', 'parent_id', limit=10)` → install raises |
| MEDIUM   | Model overrides `name_get()` instead of `_compute_display_name()` — works but deprecated, plan migration |
| MEDIUM   | Field declares `group_operator='sum'` instead of `aggregator='sum'` — works with warning, fix during cleanup |
| MEDIUM   | Raw SQL with manual `%s` formatting instead of `SQL` wrapper — works but no injection protection |
| LOW      | Code calls `check_access_rights` + `check_access_rule` separately instead of `check_access()` — style only |
| LOW      | Uses `fields_get_keys()` instead of `_fields.keys()` — works, deprecated |

## C. Views (Odoo 18 syntax)

Same as 17:
- `attrs="{...}"` and `states="..."` are **removed**. Use `invisible="<expr>"`, `readonly="<expr>"`, `required="<expr>"` directly with Python expressions.
- `<xpath expr position="after|before|inside|replace|attributes">` for inheritance.
- XML IDs stable across releases.

New in 18:
- `<list>` is the preferred tag over `<tree>` (both still work — `<tree>` will be removed in a future version). Flag LOW if new views use `<tree>`.

## D. Frontend (OWL — refinements in 18)

- OWL 2 is the framework (introduced in 17, refined in 18).
- Same component patterns: `static template = "<module>.<Name>"`, `setup()`, `useService(...)`.
- New: `useChildSubEnv()` for nested OWL trees.
- Same: no jQuery; `t-esc` over `t-raw`.
- Asset bundles: same registration via `__manifest__.py` `'assets'` key (replaces old `assets.xml` template inheritance in 18, though template inheritance still works for backwards compat — flag LOW for new files using the old style).

## E. Security / multi-company (Odoo 18 nuances)

- `check_access(operation)` is the preferred call — replaces manual `check_access_rights(operation)` + `check_access_rule(operation)`.
- `has_access(operation)` to check without raising.
- `_filtered_access(operation)` to filter a recordset down to allowed records.
- CSRF policy unchanged: JSON-RPC `csrf=False` convention, HTTP form `csrf=True`.
- New: `mail.thread` mixin tracking changes; verify message_post calls aren't broken.

## F. Monkey-patches / install-uninstall symmetry (Odoo 18)

- Patches via `setattr` still work; uninstall path must restore originals.
- New: dynamic field declaration patterns supported — but flag any addon that uses runtime `add_field` on installed models; uninstall must `remove_field`.

## G. Manifest hygiene (Odoo 18)

- `version`: `18.0.<major>.<minor>.<patch>`.
- `data` order: `security/` → `data/` → `views/` → menus (unchanged).
- `depends` lists exactly what the module imports / inherits.
- `installable: True`; `application` only for top-level apps.
- New: `'assets': {...}` in manifest is the **preferred** way to declare frontend assets, replacing template-inheritance-of-assets-bundle in 17.
- `license`: matches project default.

## H. SQL + persisted JSON (Odoo 18)

- Use the new `SQL` wrapper for safe SQL composition:
  ```python
  from odoo.tools import SQL
  query = SQL("SELECT id FROM %s WHERE name = %s", SQL.identifier(self._table), 'Acme')
  self.env.cr.execute(query)
  ```
- Manual `%s` formatting in `execute()` still works but is now MEDIUM ("missed `SQL` wrapper opportunity").
- `Json` field type (introduced in 17, refined in 18): native PostgreSQL JSON.

## Severity anchors (Odoo-18-specific)

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | `search(args=[...])` with keyword `args=` → TypeError |
| BLOCKER  | Uses `inselect` operator → AttributeError |
| BLOCKER  | `One2many` / `Many2many` field declares `limit=` → install raises |
| BLOCKER  | Model declares `_sequence = '...'` — attribute removed in 18 |
| MEDIUM   | Overrides `name_get()` instead of `_compute_display_name()` |
| MEDIUM   | Field uses `group_operator=` instead of `aggregator=` |
| MEDIUM   | Raw SQL `execute(f"... {value} ...")` instead of `SQL` wrapper |
| MEDIUM   | Manual `check_access_rights` + `check_access_rule` instead of unified `check_access()` |
| LOW      | New view file uses `<tree>` instead of `<list>` |
| LOW      | New asset declared via template inheritance instead of `__manifest__.py` `'assets'` |
| LOW      | Uses `fields_get_keys()` / `_mapped_cache()` (latter is removed but if codebase ships polyfill) |

## Live-verify recipes (Odoo 18 + realdata_test MCP)

```python
# Confirm `check_access` is in effect (18+ method exists)
hasattr(env['<model>'], 'check_access')

# Detect name_get overrides that should migrate to _compute_display_name
hasattr(type(env['<model>']), 'name_get') and 'display_name' not in type(env['<model>']).__dict__

# Drift between Python default and DB-stored values
env['<model>'].search_count([('<field>', '=', <python_default>)])

# Determinism of an aggregation
sum(env['<model>'].search([(<domain>)]).mapped('<field>'))
```

## Anti-patterns specific to Odoo-18 review

- Flagging `<tree>` as a bug in 18 — it works, just LOW (prefer `<list>` for new files).
- Flagging `group_operator=` as syntax error — it warns, still works, MEDIUM cleanup.
- Suggesting `inselect` "for compatibility" — removed since 17.4.
- Applying v17 raw SQL patterns without `SQL` wrapper — works but misses injection protection.
- Assuming `_sequence` Model attribute still exists — removed in 18.

## Migration notes (17 → 18)

When reviewing code that's mid-migration from 17 to 18:
- Grep for `args=` keyword in `search`/`search_count`/`_search` calls → replace with `domain=` or positional.
- Grep for `group_operator=` in field declarations → rename to `aggregator=`.
- Grep for `name_get` overrides → migrate to `_compute_display_name`.
- Grep for `inselect` and `_mapped_cache` and `_flush_search` → remove / replace.
- Grep for `limit=` on `One2many` / `Many2many` declarations → drop or move limit to caller.
- Grep for `_sequence` Model attribute → remove.
