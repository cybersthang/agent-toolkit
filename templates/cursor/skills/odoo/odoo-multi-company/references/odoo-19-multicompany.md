# Odoo 19 — multi-company specifics (neighbour = v18 → v17)

> odoo-19 reference (drafted v0.29). Deltas vs v18/v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load this when Step 0 detected major = **19** (released Sept 2025, Odoo
Experience 2025; stable through the 19.x patch line). The multi-company
*model* (`with_company()`, `_check_company_auto`, `check_company=True`,
`self.env.company` / `self.env.companies`, `company_dependent=True`) is
unchanged from v17/v18 — so **read `odoo-18-multicompany.md` first**
(which itself cascades to `odoo-17-multicompany.md`). This file flags
only the 19-specific deltas: the `read_group` deprecation and the
documented company-dependent compute decorator.

## What is UNCHANGED from v18 (and v17)

See `odoo-18-multicompany.md` (and `odoo-17-multicompany.md` for the full
treatment). Verified against the Odoo 19 "Multi-company Guidelines",
/documentation/19.0/developer/howtos/company.html:

- **§1 `with_company(company_or_id)`** — same propagation; `company_id`
  in `vals` still required.
- **§2 `self.env.company` / `self.env.companies` /
  `self.env.user.company_id`** — same semantics; prefer
  `self.env.company`.
- **§3 `_check_company_auto = True` + `check_company=True`** on
  relational fields — same auto-validation; still NEVER on `company_id`
  itself (carried forward from the 18 docs hard rule).
- **§4 `ir.rule` `company_ids` / `companies` placeholders** — same domain
  forms (the 19 docs list both placeholders explicitly).
- **§5 `default=lambda self: self.env.company`** on `required=True`
  `company_id` — same documented pattern.
- **§6 `mail.template.send_mail()`** — chain `with_company` BEFORE send.
- **§7 Tests** — `TransactionCase`; `self.env(user=..., company=...)`.
- **§8 `check_company=True` default domain**
  `['|', ('company_id','=',False), ('company_id','=',company_id)]` —
  unchanged from v18.
- **Display labels** — `_compute_display_name` (NOT `name_get`, removed
  pre-18) — unchanged from v18.

## 19-specific notes / DELTAS vs 18

The multi-company semantics are unchanged from v18; the deltas below are
framework-wide ORM changes (verified against the Odoo 19.0 ORM changelog,
/documentation/19.0/developer/reference/backend/orm/changelog.html, and
PR #110737) that surface in multi-company aggregation / reporting code.

### `read_group()` deprecated → `_read_group()` / `formatted_read_group()`

This is the load-bearing 19 delta for multi-company **reports**.
`read_group()` is deprecated in 19; use `_read_group()` for backend
aggregation and `formatted_read_group()` for the formatted public API
(verified: 19.0 changelog; `_read_group()` got a new signature in
#110737). Cross-company consolidation reports that grouped by
`company_id` via `read_group([...], ['amount:sum'], ['company_id'])`
should move to the new API.

```python
# v19 — backend per-company aggregation (replaces read_group)
groups = self.env['account.move.line']._read_group(
    domain=[('company_id', 'in', self.env.companies.ids)],
    groupby=['company_id'],
    aggregates=['balance:sum'],
)
for company, balance_sum in groups:
    ...   # company is a res.company record; balance_sum the aggregate
```

The `_read_group()` return shape (list of value-tuples, NOT the legacy
list-of-dicts with `__domain` / `__count` keys) is the new signature.
When the exact aggregate/groupby tuple ordering is load-bearing in an
audit finding, read `_read_group` on the `odoo/odoo` 19.0 branch — the
positional layout matters and is easy to misquote.
`aggregator='sum'` (renamed from `group_operator` back in 17.2) is the
field-level attribute used by these aggregates.

A multi-company report still using `read_group()` in 19 is a
deprecation, not yet a hard break — flag it as migration cleanup with
version-tentative severity unless the project pins a 19.x where it was
actually removed (re-check the patch line).

### `company_dependent` compute decorator — documented requirement

`@api.depends_context('company')` on a compute that reads a
`company_dependent` field is restated as a requirement in the 19
guidelines (same as 18). No behaviour change — listed so an 19 audit
applies the same rule.

### Currency `_convert` signature

<!-- VERIFY(odoo-19): the 19 multi-currency docs describe res.currency._convert as "updated to handle multi-company/multi-currency contexts" but a precise positional/keyword delta vs the v17/v18 signature (from_amount, to_currency, company, date, round=True) could not be web-confirmed. Read res.currency._convert on the odoo/odoo 19.0 branch (odoo/addons/base/models/res_currency.py) before asserting any signature change in a customer-facing finding. Cross-company FX selection rules in references/odoo-multi-currency.md are version-agnostic and still apply. -->

## 19-specific hard rules

- Multi-company aggregation/reports: prefer `_read_group()` /
  `formatted_read_group()` over the deprecated `read_group()`; expect the
  new tuple-based return shape (#110737).
- Everything else (with_company, `_check_company_auto`,
  `check_company=True` rules incl. the `company_id`-itself prohibition,
  `default=lambda self: self.env.company`, `ir.rule` `company_ids`,
  `_compute_display_name` labels, `@api.depends_context('company')`)
  is unchanged from v18 — see `odoo-18-multicompany.md`.
- Do NOT assert a `_convert` signature change without reading the 19.0
  branch (see VERIFY note above).

See `references/odoo-multi-currency.md` for cross-company FX rate
selection rules (version-agnostic).
