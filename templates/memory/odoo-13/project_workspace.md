---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 13 workspace root, addon roots, stack and verification recipe.
type: project
metadata:
  type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 13 (Python {{STACK_LANGUAGE_VERSION}}, jQuery + QWeb frontend, PostgreSQL >= 10).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}`.
- CLI entry point: `odoo-bin` (not `odoo.py` like 12).
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem. Odoo 13 sits between two large API breaks (Python 2 drop in 13, OWL + decorator cleanup in 14), so the version label matters more than usual.

**How to apply:** Pre-13 conventions partially carry over (`attrs=`, `states=`, `mail.thread`), but post-13 patterns do **not** apply — no OWL, no recordset-only requirement yet (`@api.multi` is deprecated, not removed), no `_check_company_auto`. When verifying with `odoo-bin`, always pass `-d {{DEFAULT_DB}}` and `--stop-after-init` for the narrowest check.
