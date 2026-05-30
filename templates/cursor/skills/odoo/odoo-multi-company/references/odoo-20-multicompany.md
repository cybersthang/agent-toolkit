# Odoo 20 — multi-company specifics (PRE-GA; neighbour = v19 → v18 → v17)

> odoo-20 reference (drafted v0.29). **Odoo 20 is PRE-GA at drafting
> time.** Planned GA Sept 2026 (Odoo Experience 2026, Brussels, 24–26
> Sept 2026); until then 20 lives on the non-frozen `master` branch and
> NOTHING below is stable. Deltas cascade from v19/v18/v17; every
> 20-specific claim is <!-- VERIFY(odoo-20) --> until the branch is cut.

Load this when Step 0 detected major = **20**. Because 20 has not reached
GA, this file is a **cascade stub**: the multi-company API is assumed
unchanged from v19 (which is unchanged from v18/v17) and any audit
finding that hinges on 20-specific behaviour MUST be flagged
version-tentative and re-checked against the live `master` / 20.0 branch
of `odoo/odoo` and the master multi-company guidelines
(/documentation/master/developer/howtos/company.html).

## What is assumed UNCHANGED from v19 (→ v18 → v17)

Read `odoo-19-multicompany.md` as the base (it cascades to
`odoo-18-multicompany.md` and `odoo-17-multicompany.md`). The full
multi-company model is assumed to carry forward:

- **`with_company(company_or_id)`** — same propagation; `company_id` in
  `vals` still required.
- **`self.env.company` / `self.env.companies` /
  `self.env.user.company_id`** — same semantics; prefer
  `self.env.company`.
- **`_check_company_auto = True` + `check_company=True`** on relational
  fields — same auto-validation; still NEVER on `company_id` itself.
- **`ir.rule` `company_ids` / `companies` placeholders** — same domain
  forms.
- **`default=lambda self: self.env.company`** on `required=True`
  `company_id`.
- **`mail.template.send_mail()`** — chain `with_company` BEFORE send.
- **Tests** — `TransactionCase`; `self.env(user=..., company=...)`.
- **`check_company=True` default domain**
  `['|', ('company_id','=',False), ('company_id','=',company_id)]`.
- **Display labels** — `_compute_display_name` (NOT `name_get`).
- **Aggregation/reports** — `_read_group()` / `formatted_read_group()`
  (the v19 deprecation of `read_group()` is assumed to hold / harden in
  20; re-check whether `read_group()` is fully removed in 20.0).
- **`@api.depends_context('company')`** on company-dependent computes.

## 20-specific notes / DELTAS

<!-- VERIFY(odoo-20): No multi-company-specific API deltas can be confirmed pre-GA. The headline Odoo 20 theme reported pre-release is deep/"agentic" AI embedding (accounting, website, helpdesk, timesheets, records) — orthogonal to the multi-company ORM contract. Before relying on this file for a 20 audit: (1) read /documentation/master|20.0/developer/howtos/company.html for any reworded company rules; (2) read the master ORM changelog for read_group removal vs deprecation, any with_company / company_dependent / check_access changes; (3) read res_currency.py / models.py on the 20.0 branch for signature drift. Treat ALL 20 multi-company findings as version-tentative until GA. -->

## 20-specific hard rules

- This file is a **pre-GA cascade stub**. Apply `odoo-19-multicompany.md`
  rules; flag any 20-specific finding LOW / version-tentative.
- Before citing ANY 20 multi-company behaviour in a customer-facing
  audit, re-verify against the live `master` / 20.0 branch and the master
  multi-company guidelines — the branch is not frozen.
- No `_convert` / `read_group` removal / `check_access` claim about 20
  may be asserted without reading the matching 20.0 source.

See `references/odoo-multi-currency.md` for cross-company FX rate
selection rules (version-agnostic).
