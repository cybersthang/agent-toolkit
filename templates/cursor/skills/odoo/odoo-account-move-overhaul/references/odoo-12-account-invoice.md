# Odoo 12 — legacy `account.invoice` (pre-unification)

Load this when Step 0 detected major = **12**. On 12, invoices live in
their own `account.invoice` model — the unification into `account.move`
has NOT happened yet (that's v13, see `odoo-14-account-move-unification.md`).

> Verified against `github.com/odoo/odoo` branch `12.0`,
> `addons/account/models/account_invoice.py`.

## The three legacy models

| Model | Replaced in v13 by |
|---|---|
| `account.invoice` | `account.move` |
| `account.invoice.line` | `account.move.line` |
| `account.invoice.tax` | `account.move.line` (tax lines are just move lines) |

A posted invoice in v12 generates a **separate** `account.move` (the
journal entry) via `invoice.move_id`. Two records, kept in sync. v13
collapses them into one.

## `account.invoice.type` — 4 values (no `entry`, no receipts)

```python
# v12 — account.invoice.type
type = fields.Selection([
    ('out_invoice', 'Customer Invoice'),
    ('in_invoice',  'Vendor Bill'),
    ('out_refund',  'Customer Credit Note'),
    ('in_refund',   'Vendor Credit Note'),
], default=lambda self: self._context.get('type', 'out_invoice'))
```

- Field is `type` (not `move_type` — that rename is v14).
- No `entry` value: an `account.invoice` is *always* invoice-shaped.
- No `out_receipt` / `in_receipt` (those arrive on `account.move` in v13).

## `account.invoice.state` — 5 values incl. `open`

```python
# v12 — account.invoice.state
state = fields.Selection([
    ('draft',      'Draft'),
    ('open',       'Open'),        # validated, unpaid — REMOVED in v13+
    ('in_payment', 'In Payment'),
    ('paid',       'Paid'),
    ('cancel',     'Cancelled'),
], default='draft')
```

Validation/payment lifecycle is encoded in `state` itself. This is why
v12/v13 code branches on `state == 'open'` — it means "validated &
unpaid". On v14+ that concept splits into `state='posted'` +
`payment_state in ('not_paid','partial')` (see §2 of SKILL).

## Compute + workflow (v12 API)

```python
from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi                              # v12 needs @api.multi
    def action_invoice_open(self):
        # draft -> open ; posts the linked account.move
        return super().action_invoice_open()

    @api.one
    @api.depends('invoice_line_ids.price_subtotal', 'tax_line_ids.amount')
    def _compute_amount(self):
        # v12: amount_untaxed / amount_tax / amount_total recomputed here
        ...
```

- `@api.multi` on recordset methods (dropped as a no-op in v13+).
- Tax lines recomputed via the `@api.onchange('invoice_line_ids', ...)`
  handlers + `compute_taxes()` button, NOT a unified line-sync engine.

## Creating an invoice (v12)

```python
# v12 — single-vals create on account.invoice
inv = self.env['account.invoice'].create({
    'partner_id': partner.id,
    'type': 'out_invoice',                  # field is `type`
    'invoice_line_ids': [(0, 0, {
        'product_id': product.id,
        'quantity': 1,
        'price_unit': 100.0,
        'invoice_line_tax_ids': [(6, 0, tax.ids)],   # NB: invoice_line_tax_ids
        'account_id': income_account.id,             # required on v12 lines
    })],
})
inv.action_invoice_open()                   # validate -> state 'open'
```

- Line tax field is `invoice_line_tax_ids` (v14+ uses `tax_ids` on
  `account.move.line`).
- Each line needs an explicit `account_id` on v12.

## Refund / credit note (v12)

```python
# v12 — dedicated wizard, NOT a move_type on create
wiz = self.env['account.invoice.refund'].with_context(
    active_ids=invoice.ids,
).create({'filter_refund': 'refund', 'description': 'RMA'})
wiz.invoice_refund()
```

`account.invoice.refund` wizard is **gone** in v13+; refunds become
`account.move` with `move_type='out_refund'` + `reversed_entry_id`
(or the `account.move.reversal` wizard).

## Payment state lookup (v12)

```python
# v12 — unpaid validated customer invoices
self.env['account.invoice'].search([
    ('type',  '=', 'out_invoice'),
    ('state', '=', 'open'),                 # valid ONLY on v12/v13-invoice
])
```

## Hard rules (Odoo 12 specific)

- Model is `account.invoice` (+ `.line`, `.tax`) — exists and is correct
  on 12. Migrating to v13+? It is **removed** — see
  `odoo-14-account-move-unification.md`.
- Field is `type`, not `move_type`. Don't forward-port `move_type` into
  v12 code — the field does not exist.
- `state == 'open'` is the v12 "validated & unpaid" marker. Legitimate
  here; a **dead filter** on v14+.
- Line tax field is `invoice_line_tax_ids`; lines require `account_id`.
- `@api.multi` on every recordset method (and `@api.one` is deprecated —
  don't introduce it).
- Refunds go through the `account.invoice.refund` wizard, not a create
  with `move_type`.
- Invoice and its journal entry are two records linked by
  `invoice.move_id` — they merge into one in v13.
