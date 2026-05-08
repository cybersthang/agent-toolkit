---
name: Workspace layout
description: {{PROJECT_NAME}} {{STACK_LABEL}} workspace root, addon roots, stack and verification recipe.
type: project
---
- Root: `{{WORKSPACE_ROOT}}`.
- Stack: {{STACK_LABEL}} ({{STACK_LANGUAGE}} {{STACK_LANGUAGE_VERSION}}, PostgreSQL).
- Database (default): `{{DEFAULT_DB}}`.
- Python: `{{PYTHON_BIN}}`.
- Addon roots:
{{ADDON_ROOTS}}

**Why:** These facts come up in nearly every task; storing them lets answers stay consistent without re-deriving them from the filesystem.

**How to apply:** When a question depends on these facts, prefer this memory. When the answer is mission-critical (e.g. before running a destructive command), still verify against `.cursor/rules/` and `AGENTS.md` to catch drift.
