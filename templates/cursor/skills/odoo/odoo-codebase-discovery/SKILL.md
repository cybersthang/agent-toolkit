---
name: odoo-codebase-discovery
description: Discover Odoo modules, manifests, model inheritance and XML IDs through the codebase MCP without broad-reading files. Works for any Odoo major version (12, 17, 18, 19, 20, future) — discovery tools are version-agnostic. Module-agnostic — works for every addon under the configured roots.
---

# Odoo — Codebase Discovery (MCP-first, version-agnostic)

Use this skill **before** opening files. Broad reads waste tokens and create stale assumptions. The MCP discovery surface (`codebase.discover_modules`, `read_manifest`, `find_inheritance_chain`, `search_xml_ids`, `lookup_canonical_decision`, …) is identical across Odoo versions, so this skill ships ONE body and does NOT need version detection.

> If you need version-specific *advice* (e.g. how to handle `@api.multi` vs recordset), open the matching sibling skill (`odoo-code-patterns`, `odoo-code-review`). Those skills do version detection at Step 0.

## Routing

| Question                                | Tool                                  |
|-----------------------------------------|---------------------------------------|
| "Where do addons live?"                 | `codebase.workspace_status`           |
| "List modules under X"                  | `codebase.discover_modules`           |
| "What does this module depend on?"      | `codebase.module_dependencies`        |
| "Read this module's manifest"           | `codebase.read_manifest`              |
| "Find model `_name` / `_inherit`"       | `codebase.find_inheritance_chain`     |
| "Search XML ID across the workspace"    | `codebase.search_xml_ids`             |
| "Locate definition of `<symbol>`"       | `codebase.search_text`                |
| "List tests for this module"            | `codebase.list_test_targets`          |
| "Read a short slice of this file"       | `codebase.read_file_chunk`            |
| "Recurring project answer (X)"          | `codebase.lookup_canonical_decision`  |

## Workflow

1. **Narrow first.** When the workspace has multiple addon roots, pass `root_hint` (the name of an addon root from `agent-toolkit.config.json` — e.g. `custom_addons`, the project's main addon dir, or a vendor folder). Never broad-search without it.
2. **Discover then drill.** `discover_modules` → pick one → `read_manifest` → `find_inheritance_chain`.
3. **Read by chunk.** `read_file_chunk` with start/end_line; never full files unless small (<200 lines).
4. **Cite sources.** When summarising, return `path:line` so the user can click through.

## Anti-patterns

- Searching the full workspace with `search_text` and no `root_hint`.
- Calling `read_file_chunk` before `discover_modules` when you don't yet know which module owns a model.
- Re-deriving "where is X" answers from scratch when `lookup_canonical_decision` already covers it.
- Reading every `__manifest__.py` to "see what's around" — that's what `discover_modules` returns in one call.
