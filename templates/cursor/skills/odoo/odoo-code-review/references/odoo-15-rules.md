# Odoo 15 — Code Review Reference (Version-Specific Deltas)

> odoo-15 reference (drafted v0.29). Deltas vs odoo-12 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **15**. Combine with the shared dimensions in the parent SKILL.md
and the cross-version checklists under `_common/code-review/references/`.

v15 is transitional: the **ORM decorator surface matches v17** but the
**view syntax matches v12**. Calibrate accordingly.

## A. ORM / API decorators (Odoo 15) — DELTA from v12

- `@api.multi` is **REMOVED** (since v13). Flagging its ABSENCE is wrong;
  flag its PRESENCE — leftover `@api.multi` in v15 code is dead/imported
  v12 code and will raise (`module odoo.api has no attribute 'multi'`).
  Web-verified: decorators removed in v13.
- `@api.one` likewise removed — flag any usage as BLOCKER (import error).
- `create()` override should be `@api.model_create_multi` taking
  `vals_list` (list). A single-record `@api.model create(self, vals)`
  override in v15 silently breaks batch inserts — flag MEDIUM/BLOCKER
  per blast radius. `@api.model_create_multi` exists since v12
  (web-verified: defined in 12.0 odoo/api.py).
- `@api.depends(...)` complete on every computed field — unchanged from
  v12 (see odoo-12-rules.md §A).
- `ensure_one()` whenever a method assumes a single record — unchanged.

### Severity calibration

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | `@api.multi` / `@api.one` present in v15 code → `AttributeError` on `odoo.api` at import |
| BLOCKER  | `create()` overridden single-record (`@api.model`, `vals`) on a model hit by batch import/`load()` → only first record processed |
| MEDIUM   | `@api.depends` missing a field the compute reads → stale cached values |
| LOW      | Mixed v12-style and v15-style override left in a migrated file (style/consistency) |

## B. Loops + N+1 (Odoo 15) — Unchanged from v12

`search()`/`browse(id)` in loops, `len(search())` → `search_count`,
unstored-compute-in-loop fan-out, unpaginated `t-foreach`. Unchanged from
v12 — see odoo-12-rules.md §B.

## C. Views (Odoo 15 syntax — SAME as v12, DIFFERENT from 17)

- `attrs="{'invisible': [('state','=','done')]}"` and
  `states="draft,confirmed"` are the **correct v15 idioms** — do NOT flag
  them as bugs. Removed only in v17 (web-verified). Same as v12.
- Direct `invisible="state == 'done'"` Python-expression syntax is v17+
  and does NOT work in v15 — flag if introduced.
- Other view flags (malformed `attrs`, `<xpath>` without `position=`,
  root-tag replacement, XML-ID stability) — unchanged from v12, see
  odoo-12-rules.md §C.

## D. Frontend (TRANSITIONAL — OWL + jQuery coexist in v15) — DELTA

- jQuery / `web.Widget.extend({...})` is **still legal** in v15 (legacy
  stack ships). Do NOT flag it as "OWL-era code wrongly used".
- OWL components ARE valid in v15 (the new layer). Flag, in OWL files:
  - Missing `/** @odoo-module **/` header — NEW in v15; without it the
    ES6-style `import` is not transpiled (web-verified, server-side
    transpiler). MEDIUM if the module relies on `import`/`export`.
  - Use of the `@odoo/owl` package import (`import { Component } from
    "@odoo/owl"`) — that is the OWL 2 / **v16+** form; in v15 OWL is the
    1.x era exposed on the global `owl`. Flag as wrong-version import.
  - OWL XML template missing the `owl="1"` attribute on its root node.
- QWeb `t-raw` XSS risk — unchanged from v12.
- Asset registration: see §G (manifest `assets` dict, NEW in v15).

## E. Security / multi-company (Odoo 15) — DELTA from v12

- ACL rows / `TransientModel`+`AbstractModel` exemption — unchanged from
  v12 (see odoo-12-rules.md §E).
- Multi-company `ir.rule` by `company_id` — the **API surface differs
  from v12**: v15 has `self.env.company` / `with_company()` /
  `_check_company_auto` (web-verified: `env.company` arrived v13,
  `with_company()` v14). Flag use of the v12-only `force_company` context
  key as outdated (it still works in v13–15 but `with_company()` is the
  idiom from v14). See odoo-15-multicompany.md.
- `sudo()` documented; CSRF rules for `type='json'`/`type='http'` —
  unchanged from v12 (see odoo-12-rules.md §E).

## F. Monkey-patches / install-uninstall symmetry — Unchanged from v12

`_register_hook`, `_post_init_hook`, teardown symmetry. Unchanged from
v12 — see odoo-12-rules.md §F.

## G. Manifest hygiene (Odoo 15) — DELTA from v12

- `version`: `15.0.<major>.<minor>.<patch>` — flag if different shape.
- `assets` dict: JS/SCSS/OWL-XML must be registered in the manifest
  `assets` key (NEW in v15), NOT via `<template inherit_id=...>` XML
  records (that is the v12 way). Flag leftover XML asset records in a
  v15 module as a migration miss (web-verified).
- `web.assets_qweb` bundle is the v15 home for OWL XML templates; it is
  removed in v16 — fine to use in v15.
- `data` order, `depends` minimalism, `installable` — unchanged from v12
  (see odoo-12-rules.md §G).

## H. Project-specific notes

Unchanged from v12 — see odoo-12-rules.md §H (addon roots from
`agent-toolkit.config.json`, `root_hint` on discovery, locked-findings
files, JIRA URLs in `.codex/mcp.local.env`).

## Severity anchors — Unchanged from v12

Reuse the Odoo-12 audit anchor table — see odoo-12-rules.md "Severity
anchors". The concrete examples (daemon thread, JSON view NULL, AND/OR
bug, CSRF, decompression bomb, default drift) are version-agnostic.

## Anti-patterns specific to Odoo-15 review

- Flagging `attrs="..."` / `states="..."` as bugs — correct in v15
  (removed only in v17).
- Flagging the ABSENCE of `@api.multi` — it does not exist in v15.
  Conversely, leftover `@api.multi`/`@api.one` IS a bug (import error).
- Suggesting single-record `create(vals)` — v15 uses
  `@api.model_create_multi(vals_list)`.
- Treating jQuery as forbidden — it coexists with OWL in v15.
- Suggesting the `@odoo/owl` package import — that is v16+ (OWL 2).
