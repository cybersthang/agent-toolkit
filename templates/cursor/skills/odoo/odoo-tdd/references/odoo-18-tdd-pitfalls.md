# Odoo 18 — TDD pitfalls (cascade from 17)

| Pitfall | Detection | Fix |
|---|---|---|
| `search(args=...)` in test fails | API rename | Use `search(domain=...)` keyword (positional `search([(...)])` still works) |
| `read_group` test asserts on aggregator field name | `group_operator` renamed → `aggregator` on field decl | Update field declaration + test expectations |
| `name_get()` mock no-op | Deprecated; some code paths bypass it | Mock / override `_compute_display_name()` instead |
| `check_access_rights` test branch never hit | Unified into `check_access('operation')` | Update mock to call unified API |
