---
name: MCP routing
description: MCP servers wired into the workspace and their primary tools.
type: project
metadata:
  type: project
---
The following MCP servers are configured for this workspace (see `.codex/config.toml.example`):

- `codebase` — module discovery (`discover_modules`, `read_manifest`, `module_dependencies`), model graph (`find_inheritance_chain`, `search_model_definitions`), text/XML search (`search_text`, `search_xml_ids`), file slicing (`read_file_chunk`), tests (`list_test_targets`), canonical answers (`list_canonical_decisions`, `lookup_canonical_decision`).
- `postgres` — read-only Postgres (>= 10 required by 14.0): `list_databases`, `list_schemas`, `describe_table`, `query_readonly`. Mutations are syntactically rejected.
- `realdata_test` — `run_smoke_test`, `run_registry_boot`, `run_module_test` (with explicit write guards), and read-only ORM eval: `eval_orm_expression`, `consistency_check_eval`, `compare_with_expected`. ORM eval rejects mutation tokens (=, write, create, unlink, commit, import, dunders).

**Why:** Routing the right question to the right server keeps answers reproducible and cheap. The rule lives at `.cursor/rules/mcp-routing.mdc` and is reinforced by `decision-consistency.mdc`.

**How to apply:**
- Always pick the right MCP before opening files with native tools.
- For real-data verification, prefer `consistency_check_eval` over a one-shot `eval_orm_expression` when the question is "is this deterministic?".
- Odoo 14 specifics:
  - Do not write expressions that rely on `@api.multi` semantics — recordset is the default; `@api.model_create_multi` is the create-override contract.
  - Accounting probes target `account.move` (with `move_type in ('out_invoice','in_invoice', ...)`) — `account.invoice` no longer exists in 14.
  - For frontend questions, first use `codebase.search_text` to determine whether the target widget is OWL v1 (`owl.Component` / `static/src/components/**`) or legacy AMD (`odoo.define(...)`), then probe the matching layer.
