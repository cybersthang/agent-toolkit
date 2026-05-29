---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 16 workspace root, addon roots, stack and verification recipe.
type: project
metadata:
  type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 16 (Python {{STACK_LANGUAGE_VERSION}} — 3.10+ required, OWL v2 frontend, PostgreSQL >= 12).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}`.
- CLI entry point: `{{PYTHON_BIN}} odoo-bin -d {{DEFAULT_DB}}` from `{{WORKSPACE_ROOT}}`.
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem. Odoo 16 is a pivot release — Python 3.10+, OWL v2 web client, mainstream `_check_company_auto`, and `flush_recordset()` / `flush_all()` as the formal cache-flush contract — so the wrong-version assumptions bite hard.

**How to apply:** Pre-16 conventions DO NOT apply here — methods are recordset by default (no `@api.multi`), and `create()` overrides MUST be `@api.model_create_multi`. Frontend is OWL v2 (class-based), not OWL v1 or QWeb+jQuery. View attribute conditions: prefer `invisible="…"` / `readonly="…"` / `required="…"` for new code (the 17-ready form, already valid in 16); leave existing `attrs="{...}"` / `states="…"` alone unless explicitly migrating. For new company-scoped models, set `_check_company_auto = True` and `check_company=True` on relations.
