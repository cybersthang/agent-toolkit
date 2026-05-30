> odoo-14 reference (drafted v0.29). Deltas vs odoo-12-rules.md web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

# Odoo 14 — Code Review Reference (Version-Specific Deltas)

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **14**. Combine with the shared dimensions in the parent SKILL.md
and the cross-version checklists under `_common/code-review/references/`.

**Orientation**: On ORM/API decorators 14 behaves like 17 (no `@api.multi`);
on the view layer and asset declaration it behaves like 12 (`attrs`/`states`,
XML asset bundles). Calibrate flags accordingly.

## A. ORM / API decorators (Odoo 14 — like 17, NOT like 12)

- `@api.multi` is **removed** (since Odoo 13; verified `odoo/api.py` 14.0
  has no `multi`). A `@api.multi` decorator or `from odoo.api import multi`
  in 14 code is a migration bug → import-time failure. **Flag it.**
- `@api.one` is **removed** (since 13). Same severity.
- Methods are **recordset by default** — `for record in self:` needs no
  decorator. Do NOT flag a missing `@api.multi` (it correctly does not exist).
- `@api.model_create_multi(vals_list)` is the recommended `create()`
  override (decorator EXISTS in 14, verified). A single-record `@api.model
  create(self, vals)` override still runs in 14 but processes per-record,
  losing batch semantics — flag as MEDIUM (consistency / perf), not BLOCKER,
  since base `create` still iterates correctly.
- `@api.depends`, `@api.constrains`, `@api.onchange`, `@api.depends_context`
  as in 12/17.
- `ensure_one()` whenever a method assumes a single record.
- `@api.ondelete` does **NOT** exist in 14 (introduced in 15). Deletion
  guards in 14 are done by overriding `unlink()` or via SQL constraints —
  do NOT suggest `@api.ondelete` for a 14 module.

### Severity calibration

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | `@api.multi` decorator or `from odoo.api import multi` in 14 code → import-time failure, blocks module load |
| BLOCKER  | `@api.one` used → removed in 13, import-time failure |
| MEDIUM   | Override `create()` with single-record `@api.model create(vals)` instead of `@api.model_create_multi(vals_list)` — loses batch semantics on bulk import |
| MEDIUM   | `@api.depends` missing a field the compute reads → stale cached values |
| LOW      | Extra `@api.model` on a method that operates on a recordset — style noise |

## B. Loops + N+1 (Odoo 14 specifics)

Unchanged from v12 — see odoo-12-rules.md §B. (`search`/`browse(id)` in
loops → batch; `len(search())` → `search_count`; stored-compute fan-out;
`t-foreach` over 1000+ records in QWeb reports.)

## C. Views (Odoo 14 syntax — same as 12, DIFFERENT from 17)

- `attrs="{'invisible': [('state','=','done')]}"` and `states="draft,confirmed"`
  are the **correct** Odoo-14 idioms (verified against
  `addons/base/models/ir_ui_view.py` 14.0). **Do NOT flag them as bugs.**
- The direct `invisible="<py expr>"` syntax does NOT exist in 14 (that is
  17+) — if a 14 module ships it, the view will not parse. Flag as BLOCKER.
- Everything else unchanged from v12 — see odoo-12-rules.md §C (malformed
  `attrs` JSON, `attrs` referencing undeclared field, `<xpath>` without
  `position=`, root-tag replacement, XML-ID rename without migration).

## D. Frontend (QWeb + jQuery default; OWL is NEW in 14)

- jQuery / `web.Widget` selectors are **legal** in 14 and are still the
  default for custom backend widgets — do NOT flag as deprecated.
- OWL exists in 14 (first shipped this version, OWL 1.4.11) but most of the
  web client is the legacy widget framework. An OWL component in a 14 module
  is legitimate — but it must use the **global `owl` namespace**
  (`const { Component } = owl;`), NOT `import ... from "@odoo/owl"`, and must
  be wrapped in `odoo.define(...)`.
- The `/** @odoo-module **/` header is **NOT honored in 14 — it is 15+**
  (verified: 14.0 has no `odoo/tools/js_transpiler.py` and no
  `transpile_javascript` / `is_odoo_module` import in
  `odoo/addons/base/models/assetsbundle.py`; both first appear on the 15.0
  branch). In 14 the header is just a comment and the file is NOT transpiled,
  so ES6 `import`/`export` in a 14 asset will **not** resolve — the bundle
  loads raw and the module errors at runtime. **Flag `import`/`export` (or a
  load-bearing `/** @odoo-module **/`) in a 14 JS asset as a version
  mismatch.** A bare `/** @odoo-module **/` comment with no ES6 syntax is
  harmless (ignored).
- Asset bundles: new JS / SCSS must be registered via **XML** inheriting
  `web.assets_backend` / `web.assets_frontend`. The manifest `'assets'`
  dict is **15+** (verified) — flag an `'assets': {...}` block in a 14
  manifest as a version mismatch (it is silently ignored in 14).
- QWeb templates: `t-foreach`, `t-if`, `t-esc`, `t-raw`. `t-raw` is XSS-risk.

## E. Security / multi-company (Odoo 14 nuances — `with_company` era)

- Multi-company API in 14 is the **`with_company()` / `env.company` era**,
  NOT the v12 `force_company` era. `with_context(force_company=...)` in 14
  logs a deprecation warning and is no longer honored (verified
  `odoo/models.py` 14.0: "Context key 'force_company' is no longer
  supported. Use with_company(company) instead."). Flag `force_company`
  usage in 14 as MEDIUM. See `odoo-multi-company/references/odoo-14-multicompany.md`.
- `_check_company_auto = True` + `check_company=True` on `Many2one` exist
  in 14 — prefer over hand-rolled company-consistency checks.
- Every new `models.Model` needs ≥1 `ir.model.access.csv` row;
  `TransientModel`/`AbstractModel` don't.
- Company-scoped models need an `ir.rule` filtering by `company_id` against
  the `company_ids` placeholder.
- CSRF: unchanged from v12 — see odoo-12-rules.md §E (`type='json'`
  conventionally `csrf=False`; `type='http'` state-changing POSTs MUST keep
  `csrf=True`).

## F. Monkey-patches / install-uninstall symmetry (Odoo 14)

Unchanged from v12 — see odoo-12-rules.md §F (`setattr` patches need an
uninstall restore path; `_register_hook` / `_post_init_hook` paired with
teardown).

## G. Manifest hygiene (Odoo 14)

- `version`: `14.0.<major>.<minor>.<patch>` — flag if different shape.
- `data` order: `security/` → `data/` → `views/` → menus.
- `depends` lists exactly what the module imports / inherits.
- `license`: conventional (`LGPL-3` for community, `OEEL-1` for Enterprise);
  match sibling manifests.
- No `'assets'` dict (that is 15+) — assets via XML records in 14.
- `installable: True`; `application` only for top-level apps.

## H. Project-specific notes (this Odoo-14 workspace)

Unchanged from v12 — see odoo-12-rules.md §H (addon roots from
`agent-toolkit.config.json`; pass `root_hint` to discovery tools; consult
`.codex/audit_findings_*_locked.md` before answering "anything else to
fix?"; JIRA URLs only in `.codex/mcp.local.env`).

## Anti-patterns specific to Odoo-14 review

- Flagging missing `@api.multi` — it is correctly absent in 14 (removed in 13).
- Suggesting `@api.multi` / `@api.one` "for compatibility" — both removed.
- Flagging `attrs="..."` / `states="..."` as bugs — they are correct in 14.
- Suggesting the direct `invisible="<expr>"` view syntax — that is 17+,
  will not parse in 14.
- Suggesting `@api.ondelete` — that is 15+; in 14 override `unlink()`.
- Suggesting the manifest `'assets'` dict — that is 15+; 14 uses XML asset
  bundles.
- Suggesting ES6 `import`/`export` modules or relying on `/** @odoo-module **/`
  transpilation — that is 15+; a 14 OWL component uses `odoo.define(...)` +
  the global `owl` namespace (`const { Component } = owl;`).
- Suggesting `with_context(force_company=...)` — deprecated and ignored in
  14; use `with_company()`.
- Re-deriving "what to fix" without consulting
  `.codex/audit_findings_*_locked.md` and `canonical_decisions.json` first.
