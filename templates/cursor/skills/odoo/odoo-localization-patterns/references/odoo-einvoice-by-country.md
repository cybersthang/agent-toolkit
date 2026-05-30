# Odoo e-invoicing patterns by country

Reference for the `odoo-localization-patterns` SKILL. E-invoicing is
where l10n bugs become legal liabilities — authorities reject malformed
payloads and assess penalties. Module **existence** is verified below;
do not assert a specific version for a module's behaviour without opening
that major's source / fiscal-localization doc.

## The `account_edi` framework

Odoo standardizes EDI through the **`account_edi`** module ("Import/Export
Invoices From XML/PDF", category Accounting; `depends: ['account']`). It
exists in current majors (confirmed on branches 16.0 and 17.0) and an
EDI/electronic-invoicing capability is documented as far back as 14.0.

Format-specific generators are separate modules layered on top:

- **`account_edi_ubl_cii`** — the unified UBL + CII generator. Contains
  UBL 2.0 < 2.1 < **BIS 3** inheritance, plus E-FFF, EHF3, NLCIUS,
  **XRechnung** (UBL) and **Factur-X** (the CII format). Confirmed present
  on branches 17.0 and 18.0. Verify its `depends` on your target: on
  17.0 the manifest `depends` is `['account']` (not `account_edi`) — the
  module wiring around `account_edi` has been reorganized across majors,
  so do not assume the dependency edge.

```text
account            base accounting
  └─ account_edi          EDI framework (account.edi.format)
  └─ account_edi_ubl_cii  UBL (BIS3, XRechnung, NLCIUS, EHF3, E-FFF) + CII (Factur-X)
```

When generating the invoice PDF, UBL formats embed the PDF (base64)
inside the XML, so importing the XML alone re-creates the PDF. Factur-X
embeds the XML inside a **PDF/A-3** instead.

## EU — EN 16931, UBL, Factur-X, Peppol

- **EN 16931** is the EU semantic standard for the core invoice; **UBL**
  and **CII** are its two syntax bindings. **Factur-X** = CII XML embedded
  in a PDF/A-3 (identical to **ZUGFeRD 2.x** in Germany). Odoo's Factur-X
  output targets the EN 16931 conformance level.
- **Peppol BIS Billing 3.0** is the UBL profile for the Peppol network.
  Recent majors ship `account_peppol` and let Odoo act as a Peppol access
  point / SMP — confirm availability on your target major.
- **Common bug:** issuing an intra-EU B2B invoice before the customer's
  VAT number is validated via **VIES** (`base_vat`) — reverse-charge fails
  to apply and the seller becomes liable for the VAT.
- **ViDA ("VAT in the Digital Age")** phases in mandatory structured
  cross-border B2B e-invoicing across the EU later this decade; treat the
  exact dates as policy to confirm, not a code fact.

## Italy — FatturaPA via SdI

- Invoices are XML in the **FatturaPA** schema, transmitted through the
  **SdI** (Sistema di Interscambio), which validates before delivery.
- **Odoo Enterprise:** `l10n_it_edi` generates, submits and tracks
  FatturaPA (Demo / Test / Official EDI modes).
- **OCA alternative:** `l10n_it_fatturapa` (+ `l10n_it_fatturapa_out` /
  `_in`) and `l10n_it_sdi_channel` (PEC / web-API / SFTP transmission).
- Do not install the Odoo and OCA stacks together for the same DB — they
  collide on Italian chart/tax records.

## Spain — SII (and TicketBAI / Veri*Factu)

- **SII** = *Suministro Inmediato de Información del IVA*: near-real-time
  submission of VAT record books to the AEAT (required for >EUR 6M
  turnover / REDEME registrants; within ~4 days, before the 16th of the
  following month).
- **Odoo Enterprise:** `l10n_es_edi_sii` ("Spain - SII EDI Suministro de
  libros") sends VAT info from customer invoices / vendor bills after
  validation; needs a configured certificate + tax-agency endpoint.
- **OCA alternative:** `l10n_es_aeat_sii` (a.k.a. `..._oca`).
- Regional **TicketBAI** (Basque Country) and national **Veri*Factu** are
  separate Spanish anti-fraud regimes — distinct modules; confirm on the
  Spain fiscal-localization page for your major.

## France — Factur-X + FEC + anti-fraud chaining

- **FEC** (`l10n_fr_fec`) export is mandatory for tax audits.
- **Loi Anti-Fraude (NF525):** posted invoices are cryptographically
  chained — `account.move.secure_sequence_number` + `inalterable_hash`
  must never be null on a posted move.
- **Factur-X** is the French B2B structured format (PDF/A-3 + embedded
  CII): in Enterprise via `account_edi_ubl_cii`; OCA option
  `l10n_fr_account_invoice_facturx` (on `account_invoice_facturx` +
  `l10n_fr_siret`). The 2026+ French e-invoicing reform mandates it —
  treat the timeline as policy to confirm.

## Latin America (`l10n_latam_*`)

- Built on `l10n_latam_base` + `l10n_latam_invoice_document`.
- **MX (SAT / CFDI 4.0):** invoice signed with the *Sello Digital* cert,
  re-signed by a SAT-authorized **PAC** (`l10n_mx_edi`) — never bypass the
  PAC.
- **CO (DIAN):** submit with a **CUFE** hash (`l10n_co_dian` / DIAN
  modules); late submission = per-invoice penalty.
- **CL (SII):** **folio** ranges pre-allocated (`l10n_cl_edi`); running out
  mid-month blocks invoicing.
- **PE:** UBL 2.1 e-invoicing.

## Vietnam (`l10n_vn`)

Odoo-official ships **no** e-invoice connector — every deployment
integrates a third-party provider (**VNPT-Invoice**, **Viettel-SInvoice**,
**MISA-meInvoice**, **EFY**, **VietInvoice**), each with its own signing
flow (USB token / HSM / cloud). Mandatory fields: seller tax code (MST),
buyer tax code (B2B), template code + invoice series, signed
`XMLSignature`. Never delete a posted invoice — number gaps trigger
audits; cancel + reissue with a `replaces_id`-style link.

## Audit checklist (e-invoicing)

| Country | Module(s) — confirm version | Must-not-be-null / required |
|---|---|---|
| EU generic | `account_edi_ubl_cii`, `account_peppol` | VIES-validated VAT before intra-EU RC |
| IT | `l10n_it_edi` (EE) / `l10n_it_fatturapa` (OCA) | FatturaPA schema, SdI transmission channel |
| ES | `l10n_es_edi_sii` (EE) / `l10n_es_aeat_sii` (OCA) | certificate + AEAT endpoint, 4-day window |
| FR | `account_edi_ubl_cii`; `l10n_fr_fec` | `secure_sequence_number`, `inalterable_hash` |
| MX | `l10n_mx_edi` | Sello Digital + PAC stamp (CFDI 4.0) |
| CO | `l10n_co_dian` | CUFE, 48h-ish window |
| CL | `l10n_cl_edi` | folio range available |
| VN | 3rd-party (no Odoo connector) | MST, template code, series, XMLSignature |

## Hard rules (e-invoicing)

- Identify the framework edge before coding: `account_edi` is the base;
  `account_edi_ubl_cii` is UBL+CII (incl. Factur-X) — confirm the
  `depends` chain on the target major.
- Never run Odoo-official and OCA e-invoice stacks for the same country
  together.
- EU intra-community: validate the buyer VAT via VIES (`base_vat`) before
  applying reverse charge.
- FR: never allow `secure_sequence_number` / `inalterable_hash` to be null
  on a posted move.
- MX: never bypass the PAC; CL: never let folios run out; CO: respect the
  DIAN submission window.
- VN: never delete a posted invoice — cancel + reissue with a replacement
  link; never ship without verifying provider + signing cert are wired.

## Sources verified

- `account_edi` manifest, branch 17.0 and 16.0 (name, `depends:[account]`).
  `https://github.com/odoo/odoo/blob/17.0/addons/account_edi/__manifest__.py`
- `account_edi_ubl_cii` manifest, branch 17.0 (`depends:[account]`;
  UBL/CII, BIS3, XRechnung, NLCIUS, EHF3, E-FFF, Factur-X PDF/A-3) +
  directory present on branch 18.0.
  `https://github.com/odoo/odoo/blob/17.0/addons/account_edi_ubl_cii/models/account_edi_xml_ubl_bis3.py`
- Electronic invoicing (EDI) docs, 14.0 and 17.0 — format list (Factur-X,
  Peppol BIS3, XRechnung, NLCIUS, EHF3, FatturaPA, CFDI 4.0, SII…),
  Peppol access-point / `account_peppol`.
- Italy fiscal localization 19.0 + Apps Store — `l10n_it_edi`, SdI,
  FatturaPA; OCA `l10n_it_fatturapa`, `l10n_it_sdi_channel`.
- Spain SII — odoo.com blog + Apps Store `l10n_es_edi_sii` /
  `l10n_es_aeat_sii`.
- Factur-X / OCA `l10n_fr_account_invoice_facturx` — Apps Store + OCA.
