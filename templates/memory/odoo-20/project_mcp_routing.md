---
name: MCP routing
description: MCP servers wired into the workspace and their primary tools, with Odoo 20 routing notes.
type: project
metadata:
  type: project
---
The following MCP servers are configured for this workspace (see `.codex/config.toml.example`):

- `codebase` — module discovery (`discover_modules`, `read_manifest`, `module_dependencies`), model graph (`find_inheritance_chain`, `search_model_definitions`), text/XML search (`search_text`, `search_xml_ids`), file slicing (`read_file_chunk`), tests (`list_test_targets`), canonical answers (`list_canonical_decisions`, `lookup_canonical_decision`).
- `postgres` — read-only Postgres: `list_databases`, `list_schemas`, `describe_table`, `query_readonly`. Mutations are syntactically rejected.
- `realdata_test` — `run_smoke_test`, `run_registry_boot`, `run_module_test` (with explicit write guards), and read-only ORM eval: `eval_orm_expression`, `consistency_check_eval`, `compare_with_expected`. ORM eval rejects mutation tokens (=, write, create, unlink, commit, import, dunders).

**Why:** Routing the right question to the right server keeps answers reproducible and cheap. Odoo 20 is the most recent stable release and the toolkit's rule coverage is **stub-extends-v19** — the `codebase` MCP is the only reliable way to confirm whether a v19 pattern survives into v20.

**How to apply:**
- Always pick the right MCP before opening files with native tools.
- For real-data verification, prefer `consistency_check_eval` over a one-shot `eval_orm_expression` whenever the question is "is this deterministic?".
- Odoo 20 specifics: avoid `@api.multi` semantics — recordset is default; `@api.model_create_multi` is the create-override contract; `_compute_display_name` replaces `name_get`; views use Python-expression `invisible=` / `readonly=` (no `attrs=` / `states=`).
- **Before applying any non-trivial v19 pattern in v20 code, `codebase.search_text` for the symbol / decorator / widget / mail hook in the installed Odoo source.** If the installed tree disagrees, the installed source wins — capture the delta as an ADR.
