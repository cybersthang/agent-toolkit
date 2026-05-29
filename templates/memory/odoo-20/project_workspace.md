---
name: Workspace layout
description: {{PROJECT_NAME}} Odoo 20 workspace root, addon roots, stack and verification recipe.
type: project
metadata:
  type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: Odoo 20 (Python {{STACK_LANGUAGE_VERSION}}, OWL v2 frontend, PostgreSQL ≥ 14 / 16 preferred).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}` (3.11+, 3.12 standard).
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem. v20 is the cutting-edge release and the toolkit's rule coverage is **stub-extends-v19** — pinning the runtime contract here keeps the agent from silently regressing to pre-v17 idioms.

**How to apply:** Pre-v17 conventions DO NOT apply — methods are recordset-by-default (no `@api.multi`), views use Python-expression `invisible=` / `readonly=` (no `attrs=` / `states=`), `_compute_display_name` replaces `name_get`, `@api.model_create_multi` is mandatory on `create()` overrides. Frontend is OWL v2 (no jQuery / legacy widgets). Mail framework is v2 (carried from 19). For any non-trivial pattern, verify against the actually installed Odoo source via `codebase` MCP before assuming v19 carryover — installed source wins.
