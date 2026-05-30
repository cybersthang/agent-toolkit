---
name: odoo-localization-patterns
description: Odoo `l10n_<country>` patterns — chart-of-accounts loading, tax / fiscal-position lookup by xmlid (never by `tax_use` + rate), OCA-vs-official overlap, and country-specific e-invoicing hot spots (Vietnam VietInvoice / VNPT, France FEC + NF525, Latam SAT/DIAN/SII, EU ViDA 2026+). Version-aware: pre-v15 `try_loading_for_current_company`, v15+ `_load()` API, v17+ `account_country_id` discovery, v19+ EU/Latam e-invoicing tightening. References: `references/odoo-l10n-pattern.md`, `references/odoo-einvoice-by-country.md`. Open whenever the user says "l10n", "localization", "chart of accounts", "fiscal position", "tax", "thuế", "e-invoice", "country", "Vietnam", "VN", "EU e-invoicing", or when code review touches `l10n_*/**` files.
license: MIT
---

# Odoo — Localization (`l10n_<country>`) Patterns

Localization modules are dense: `l10n_vn` ships a chart of accounts,
~20 tax templates, fiscal positions, account groups, and (sometimes)
report layouts + e-invoicing connectors. Every consultancy deploying
Odoo across regions hits the **top 6 anti-patterns** below within the
first three engagements. Vietnam is the worked example because the
toolkit's primary user base is Vietnamese consultancies — same
patterns apply elsewhere.

> Module-agnostic: never hard-code tax xmlids from one project's
> `l10n_vn` fork. Discover them with `codebase.search_xmlid` against
> the localization module under audit.

Pair with `odoo-code-review` (severity anchors),
`odoo-data-verification` (live ORM probes), and `odoo-multi-company`
(cross-country deployments are always multi-company).

## 0. The l10n module pattern

- **Naming:** `l10n_<2letter ISO>` — `l10n_vn` (VN), `l10n_us`, `l10n_fr`, `l10n_de`.
- **Multi-country combos:** `l10n_eu_service` (EU OSS), `l10n_latam_*` (AR/MX/CL/CO share `l10n_latam_base`, `l10n_latam_invoice_document`).
- **Each ships:** `account.chart.template` + tax templates + fiscal positions + `account.group` + (often) country-specific report layouts.
- **Loaded via** `account.chart.template._load(company)` on company creation (v15+); pre-v15 used `try_loading_for_current_company()`.

## 1. Version detection (MANDATORY first step)

Same protocol as `odoo-code-review` / `odoo-multi-company`: read
`__manifest__.py` `version` (`codebase.read_manifest({module_path})`);
fallback signals — `try_loading_for_current_company` call → ≤14;
`_load()` on `account.chart.template` → ≥15; `account_country_id`
field on `res.company` → ≥17. Ask only if inconclusive.

| Detected major | Notes |
|---|---|
| 12 / 13 / 14 | `try_loading_for_current_company()`; match country via `res.company.country_id` only. |
| 15 / 16 | `_load(company)` API; no per-company `account_country_id`. |
| 17 | `account_country_id` auto-derived; cleaner per-country e-invoicing hooks. |
| 18 / 19 | Tightened EU e-invoicing (`account_edi_*` reorganized), Latam signers consolidated. Re-check the target major's `account` release notes before relying on this skill for an audit. |

## 2. Pattern A — Modifying `l10n_*` directly instead of inheriting

**Confidence: H**

Odoo-official `l10n_*` modules are regenerated from canonical XML on
every minor release. Edits to the installed module (or a forked-and-
renamed copy) are silently overwritten on `-u l10n_vn`. Fix: a sibling
`l10n_<country>_<client>` module with `depends: ['l10n_<country>']`
and `noupdate="1"` on records that must survive re-imports.

```xml
<!-- BAD: editing l10n_vn/data/*.xml directly — wiped on upgrade -->
<!-- GOOD: l10n_vn_clientco/data/chart_extension.xml -->
<odoo noupdate="1">
    <record id="l10n_vn.chart_template_vn" model="account.chart.template">
        <field name="name">VAS — ClientCo branch</field>
    </record>
</odoo>
```

**Falsify:** Edit `l10n_vn` directly → run `-u l10n_vn` → edit reverts.
Sibling-module approach → edit survives.

**Invariant:**

```json
{ "id": "l10n-no-direct-edit-official", "applies_to": ["**/l10n_[a-z][a-z]/**"],
  "rules": {"must_keep_call": ["__do_not_edit_directly__"]},
  "severity": "blocker", "rationale": "Upgrades wipe direct edits — §2." }
```

---

## 3. Pattern B — Hardcoding taxes by `(tax_use, rate)` instead of xmlid

**Confidence: H**

Tax records have stable xmlids (`l10n_vn.10_VAT_S`), but rates change
— Vietnam's VAT dropped to 8% in 2022, back to 10%, then 8% again.
`search([('amount','=',10.0), ('type_tax_use','=','sale')])` breaks on
rate change, or silently picks the wrong tax when 8% and 10% coexist
during transition.

```python
# BAD — fragile to rate changes
self.env['account.tax'].search([('type_tax_use','=','sale'), ('amount','=',10.0)], limit=1)

# GOOD v17+ — stable client-defined code, country-aware
self.env['account.tax'].search([
    ('company_id','=',company.id), ('country_id','=',company.account_country_id.id),
    ('type_tax_use','=','sale'), ('l10n_vn_tax_code','=','VAT_S_STD')], limit=1)
```

Pre-v17: resolve via `self.env.ref('l10n_vn.10_VAT_S')` then match the
per-company copy by template-name.

**Falsify:** Duplicate the 10% sale tax with `amount=8.0` → audited
code returns whichever sorts first.

**Invariant:**

```json
{ "id": "l10n-no-rate-hardcoded-tax-search",
  "applies_to": ["**/models/*.py", "**/wizards/*.py"],
  "rules": {"must_keep_regex": ["self\\.env\\.ref\\(['\"]l10n_[a-z]{2}\\."]},
  "severity": "warn", "rationale": "Hardcoded rate breaks on policy changes — §3." }
```

---

## 4. Pattern C — Mixing two l10n modules (chart-code overlap)

**Confidence: H**

OCA publishes `l10n_vn` improvements ahead of Odoo-official. Installing
**both** collides on `account.account.code` — VAS numbering is fixed
by law, so both ship the *same* codes with *different* xmlids. Result:
duplicated `account.account.template` rows, ambiguous FKs,
`_check_company_consistency` raises on every move post.

```python
{'depends': ['l10n_vn', 'l10n_vn_oca_extra']}  # BAD — overlap on 111, 112, 131
{'depends': ['l10n_vn']}                       # GOOD — single canonical base;
# cherry-pick OCA's e-invoice connector (NOT its chart) into l10n_vn_clientco.
```

**Falsify:** `env['account.account.template'].search([('code','=','111'),
('chart_template_id.country_id','=', env.ref('base.vn').id)])` → expect
`len == 1`; >1 means l10n overlap.

**Invariant:**

```json
{ "id": "l10n-no-double-base", "applies_to": ["**/__manifest__.py"],
  "rules": {"must_keep_call": ["__single_l10n_base__"]},
  "severity": "warn", "rationale": "Two l10n modules collide on chart codes (VAS, GAAP) — §4." }
```

---

## 5. Pattern D — Skipping fiscal_position → wrong tax on cross-border

**Confidence: H**

`account.fiscal.position` **rewrites** taxes and accounts when a
partner's country / VAT status differs from the company's. Without it,
a Vietnamese company invoicing a Singaporean customer applies domestic
10% VAT — correct treatment is "export, 0% or non-taxable". Common
omission: custom invoice flows fetch tax directly from
`product.taxes_id` without `fiscal_position.map_tax()`.

```python
# BAD — raw product taxes
'tax_ids': [(6, 0, order_line.product_id.taxes_id.ids)]

# GOOD — routed through fiscal_position
taxes = order_line.product_id.taxes_id
if fiscal_position:
    taxes = fiscal_position.map_tax(taxes)
return {'tax_ids': [(6, 0, taxes.ids)]}
```

Same `map_account()` pattern applies — without it, domestic-revenue
accounts are used for export sales (wrong P&L category, wrong tax
report grouping).

**Falsify:** VN company + "Export — 0% VAT" fiscal position, SG customer auto-
derives to "Export" → bug: invoice line carries domestic 10% VAT.

**Invariant:**

```json
{ "id": "l10n-fiscal-position-map-tax",
  "applies_to": ["**/models/*.py", "**/wizards/*.py"],
  "rules": {"must_keep_regex": ["fiscal_position(?:_id)?\\.map_tax\\("]},
  "severity": "warn", "rationale": "Cross-border without fiscal_position rewrite — §5." }
```

---

## 6. Pattern E — OCA vs Odoo-official conflicting on same xmlid

**Confidence: M**

OCA and Odoo sometimes ship the *same logical concept* under the
*same xmlid* (e.g. `l10n_vn.tax_import_duty`) with **different field
values**. `env.ref('l10n_vn.tax_import_duty')` silently returns
whichever module was loaded last, and `-u <module>` flips the value
back and forth. Distinct from §4 (overlap by *code*) — overlap by
*xmlid* is more insidious because `env.ref()` returns the wrong
record without raising.

Pick a canonical module (almost always Odoo-official); override in
`l10n_vn_clientco` with `noupdate="1"`:

```xml
<odoo noupdate="1">
    <record id="l10n_vn.tax_import_duty" model="account.tax.template">
        <field name="amount">10.0</field>
    </record>
</odoo>
```

**Falsify:** `-u l10n_vn` then `-u l10n_vn_oca` → value oscillates.

**Invariant:**

```json
{ "id": "l10n-override-requires-noupdate",
  "applies_to": ["**/data/*.xml", "**/security/*.xml"],
  "rules": {"must_keep_regex": ["<odoo[^>]*noupdate=['\"]1['\"]"]},
  "severity": "warn", "rationale": "Without noupdate, overrides oscillate on upgrade — §6." }
```

---

## 7. Pattern F — Reports / e-invoice XML missing `_()` wrapping

**Confidence: M**

Localization modules ship report layouts and e-invoice XML generators
with country-specific labels — "Hóa đơn GTGT" (VN), "Factura
electrónica" (MX), "Facture d'acompte" (FR). When emitted from Python
without `_()` / `_lt()`, the deployment's translation file can't
override them — reports render in the developer's locale, and
e-invoice `<InvoiceTypeName>` gets the source-language literal.

```python
from odoo import _
return "Hóa đơn GTGT"   # BAD — un-translatable
return _("VAT Invoice") # GOOD — .po overrides per locale; use _lt() for class-level
```

**Invariant:**

```json
{ "id": "l10n-translate-user-facing-strings",
  "applies_to": ["**/l10n_*/**/*.py"], "rules": {"must_keep_regex": ["\\b_\\(['\"]"]},
  "severity": "warn", "rationale": "Un-wrapped strings can't be overridden by .po — §7." }
```

---

## 8. Country-specific e-invoicing hot spots

E-invoicing is where l10n bugs become legal liabilities — tax
authorities reject malformed payloads and assess penalties.

**Vietnam (`l10n_vn`)** — Odoo-official ships **no** e-invoice
connector. Every deployment integrates a third-party provider:
**VietInvoice**, **VNPT-Invoice**, **Misa-MeInvoice**, **EFY**,
**Viettel-SInvoice** — each has its own signing flow (USB token vs HSM
vs cloud-signing). Mandatory fields: `seller_tax_code` (MST),
`buyer_tax_code` (B2B), `template_code` + `invoice_series`, signed
`XMLSignature`. Invoice number gaps trigger tax-authority audits —
never delete a posted invoice; cancel + reissue with `replaces_id`.

**France (`l10n_fr`)** — **FEC export** mandatory for tax audits
(`l10n_fr_fec`). **Loi Anti-Fraude (NF525)**: invoices
cryptographically chained — `account.move.secure_sequence_number` +
`inalterable_hash` must never be null on a posted invoice. **2026+
Factur-X**: PDF/A-3 with embedded XML (`account_edi_facturx`); check
EN16931 schema version.

**Latam (`l10n_latam_*`)** — **MX (SAT/CFDI)**: every invoice signed
by `Sello Digital` cert, re-signed by SAT-authorized PAC
(`l10n_mx_edi`); never bypass PAC. **CO (DIAN)**: submit within 48h
with CUFE hash (`l10n_co_dian`); late = retroactive penalty per
invoice. **CL (SII)**: folio range pre-allocated (`l10n_cl_edi`);
running out mid-month blocks all invoicing.

**EU (ViDA 2026+)** — **VAT in the Digital Age** directive phases in
mandatory structured e-invoicing for cross-border B2B from 2026/2028.
Currently live: Italy (SdI), Spain (TicketBAI / Veri*Factu), Germany
(XRechnung), Poland (KSeF). v19+ tightens unified
`account_edi_ubl_cii` generator. Common bug: invoice issued before
customer's VAT number validated via VIES (`base_vat`) → intra-EU
reverse-charge fails to apply and seller is liable for VAT.

See `references/odoo-einvoice-by-country.md` for full provider /
xmlid / signing-cert matrix.

---

## 9. Probe recipes (`eval_orm_expression`)

Use `eval_orm_expression` (via `odoo-data-verification`) to verify the
deployment's l10n state **before** writing dependent code.

```python
# l10n module install + tax templates + fiscal positions in one pass
company = env.user.company_id
country = company.country_id  # or company.account_country_id on v17+

modules = env['ir.module.module'].search([
    ('name', '=like', f'l10n_{country.code.lower()}%'),
    ('state', '=', 'installed')])
# VN expected: [('l10n_vn', '17.0.x'), ('l10n_vn_clientco', '17.0.x')]
# Red flag: 0 results, or competing bases (l10n_vn + l10n_vn_oca)

taxes = env['account.tax'].search([('company_id', '=', company.id)])
# VN v17 expected: ~6 sale + ~6 purchase (10%, 8%, 5%, 0%, exempt)
# Red flag: 0 → chart not loaded; 50+ → double-l10n install

fps = env['account.fiscal.position'].search([('company_id', '=', company.id)])
# VN expected: at least "Export" (auto_apply=True, country_id != VN)
# Red flag: 0 fiscal positions → cross-border invoices use domestic VAT
```

```python
# E-invoice provider wiring (Vietnam example)
print({
    'tax_code': company.vat,  # MST — must be non-empty
    'einvoice_provider': getattr(company, 'l10n_vn_einvoice_provider', None),
    'signing_cert_loaded': bool(getattr(company, 'l10n_vn_signing_cert', None)),
})
# Red flag: any None/empty before issuing real invoices
```

---

## 10. Code-review checklist (H/M/L for `l10n_*/**`)

| Check | Sev | Pattern |
|---|---|---|
| Edits inside `l10n_<2letters>/**` (Odoo-official) | **H** (blocker) | §2 |
| `account.tax` search filters on `('amount', '=', N)` literal | **H** | §3 |
| Manifest `depends` lists ≥2 entries matching `l10n_<same2letters>*` | **H** | §4 |
| `tax_ids` from `product.taxes_id` without `map_tax` | **H** | §5 |
| `<record id="l10n_X.Y">` override outside `noupdate="1"` | **M** | §6 |
| User-facing strings in `l10n_*/**/*.py` without `_(` wrap | **M** | §7 |
| E-invoice generator missing `secure_sequence_number` (FR) / `MST` (VN) / `Sello Digital` (MX) | **H** | §8 |
| Hardcoded country code `'VN'`/`'FR'` vs `company.account_country_id` lookup | **L** | refactor |

---

## 11. Cross-references & sibling skills

| Concern | Skill / file |
|---|---|
| Severity anchors for l10n findings | `odoo-code-review` §D + `references/odoo-<N>-rules.md` §F |
| Live ORM probes against installed l10n state | `odoo-data-verification` |
| Multi-company × multi-country | `odoo-multi-company` |
| Scaffold for sibling `l10n_<country>_<client>` | `odoo-module-scaffold` |
| OCA-vs-official decision matrix | `odoo-community-patterns` + `odoo-enterprise-patterns` |
| L10n pattern reference (chart load + tax xmlid) | `references/odoo-l10n-pattern.md` |
| Per-country e-invoice provider matrix | `references/odoo-einvoice-by-country.md` |

**Call BEFORE this skill:** `odoo-codebase-discovery` (locate installed
l10n modules + read manifests), `odoo-deterministic-answers`
(`lookup_canonical_decision` for project-specific l10n rules — e.g.
"always use VNPT-Invoice for this client" — before re-deriving),
`odoo-data-verification` (run §9 probes before writing code that
assumes a specific chart / tax / fiscal-position state).

## 12. Hard rules summary

- Never edit `l10n_<2letters>/**` directly — extend via sibling module
  with `noupdate="1"`.
- Never search `account.tax` by `(amount, type_tax_use)` literal — use
  xmlid / stable client-defined code.
- Never install two competing l10n bases for the same country.
- Never assign `tax_ids` from `product.taxes_id` without routing
  through `fiscal_position.map_tax()`.
- Never override an `l10n_*.<id>` from outside that module without
  `noupdate="1"`.
- Never emit a user-facing string from `l10n_*` Python without
  wrapping in `_()` / `_lt()`.
- Never ship VN / FR / Latam without verifying e-invoicing provider +
  signing certificate are wired (§8 + §9 probes).
