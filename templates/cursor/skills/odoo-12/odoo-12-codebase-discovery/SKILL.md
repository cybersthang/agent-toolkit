---
name: odoo-12-codebase-discovery
description: Discover Odoo 12 modules, manifests, model inheritance and XML IDs through the codebase MCP without broad-reading files. Module-agnostic - works for every addon under the configured roots.
---

# Odoo 12 — Codebase Discovery (MCP-first)

Use this skill **before** opening files. Broad reads waste tokens and create stale assumptions.

## Routing

| Question                                | Tool                                  |
|-----------------------------------------|---------------------------------------|
| "Where do addons live?"                 | `codebase.workspace_status`    |
| "List modules under X"                  | `codebase.discover_modules`    |
| "What does this module depend on?"      | `codebase.module_dependencies` |
| "Read this module's manifest"           | `codebase.read_manifest`       |
| "Find model `_name` / `_inherit`"       | `codebase.find_inheritance_chain` |
| "Search XML ID across the workspace"    | `codebase.search_xml_ids`      |
| "Locate definition of `<symbol>`"       | `codebase.search_text`         |
| "List tests for this module"            | `codebase.list_test_targets`   |
| "Read a short slice of this file"       | `codebase.read_file_chunk`     |
| "Recurring project answer (X)"          | `codebase.lookup_canonical_decision` |

## Workflow

1. **Narrow first.** When the workspace has multiple addon roots, pass `root_hint` (e.g. `nakivo`).
2. **Discover then drill.** `discover_modules` -> pick one -> `read_manifest` -> `find_inheritance_chain`.
3. **Read by chunk.** `read_file_chunk` with start/end_line, never full files unless the file is small.
4. **Cite sources.** When summarising, return `path:line` so the user can click through.

## Anti-patterns

- Searching the full workspace with `search_text` and no `root_hint`.
- Calling `read_file_chunk` before `discover_modules` when you don't yet know which module owns a model.
- Re-deriving "where is X" answers from scratch when `lookup_canonical_decision` already covers it.
