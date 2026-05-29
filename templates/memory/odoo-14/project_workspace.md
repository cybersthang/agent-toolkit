---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 14 workspace root, addon roots, stack and verification recipe.
type: project
metadata:
  type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 14 (Python {{STACK_LANGUAGE_VERSION}}, OWL v1 + jQuery/QWeb hybrid frontend, PostgreSQL >= 10).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}` (3.7+; 3.8 recommended).
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem. Odoo 14 is a transitional release whose conventions differ from 12 (`@api.multi` removed and `account.invoice` gone — both since 13, and unchanged in 14) and from 17 (`attrs`/`states` still valid, OWL is only partial).

**How to apply:** Pre-Odoo-14 conventions DO NOT apply for ORM decorators — recordset is the default; never reintroduce `@api.multi`. `@api.model_create_multi` is required on `create()` overrides. For the frontend, assume **nothing**: every UI patch starts with "is this OWL v1 or legacy jQuery/QWeb?" — the answer determines the file layout, imports, and template syntax. View XML still accepts `attrs="{...}"` and `states="..."`; do not migrate them away.
