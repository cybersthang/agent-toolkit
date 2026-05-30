---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 15 workspace root, addon roots, stack and verification recipe.
type: project
metadata:
  type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 15 (Python {{STACK_LANGUAGE_VERSION}} ≥ 3.7, OWL v1 + legacy QWeb/jQuery, PostgreSQL 12 recommended).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}`.
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem. 15 sits on a fault line — recordset-by-default (like 17) but `attrs` / `states` still legal (like 14), and the web client is a mix of OWL and QWeb/jQuery.

**How to apply:** Pre-14 conventions DO NOT apply — methods are recordset by default, no `@api.multi`, `@api.model_create_multi` for create overrides. `attrs="{...}"` / `states="..."` views ARE still valid in 15; do not migrate them to 17-style `invisible="<expr>"` unless explicitly asked. OWL is the default for **new** components; legacy QWeb/jQuery widgets keep working — do not rewrite wholesale. Before deleting any kanban widget, audit dependants: the legacy kanban JS framework is still present in 15 (it was removed in 17) and silent removals break consumers.
