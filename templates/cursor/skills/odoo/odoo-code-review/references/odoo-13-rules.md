# Odoo 13 — Code Review Reference (Version-Specific Deltas)

> odoo-13 reference (drafted v0.29). Deltas vs odoo-12-rules.md web-verified where cited; `<!-- VERIFY -->` items need DEV confirmation.

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **13**. Combine with the shared dimensions in the parent SKILL.md
and the cross-version checklists under `_common/code-review/references/`.
Odoo 13 is v12-shaped EXCEPT for the ORM-decorator removal and the
`account.move` merge — review those two deltas closely.

## A. ORM / API decorators (Odoo 13)

DELTA vs v12 — `@api.multi` and `@api.one` were **removed** in 13.0
(verified: absent from 13.0 `odoo/api.py`). Recordset is the default.

- `@api.multi` / `@api.one` in **new** 13 code is a BLOCKER-style port
  error — they no longer exist; an import-time `AttributeError` or a
  silent decorator-as-noop is the symptom. Flag any occurrence.
- Methods iterate `self` directly (`for rec in self:`). `ensure_one()`
  whenever a method assumes a single record (unchanged from v12).
- `@api.model` on class-level methods that don't need a recordset
  (unchanged).
- Override `create()` should be `@api.model_create_multi(self, vals_list)`.
  A single-record `@api.model create(self, vals)` override still works
  (the base normalises) but silently degrades batch inserts to
  per-record overrides — flag MEDIUM if the class is hit by batch
  creates (imports, `(0,0,{})` command lists).
- `@api.depends(...)` complete on every computed field (unchanged).
- `@api.depends_context('force_company')` (or other context keys) on
  company/locale-sensitive computes — missing it causes stale cross-company
  values (see multi-company reference).

### Severity calibration

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | `@api.multi` / `@api.one` present in 13 code (removed decorator; port error) |
| MEDIUM   | `create()` overridden as single-record `@api.model` on a model hit by batch `(0,0,{})` inserts → per-record override defeats `model_create_multi` |
| MEDIUM   | `@api.depends` missing a field the compute reads → stale cached values |
| MEDIUM   | Company-dependent compute missing `@api.depends_context('force_company')` → stale cross-company value |
| LOW      | Manual `for rec in self:` loop on a method that is always single-record (style; could `ensure_one()`) |

## B. Loops + N+1 (Odoo 13 specifics)

Unchanged from v12 — see odoo-12-rules.md §B. (`search`/`browse` in
loops, `len(search(...))` → `search_count`, unstored computes re-firing
per record, `t-foreach` over large recordsets.) Only the decorator
syntax in the examples differs (no `@api.multi`).

## C. Views (Odoo 13 syntax)

Unchanged from v12 — see odoo-12-rules.md §C. `attrs="{...}"` and
`states="draft,confirmed"` are the **correct** Odoo-13 idioms (verified:
removed only in 17+). Do NOT flag them. Same malformed-`attrs` /
missing-`position` / root-tag-replacement checks apply.

## D. Frontend (QWeb + jQuery — Odoo 13 default)

Unchanged from v12 — see odoo-12-rules.md §D. jQuery + `web.Widget` +
`odoo.define()` are legal in 13; assets register via XML inheritance of
`web.assets_backend` / `web.assets_frontend` (the `assets` manifest-dict
key is **v15+**, flag it as ported-forward if seen in 13). The
`/** @odoo-module **/` ES-module marker is **15+** — flag it as an
out-of-version import in a 13 module.

## E. Security / multi-company (Odoo 13 nuances)

DELTA vs v12 — 13.0 introduced the modern company environment.

- `self.env.company` / `self.env.companies` exist in 13 (verified: 13.0
  `odoo/api.py`), driven by the `allowed_company_ids` context key. Flag
  v12-era `self.env.user.company_id` as the *default* for `company_id`
  fields — the 13 idiom is `default=lambda self: self.env.company`.
- `_company_default_get('<model>')` is **deprecated in 13** (verified:
  13.0 `res_company.py` emits a deprecation warning). Flag LOW if used
  in new code; suggest `self.env.company`.
- `_check_company_auto = True` + `check_company=True` on company-scoped
  Many2one fields is the 13 consistency mechanism — flag MEDIUM if a
  cross-company relational field lacks it on a model that mixes companies.
- `ir.rule` company domains still reference `company_ids` (plural) —
  unchanged from v12. Singular `user.company_id.id` is still a bug.
- CSRF rules unchanged from v12 — see odoo-12-rules.md §E.
- Every new `models.Model` still needs an `ir.model.access.csv` row
  (unchanged).

## F. Monkey-patches / install-uninstall symmetry (Odoo 13)

Unchanged from v12 — see odoo-12-rules.md §F.

## G. Manifest hygiene (Odoo 13)

- `version`: `13.0.<major>.<minor>.<patch>` — flag if different shape.
- No `assets` dict key in 13 manifests (that's 15+); assets go through
  XML. Flag a 15-style `assets` key as ported-forward.
- `data` order, `depends`, `installable`/`application` rules unchanged
  from v12 — see odoo-12-rules.md §G.

## H. Accounting review (Odoo 13 — `account.move` merge)

DELTA vs v12 — `account.invoice` / `account.invoice.line` /
`account.invoice.tax` were **removed** and merged into `account.move` /
`account.move.line` (verified: 13.0 PR #33797).

- Flag any reference to `account.invoice`, `account.invoice.line`,
  `account.invoice.tax`, `account.invoice.refund`,
  `account.invoice.confirm` in 13 code — these models/wizards are gone.
- The discriminator field on `account.move` in 13 is **`type`** (NOT
  `move_type` — that rename is v14). Flag `move_type` in 13 code as a
  v14-era port error.
- Invoice posting: `move.action_post()` (not `invoice_validate`).
  Refunds: `account.move.reversal`.
- Invoice lines: `invoice_line_ids` (One2many → `account.move.line`).

## I. Project-specific notes (this Odoo-13 workspace)

Unchanged from v12 — see odoo-12-rules.md §H (addon roots from
`agent-toolkit.config.json`, `root_hint` on discovery calls,
`.codex/audit_findings_*_locked.md` before re-deriving fixes, JIRA URLs
in `.codex/mcp.local.env`).

## Anti-patterns specific to Odoo-13 review

- Flagging `attrs="..."` as a bug — correct in 13 (removed only in 17+).
- Treating jQuery as deprecated — fine in 13; OWL backend is 14+/17.
- Flagging `@api.model_create_multi` — that is the **correct** 13 form
  (not, as in v12, a "14+ feature"). Conversely, `@api.multi` IS a bug
  in 13.
- Asking for `account.invoice` — it does not exist in 13; use
  `account.move`.
- Re-deriving "what to fix" without consulting
  `.codex/audit_findings_*_locked.md` and `canonical_decisions.json`.
