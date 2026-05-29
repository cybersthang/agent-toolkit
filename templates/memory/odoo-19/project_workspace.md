---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 19 workspace root, addon roots, stack and verification recipe.
type: project
metadata:
  type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 19 (Python {{STACK_LANGUAGE_VERSION}}, OWL v2 frontend, PostgreSQL >= 14).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}` (3.11+ required).
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem. Odoo 19 is a recent release (~late 2025 / early 2026), so the agent must distinguish "v18 carries over" from "v19 changed it" — particularly around the mail framework.

**How to apply:**
- Pre-v14 conventions DO NOT apply: methods are recordset by default, no `@api.multi`.
- Pre-v17 view conventions DO NOT apply: no `attrs="{...}"` / `states="..."`; use `invisible/readonly/required="<py-expr>"`.
- Use `_compute_display_name`, not `name_get`. `@api.model_create_multi` for `create()` overrides.
- **Mail framework v2** is the one v18→v19 break: before editing any subclass of `mail.thread` or `mail.activity.mixin`, read the actual installed Odoo 19 source for the mixin — do not assume v18 internal field names, helper signatures, or follower handling still apply.
- Frontend is OWL v2, not QWeb+jQuery.
