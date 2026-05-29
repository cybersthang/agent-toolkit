---
name: MCP routing
description: MCP servers wired into the Odoo 13 workspace and their primary tools.
type: project
metadata:
  type: project
---
The following MCP servers are configured for this workspace (see `.codex/config.toml.example`):

- `codebase` — module discovery (`discover_modules`, `read_manifest`, `module_dependencies`), model graph (`find_inheritance_chain`, `search_model_definitions`), text/XML search (`search_text`, `search_xml_ids`), file slicing (`read_file_chunk`), tests (`list_test_targets`), canonical answers (`list_canonical_decisions`, `lookup_canonical_decision`).
- `postgres` — read-only Postgres: `list_databases`, `list_schemas`, `describe_table`, `query_readonly`. Mutations are syntactically rejected.
- `realdata_test` — `run_smoke_test`, `run_registry_boot`, `run_module_test` (with explicit write guards), and read-only ORM eval: `eval_orm_expression`, `consistency_check_eval`, `compare_with_expected`. ORM eval rejects mutation tokens (=, write, create, unlink, commit, import, dunders).

**Why:** Routing the right question to the right server keeps answers reproducible and cheap. The rule lives at `.cursor/rules/mcp-routing.mdc` and is reinforced by `decision-consistency.mdc`.

**How to apply:**
- Always pick the right MCP before opening files with native tools.
- For real-data verification, prefer `consistency_check_eval` over a one-shot `eval_orm_expression` whenever the question is "is this deterministic?".
- Odoo 13 specifics: ORM expressions may still call `@api.multi`-decorated methods (decorator is deprecated, not removed) — both decorated and bare recordset methods work. Do **not** assume `@api.model_create_multi` is the only valid create override path on third-party 13 modules; many still ship a single-record `create()`. When verifying batch behaviour, eval against an explicit list of vals dicts.
- Accounting: `account.invoice` and `account.move` coexist in 13 — `describe_table` both before writing migration queries.
