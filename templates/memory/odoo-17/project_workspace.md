---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 17 workspace root, addon roots, stack and verification recipe.
type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 17 (Python {{STACK_LANGUAGE_VERSION}}, OWL frontend, PostgreSQL).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}`.
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem.

**How to apply:** Pre-Odoo-17 conventions DO NOT apply here — methods are recordset by default, no `@api.multi`. Frontend is OWL, not QWeb+jQuery.
