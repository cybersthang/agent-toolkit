---
name: odoo-codebase-discovery
description: Map an UNFAMILIAR Odoo codebase BEFORE editing — discover addon roots, build the module dependency graph, trace a model's _inherit/_inherits chain, find which modules a feature touches, inventory views/controllers. MCP-first (the `codebase` server); no broad file reads. Version-agnostic — the discovery tools are identical across Odoo 12/17/18/19/20/future, so this skill ships ONE body and needs no version detection. Open whenever you are about to change a model/view/controller in a codebase you have not mapped yet, or when the user asks "where does X live", "what depends on this", "what's the inheritance chain of <model>".
---

# Odoo — Codebase Discovery (MCP-first, version-agnostic)

Use this skill **before** opening files and **before** editing anything.
Broad reads waste tokens and create stale assumptions; editing a model
whose inheritance chain you have not traced means you may override the
wrong layer (see Anti-patterns). The MCP discovery surface is identical
across Odoo versions, so this skill ships ONE body and does NOT detect
version. For version-specific *advice* (e.g. `@api.multi` vs recordset)
open `odoo-code-review` / `odoo-debug-troubleshoot` — those detect version
at their Step 0.

## 0. The MCP surface (verified tool names)

MCP server key is `codebase` (registered in `.cursor/mcp.json` / `.mcp.json`;
the server's internal name is `{{PROJECT_NAME_SLUG}}_codebase`). Tool names
below are **verified against `templates/codex/mcp_servers/codebase_server.py`** —
do not invent others.

| Tool | Required args | Returns |
|------|---------------|---------|
| `workspace_status` | — | `workspace_root` + `addon_roots[]` |
| `discover_modules` | (opt) `root_hint`, `name_contains`, `limit` | `modules[]` = `{module, path, manifest_path}` |
| `read_manifest` | `module_path` | parsed `manifest` dict (name/version/depends/data/…) |
| `module_dependencies` | `module` | `direct_dependencies[]`, `data_files[]`, `demo_files[]`, `version`, `category`, `auto_install` |
| `find_inheritance_chain` | `model` | `declarations[]` = `{path, line, role:"_name"|"_inherit", models[]}` |
| `search_model_definitions` | (opt) `model` | `_name`/`_inherit`/`_inherits` declaration lines (broader than `find_inheritance_chain`) |
| `search_xml_ids` | `xml_id` | matches in `*.xml/*.csv/*.yml/*.yaml` |
| `search_text` | `pattern` | line matches (path:line:text) |
| `list_test_targets` | `module_path` | `test_files[]` + `suggested_test_tag` |
| `read_file_chunk` | `path` | a line slice (≤250 lines) |
| `lookup_canonical_decision` | `topic` | the registered answer for a recurring "where/how is X" question |
| `list_canonical_decisions` | (opt) `topic_contains` | full registry listing |

**Honest gaps — tools that do NOT exist (so plan around them):**
- There is **no single "dependency graph" tool**. You build the graph by
  recursing `module_dependencies` yourself (recipe B below).
- There is **no AST/semantic index** — `find_inheritance_chain` and
  `search_model_definitions` are regex/line scans over `.py`. A model
  built dynamically (`type(name, (models.Model,), {...})`) or with the
  `_name`/`_inherit` on a non-literal won't be found; fall back to
  `search_text`.
- There is **no "list controllers" or "list views" tool**. Inventory them
  with `search_text` on the right pattern + `glob` (recipe D).
- `read_file_chunk` caps at **250 lines** per call; page through large files.

## 1. Workflow (discover → drill → cite)

1. **Orient.** `workspace_status` → learn `workspace_root` and the
   `addon_roots[]`. Every later call that supports `root_hint` should pass
   one of these roots to avoid scanning the whole tree.
2. **Discover then drill.** `discover_modules({root_hint})` → pick the
   module → `read_manifest` / `module_dependencies` → `find_inheritance_chain`
   for the target model → `read_file_chunk` only the relevant slice.
3. **Narrow first.** When there are multiple addon roots, ALWAYS pass
   `root_hint`. A bare `search_text` over the full workspace is the #1
   token sink and the #1 source of false matches (vendor/OCA copies).
4. **Read by chunk.** Use `read_file_chunk` with `start_line`/`end_line`;
   never read a full file unless it is small (<200 lines).
5. **Check the registry before re-deriving.** `lookup_canonical_decision({topic})`
   for recurring "where is X / how do we do X" answers — prefer the
   registered answer over re-mapping from scratch.
6. **Cite sources.** When you summarise, return `path:line` so the user
   can click through.

## 2. Concrete recipes

### A. "Where do addons live, and what modules are here?"
```
workspace_status()                                  # → addon_roots[]
discover_modules({ root_hint: "<a root from above>" })
# scope to a feature area:
discover_modules({ root_hint: "custom_addons", name_contains: "sale" })
```

### B. "Which modules does <module> pull in?" — build the dependency graph
There is no graph tool; recurse `module_dependencies` breadth-first:
```
module_dependencies({ module: "my_feature" })       # → direct_dependencies[]
# then for each dep not yet seen, repeat:
module_dependencies({ module: "<dep>" })
# stop when you hit base/web/known stdlib modules or a fixed depth (2–3 is
# usually enough to answer "what could my change break").
```
Use `read_manifest({module_path})` if you also need `data`/`demo` file
order (load order = override order; matters for views & security).

### C. "What's the inheritance chain of model `<x.y>`?" (DO THIS BEFORE EDITING)
```
find_inheritance_chain({ model: "sale.order", root_hint: "custom_addons" })
```
The result lists every file that declares `_name` or `_inherit` for that
model, with `role` and `line`. Read it as the override stack:
- `role:"_name"` → the layer that **defines** the model.
- `role:"_inherit"` → each layer that **extends** it. The module load
  order (from manifests / addons path) decides which override wins.
- If a field/method exists in several layers, open each with
  `read_file_chunk` to see which one actually owns the behaviour you're
  about to change. Edit the layer that owns it — not the base, not a
  sibling extension.
For `_inherits` (delegation/composition) the regex in
`find_inheritance_chain` keys off `_name`/`_inherit`; confirm delegation
with `search_model_definitions({ model: "x.y" })` which also surfaces
`_inherits` lines, then `search_text({ pattern: "_inherits" , root_hint })`.

### D. "Which modules / files does feature <F> touch?" — inventory
No view/controller tool exists; pattern-scan with `glob`:
```
# Controllers (HTTP routes):
search_text({ pattern: "@http.route",  glob: "*.py",  root_hint: "custom_addons" })
# View records:
search_text({ pattern: "<record",      glob: "*.xml", root_hint: "custom_addons" })
# A specific XML id referenced across data/views/security:
search_xml_ids({ xml_id: "view_my_feature_form" })
# The model touched by the feature:
search_model_definitions({ model: "my.feature", root_hint: "custom_addons" })
```
Cross-reference the matching `path`s back to modules via
`discover_modules` to get the "feature spans modules A, B, C" answer.

### E. "Is this model tested? Where?"
```
list_test_targets({ module_path: "custom_addons/my_feature" })
# → test_files[] + suggested_test_tag (e.g. "/my_feature")
```

## 3. Anti-patterns

- **Editing a model without tracing its inheritance chain first.** You
  override `action_confirm` on the base `_name` layer, but a downstream
  module already `_inherit`s and `super()`-chains it — your change lands
  in the wrong layer and is silently shadowed (or shadows the wrong one).
  ALWAYS run `find_inheritance_chain` and read each layer before editing.
- **Bare `search_text` over the whole workspace** (no `root_hint`, no
  `glob`). Returns vendor/OCA/`.venv` copies and burns tokens. Scope it.
- **Reading every `__manifest__.py` "to see what's around."** That is
  exactly what `discover_modules` returns in one call.
- **Calling `read_file_chunk` before you know which module owns a model.**
  Discover first; you'll usually open a different file than you guessed.
- **Assuming `find_inheritance_chain` is exhaustive.** It is a regex scan;
  dynamically-built or non-literal `_name`/`_inherit` won't appear — fall
  back to `search_text`.
- **Treating manifest `depends` order as override order.** Override order
  is module *load* order; `data` file order within a manifest decides
  XML/view/security record precedence. Read both when it matters.
- **Re-deriving "where is X" from scratch** when
  `lookup_canonical_decision({topic})` already has the registered answer.

## Sibling skills

- `odoo-code-review` — audit a module once you've mapped it (detects version).
- `odoo-debug-troubleshoot` — fix a failing model/view/cron (detects version).
- `odoo-data-verification` — probe the real DB for stored-value correctness.
- `odoo-jira-workflow` — pull the ticket/intent that motivates the change.
