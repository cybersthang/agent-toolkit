# Odoo localization (`l10n_<country>`) module conventions

Reference for the `odoo-localization-patterns` SKILL. Conventions below
are stable across majors; the one moving part (chart-loading API) is
called out. Do not assert a version for a fact you have not opened the
target's source / accounting-localization howto for.

## Module naming

- **`l10n_<ISO 3166-1 alpha-2>`** — `l10n_us`, `l10n_fr`, `l10n_de`,
  `l10n_vn`, `l10n_ch`, `l10n_it`. Lower-case two-letter country code.
- **Shared bases:** `l10n_latam_base`, `l10n_latam_invoice_document`
  (AR/MX/CL/CO build on these); `l10n_eu_oss` for EU One-Stop-Shop;
  `l10n_multilang` for translated chart/tax/journal data.
- **Client extensions:** keep edits in a sibling `l10n_<country>_<client>`
  that `depends` on the official module — never edit the official one
  (it is regenerated from canonical data on every minor release, wiping
  in-place edits).

On installing `account`, Odoo auto-installs the `l10n_<code>` matching
the company's country; `l10n_generic_coa` (US-style) is the fallback when
no country is set. (Verified: accounting localization howto, 17.0.)

## The four template models

A localization ships *templates*; installing it instantiates concrete
records (`account.account`, `account.tax`, `account.fiscal.position`,
`account.journal`) onto the company.

| Template model | Becomes | Holds |
|---|---|---|
| `account.chart.template` | the chart definition | CoA name, currency, code digits, default taxes/accounts |
| `account.account.template` | `account.account` | code (e.g. VAS `111`), name, account type |
| `account.group.template` | `account.group` | hierarchical code ranges for the CoA |
| `account.tax.template` | `account.tax` | `amount`, `type_tax_use`, repartition lines |
| `account.fiscal.position.template` | `account.fiscal.position` | tax + account mappings by partner profile |

`account.fiscal.position.template` carries
`account.fiscal.position.tax.template` (tax substitutions) and
`account.fiscal.position.account.template` (account substitutions).

> Naming note: the model is `account.chart.template`, but the **data /
> Python file layout** that defines a chart has shifted across majors
> (older `data/account_chart_template_data.xml` + per-template CSVs such
> as `account.account-<xx>.csv`, `account.tax-<xx>.csv`,
> `account.group-<xx>.csv`; newer majors define templates in a
> `models/template_<xx>.py`). Open the target major's localization howto
> before scaffolding — do not assume one layout.

## Chart-loading API (the version-sensitive bit)

```python
# v15+  — load templates onto a company
self.env['account.chart.template']._load(company)

# <= v14 — older entry point
self.env['account.chart.template'].try_loading_for_current_company()
```

Detection signals (from the SKILL's Step 0): a
`try_loading_for_current_company` call -> <= v14; `_load(` on
`account.chart.template` -> v15+; an `account_country_id` field on
`res.company` -> v17+ (per-company country used for tax/fiscal-position
discovery). The internal loader API has been refactored across majors —
re-read the target's `account` source before depending on a signature.

## Fiscal positions — why they exist

`account.fiscal.position` **rewrites** taxes and accounts when a partner's
country / VAT status differs from the company's:

```python
# Route product taxes through the fiscal position — NEVER raw product.taxes_id
taxes = line.product_id.taxes_id
if fiscal_position:
    taxes = fiscal_position.map_tax(taxes)      # domestic VAT -> export 0% / RC
    account = fiscal_position.map_account(account)  # domestic -> export revenue acct
```

Skip `map_tax()` and a VN company invoicing Singapore applies domestic
10% VAT instead of export 0% — wrong tax AND wrong P&L grouping. Fiscal
positions can `auto_apply` based on partner country / VAT.

## Resolving taxes/accounts — by xmlid, not by rate

Tax **records** have stable xmlids; **rates** change (VN VAT 10% -> 8% ->
10% -> 8%). Searching by `('amount','=',10.0)` breaks on a rate change and
picks the wrong tax when two rates coexist during a transition.

```python
# BAD — fragile to rate policy
env['account.tax'].search([('type_tax_use','=','sale'),('amount','=',10.0)], limit=1)

# GOOD — resolve the template-derived record by xmlid
env.ref('l10n_vn.10_VAT_S')   # then match the per-company copy by name/code
```

## `noupdate="1"` on overrides

To override a record owned by the official module, wrap it in
`<odoo noupdate="1">` inside the **client** module — otherwise the value
oscillates: `-u l10n_xx` flips it back, `-u l10n_xx_client` flips it
forward.

```xml
<!-- l10n_vn_clientco/data/tax_override.xml -->
<odoo noupdate="1">
    <record id="l10n_vn.tax_import_duty" model="account.tax.template">
        <field name="amount">10.0</field>
    </record>
</odoo>
```

## Translatable strings

Localization Python that emits user-facing labels ("Hóa đơn GTGT",
"Facture d'acompte") must wrap them in `_()` (or `_lt()` at class level)
so a deployment's `.po` can override them — otherwise reports and
e-invoice `<...Name>` elements render in the developer's locale.

```python
from odoo import _
return _("VAT Invoice")     # GOOD — .po overridable per locale
```

## Hard rules (l10n-specific)

- Module name is `l10n_<2-letter ISO>`; client work goes in a sibling
  `l10n_<country>_<client>` that `depends` on it.
- Never edit an official `l10n_*` module in place — it is regenerated on
  upgrade.
- Never install two competing chart bases for the same country (code
  collisions on legally-fixed account numbers).
- Resolve taxes by xmlid / stable code, never by `(amount, type_tax_use)`.
- Always route cross-border taxes through `fiscal_position.map_tax()`
  (and `map_account()`).
- Wrap overrides of official records in `<odoo noupdate="1">`.
- Wrap user-facing l10n strings in `_()` / `_lt()`.

## Sources verified

- `https://www.odoo.com/documentation/17.0/developer/howtos/accounting_localization.html`
  — `l10n_XX` naming, auto-install by country code, template models, CSV
  data-file conventions, `template_<xx>.py` layout.
- `https://www.odoo.com/documentation/16.0/developer/reference/standard_modules/account/account_chart_template.html`
  — `account.chart.template` model reference.
- `https://www.odoo.com/documentation/15.0/developer/howtos/accounting_localization.html`
  — `_load()` chart-loading API (v15+).
