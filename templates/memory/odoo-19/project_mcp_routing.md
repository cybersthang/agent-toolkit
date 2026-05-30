---
name: MCP routing
description: MCP servers wired into the Odoo 19 workspace and their primary tools.
type: project
metadata:
  type: project
---
The following MCP servers are configured for this workspace (see `.codex/config.toml.example`):

- `codebase` — module discovery (`discover_modules`, `read_manifest`, `module_dependencies`), model graph (`find_inheritance_chain`, `search_model_definitions`), text/XML search (`search_text`, `search_xml_ids`), file slicing (`read_file_chunk`), tests (`list_test_targets`), canonical answers (`list_canonical_decisions`, `lookup_canonical_decision`).
- `postgres` — read-only Postgres: `list_databases`, `list_schemas`, `describe_table`, `query_readonly`. Mutations are syntactically rejected.
- `realdata_test` — `run_smoke_test`, `run_registry_boot`, `run_module_test` (with explicit write guards), and read-only ORM eval: `eval_orm_expression`, `consistency_check_eval`, `compare_with_expected`. ORM eval rejects mutation tokens (=, write, create, unlink, commit, import, dunders).

**Why:** Routing the right question to the right server keeps answers reproducible and cheap. The rule lives at `.cursor/rules/mcp-routing.mdc` and is reinforced by `decision-consistency.mdc`. In Odoo 19, the `codebase` MCP is especially important for confirming the new mail-framework-v2 API on disk before editing.

**How to apply:**
- Always pick the right MCP before opening files with native tools.
- For real-data verification, prefer `consistency_check_eval` over a one-shot `eval_orm_expression` when the question is "is this deterministic?".
- Odoo 19 specifics:
  - Recordset is default; `@api.model_create_multi` is the create-override contract; `_compute_display_name` replaces `name_get`.
  - **Mail framework v2**: before editing any subclass of `mail.thread` / `mail.activity.mixin`, run `find_inheritance_chain({ model: "mail.thread" })` and `search_text` for `message_post` / follower-model usage to see how the installed v19 source actually shapes the API — v18 assumptions do not transfer.
  - For mail-related changes, prefer `run_module_test` over `eval_orm_expression` alone, since the v2 refactor affects runtime behavior the eval probe cannot fully exercise.
