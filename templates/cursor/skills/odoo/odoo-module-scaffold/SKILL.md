---
name: odoo-module-scaffold
description: Scaffold a new Odoo module under any addon root, for any Odoo major version. Step 0 detects the project's Odoo version (or asks if ambiguous), then loads `references/odoo-<N>-scaffold.md` for version-specific manifest fields and code snippets. Module-agnostic — prefix and target path always come from the user, never hard-coded. Open this skill only when scaffolding a NEW module.
---

# Odoo — Scaffold Module (version-aware)

This skill ships the **shared scaffolding workflow**. Anything that
differs between Odoo versions (manifest fields, model decorators, view
syntax) lives in `references/odoo-<N>-scaffold.md` and is loaded after
Step 0.

## 0. Version detection (MANDATORY first step)

Same protocol as `odoo-code-review`:

1. **Project-base manifest first**: if scaffolding under an addon root
   that contains existing modules, read a sibling `__manifest__.py` via
   `codebase.read_manifest` and use its `version` field. Sibling
   convention is the source of truth.
2. **If no siblings** (empty addon root): ask the user which Odoo major.
3. **Mixed-version monorepo**: confirm which addon root → which version.
   Don't assume.

Then load `references/odoo-<detected>-scaffold.md`.

| Detected major | Reference |
|---|---|
| 12 | `references/odoo-12-scaffold.md` |
| 17 | `references/odoo-17-scaffold.md` |
| 18 | `references/odoo-18-scaffold.md` ← 17 |
| 19 | `references/odoo-19-scaffold.md` ← 18 ← 17 |
| 20 | `references/odoo-20-scaffold.md` ← 19 ← 18 ← 17 (pre-GA stub) |
| 21+ | fall back to 20 stub + flag MEDIUM, ask user |

## 1. Inputs to confirm before writing files

1. **Module name** (snake_case). Honour the local convention — discover
   the prefix used in the target addon root via
   `codebase.discover_modules` before picking a name.
2. **Addon root** (one of the entries in `agent-toolkit.config.json` →
   `addon_roots`). Ask if ambiguous — never assume.
3. **`depends`** list. Read existing siblings via
   `codebase.discover_modules` if unsure.
4. **Whether mail / chatter is needed** (drives manifest depends and
   form layout).

## 2. Shared minimum layout (all versions)

```
<root>/<module>/
  __manifest__.py
  __init__.py
  models/
    __init__.py
  views/
    *.xml
  security/
    ir.model.access.csv          # one line per new model
    security.xml                  # only if module-private groups
  static/src/                     # OWL components (15+ only — see reference)
```

## 3. Shared verification

1. `odoo-bin -u <module> --stop-after-init -d <db>` (or 12-era
   equivalent — see reference).
2. Confirm XML IDs are unique inside the module.
3. If the module touches existing models, run
   `codebase.find_inheritance_chain` to confirm there are no naming
   collisions across addon roots.

## 4. Version-specific scaffold

After Step 0, load `references/odoo-<detected>-scaffold.md` for:
- Correct `'version'` string format (e.g. `'12.0.1.0.0'` vs `'17.0.1.0.0'`).
- Whether `'license'` field is needed.
- Correct `create()` decorator + signature in the model template.
- Correct view syntax (conditional visibility).
- Whether `static/src/` (OWL) is applicable.

## Universal hard rules

- Never copy module names from a sibling without re-checking that the
  addon root matches.
- Never silently adopt a prefix (e.g. `<proj>_`, `oca_`, `web_`) —
  confirm with the user.
- Never inline data files referenced by a manifest before they exist on
  disk.
- Never scaffold a module without first reading at least one sibling
  manifest — version + license + dependency conventions all come from
  there.

## Sibling skills

- `odoo-codebase-discovery` — call FIRST to discover siblings + addon
  root contents.
- `odoo-code-patterns` — copy compute / wizard / view patterns matching
  the detected version.
- `odoo-code-review` — gate the scaffolded module before merge.
- `<stack>-deterministic-answers` — cite project conventions
  (`addon-roots`, `module-naming`, `license-default`) before re-deriving.
