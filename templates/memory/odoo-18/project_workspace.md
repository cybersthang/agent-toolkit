---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 18 workspace root, addon roots, stack and verification recipe.
type: project
metadata:
  type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 18 (Python {{STACK_LANGUAGE_VERSION}} — 3.10+; 3.12 supported, OWL frontend, PostgreSQL ≥ 12 / 14 preferred).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}`.
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem. Odoo 18 is mostly "v17 + refinements" — encoding the deltas here avoids the agent silently regressing to v12/v14 idioms.

**How to apply:** Pre-Odoo-17 conventions DO NOT apply here — methods are recordset by default, no `@api.multi`, no `name_get()` (use `_compute_display_name`), no `attrs=`/`states=` in views. Frontend is OWL (continued refactor from 17), not QWeb+jQuery. Use `@api.model_create_multi` for `create()` overrides and prefer `_check_company_auto = True` on company-scoped models.
