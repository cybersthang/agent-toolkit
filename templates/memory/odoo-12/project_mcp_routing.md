---
name: MCP routing
description: Five MCP servers wired into the workspace and their primary tools.
type: project
---
Five MCP servers are configured for this workspace (see `.codex/config.toml.example`):

- `codebase` — module discovery (`discover_modules`, `read_manifest`, `module_dependencies`), model graph (`find_inheritance_chain`, `search_model_definitions`), text/XML search (`search_text`, `search_xml_ids`), file slicing (`read_file_chunk`), tests (`list_test_targets`), canonical answers (`list_canonical_decisions`, `lookup_canonical_decision`).
- `postgres` — read-only Postgres: `list_databases`, `list_schemas`, `describe_table`, `query_readonly`. Mutations are syntactically rejected.
- `realdata_test` — `run_smoke_test`, `run_registry_boot`, `run_module_test` (with explicit write guards), and read-only ORM eval: `eval_orm_expression`, `consistency_check_eval`, `compare_with_expected`. ORM eval rejects mutation tokens (=, write, create, unlink, commit, import, dunders).
- `jira_production` — live tickets. Tools: `env_status`, `get_issue`, `get_issue_raw`, `search_issues`, `list_projects`, `my_assigned_issues`. Base URL + credentials live ONLY in `.codex/mcp.local.env` under `{{ENV_PREFIX}}_JIRA_PRODUCTION_*` (call `env_status` to see the resolved URL).
- `jira_preproduction` — UAT / staging tickets. Same toolset; credentials map from `{{ENV_PREFIX}}_JIRA_PREPRODUCTION_*` in `.codex/mcp.local.env`.

**Why:** The user wanted explicit MCP coverage for: codebase scan, JIRA Production, JIRA Pre-Production, real-data algorithm verification. Routing rule lives at `.cursor/rules/mcp-routing.mdc`.

**How to apply:** Always pick the right MCP before opening files with native tools. For JIRA, name the profile in the answer to avoid mixing tickets across servers. For real-data verification, prefer `consistency_check_eval` over a one-shot `eval_orm_expression` whenever the question is "is this deterministic?".
