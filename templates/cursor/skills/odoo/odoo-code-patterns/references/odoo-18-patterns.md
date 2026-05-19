# Odoo 18 — pattern deltas (cascade from 17)

Load this **on top of** `odoo-17-patterns.md`. Only override what
differs in 18.

## ORM signature renames

- `search(args=...)` → `search(domain=...)`. The positional form
  `search([('a','=','b')])` still works; only the keyword renamed.
- `read_group(...)` aggregator keyword: `group_operator='sum'` →
  `aggregator='sum'` on field declarations.
- `check_access_rights()` + `check_access_rule()` → unified
  `check_access(operation)`.

## SQL wrapper

```python
from odoo.tools import SQL
domain = SQL("EXTRACT(year FROM %s) = %s", field, year)
```

Use `SQL` instead of raw string concatenation for parameterized SQL in
ORM contexts (search domains, `_query_get`).

## View tag — `<list>` preferred over `<tree>`

`<tree>` still works but `<list>` is the preferred form in 18+. Treat
both as legal; do NOT auto-rewrite existing `<tree>` to `<list>` without
explicit user ask.

## `name_get` deprecated

`name_get()` overrides still execute in 18 but produce a deprecation
warning. Prefer `_compute_display_name()`.

## Removed in 18 (don't introduce, refactor if present)

- `inselect` (private API helper).
- `_mapped_cache` (private cache helper).
- `_sequence` field attribute — use `order` on the model instead.

## Hard rules (Odoo 18 deltas)

- New code uses `search(domain=...)` keyword.
- New field declarations use `aggregator='sum'` not `group_operator=`.
- Access checks use the unified `check_access('write')` call.
- Prefer `<list>` for new views; keep `<tree>` if extending existing view.
- Use `_compute_display_name()` for new models needing display logic.
