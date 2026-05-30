# Odoo 13/14 — the `account.invoice` → `account.move` unification

Load this when Step 0 detected major **13–16**. The unification is a
**two-step** change — get the version split right or you'll write code
that crashes on the exact version you're targeting.

> Verified against `github.com/odoo/odoo` branches `13.0` and `14.0`,
> `addons/account/models/account_move.py`.

## The unification happened in **v13**, the rename in **v14**

| Fact | Version | Source branch |
|---|---|---|
| `account.invoice` / `.line` / `.tax` **removed**; merged into `account.move` / `account.move.line` | **13.0** | 13.0 |
| Invoice type field on `account.move` = `type` | **13.0** | 13.0 |
| Type field **renamed** `type` → `move_type` | **14.0** | 14.0 |
| Payment field `invoice_payment_state` (3 values) | **13.0** | 13.0 |
| Renamed `invoice_payment_state` → `payment_state`, expanded to 6 values | **14.0** | 14.0 |

So on **13** the selector is `type`; on **14+** it is `move_type`.
Branching on the wrong name is a silent `KeyError` / empty domain.

## `account.invoice` is GONE on v13+

```python
# v13+ — KeyError at load: model removed
self.env['account.invoice']                     # KeyError
self.env['account.invoice.line']                # KeyError
self.env['account.invoice.tax']                 # KeyError
```

```python
# v13+ — the survivors
self.env['account.move']                        # invoices + bills + journal entries
self.env['account.move.line']                   # invoice lines AND tax lines AND JE lines
```

Migrate `_inherit = 'account.invoice'` → `_inherit = 'account.move'`.
Tax lines are no longer a separate model — they are `account.move.line`
records with `tax_line_id` set (vs `tax_ids` on base product lines).

## `move_type` — 7 values (note `entry` + receipts)

```python
# v14+ — account.move.move_type  (v13: same values, field named `type`)
move_type = fields.Selection([
    ('entry',       'Journal Entry'),       # NOT invoice-shaped
    ('out_invoice', 'Customer Invoice'),
    ('out_refund',  'Customer Credit Note'),
    ('in_invoice',  'Vendor Bill'),
    ('in_refund',   'Vendor Credit Note'),
    ('out_receipt', 'Sales Receipt'),
    ('in_receipt',  'Purchase Receipt'),
], default='entry')
```

`account.move` now holds *every* journal entry, so `entry` means "not an
invoice". Always filter `move_type` before treating a move as an invoice
(or use the helpers below).

## `state` — only 3 values (no more `open`)

```python
# v13+ — account.move.state
state = fields.Selection([
    ('draft',  'Draft'),
    ('posted', 'Posted'),
    ('cancel', 'Cancelled'),
], default='draft')
```

The legacy `open` / `proforma` / `paid` invoice states are gone.
"Validated" is `state='posted'`; "paid" moves to the payment field.

## Payment state — renamed + expanded in v14

```python
# v13 — 3 values, field name invoice_payment_state
invoice_payment_state = fields.Selection([
    ('not_paid', 'Not Paid'), ('in_payment', 'In Payment'), ('paid', 'Paid'),
])

# v14+ — renamed payment_state, 6 values
PAYMENT_STATE_SELECTION = [
    ('not_paid',          'Not Paid'),
    ('in_payment',        'In Payment'),
    ('paid',              'Paid'),
    ('partial',           'Partially Paid'),       # new in v14
    ('reversed',          'Reversed'),             # new in v14
    ('invoicing_legacy',  'Invoicing App Legacy'), # new in v14
]
```

Never treat it as a boolean (every move has a value) — enumerate against
the known set. See SKILL §3.

## Type helpers already exist in v13+ (NOT a v17 feature)

```python
# v13 reads `type`; v14+ identical but reads `move_type`
def is_invoice(self, include_receipts=False):
    return self.move_type in self.get_invoice_types(include_receipts)
# is_sale_document() / is_purchase_document() / is_inbound() / is_outbound() also present
```

Prefer these over hardcoded tuples on **all** of v13–16, not just v17.

## Create an invoice (v14+)

```python
# v14+ — one model, move_type selector, model_create_multi enabled
moves = self.env['account.move'].create([{
    'move_type': 'out_invoice',             # v13: key is `type`
    'partner_id': partner.id,
    'invoice_date': fields.Date.today(),
    'invoice_line_ids': [(0, 0, {
        'product_id': product.id,
        'quantity': 1,
        'price_unit': 100.0,
        'tax_ids': [(6, 0, tax.ids)],       # was invoice_line_tax_ids on v12
    })],
}])
moves.action_post()                         # draft -> posted (was action_invoice_open)
```

- `account.move` supports batch `create([...])` (`@api.model_create_multi`).
- Validate with `action_post()`, not `action_invoice_open()`.
- Base-line tax field is `tax_ids`; `account_id` is auto-derived from the
  product/journal (no longer required per line).

## Credit note (v14+)

```python
# v14+ — reversal wizard or direct create with reversed_entry_id
self.env['account.move'].create({
    'move_type': 'out_refund',
    'partner_id': invoice.partner_id.id,
    'reversed_entry_id': invoice.id,        # replaces v12 origin_invoice_ids
})
# or: self.env['account.move.reversal'] wizard
```

## Tax recompute (v13–16 — NO `_compute_taxes()` on the move)

```python
# v13 — recompute machinery is on account.move:
move._recompute_dynamic_lines(recompute_all_taxes=True)   # v13/14/15
# v16 refactored this into a context manager: account.move._sync_dynamic_line(...)
```

There is **no** `account.move._compute_taxes()` on v13–16. Portable
pattern: mutate `invoice_line_ids` via ORM, let the onchange/compute
chain (or a draft→post round-trip) re-derive totals; never assign
`amount_total` / `amount_tax` directly (computed fields). The named
`_compute_taxes(base_lines)` engine is a v17 `account.tax` method — see
`odoo-17-account-refinements.md`.

## Tax-totals display field renamed across versions

| Field | Versions |
|---|---|
| `amount_by_group` | 13 |
| `tax_totals_json` (Char/JSON) | 14, 15 |
| `tax_totals` (Binary, computed) | 16+ |

QWeb/JS reading the totals widget must use the right field name per
target version.

## Hard rules (v13–16)

- `account.invoice*` models are **removed** in v13 — any reference
  crashes on load. Migrate to `account.move` / `account.move.line`.
- v13 selector is `type`; **v14+ is `move_type`**. Match the target
  branch exactly.
- `state` is `draft/posted/cancel` — `open` is dead. Use
  `state='posted'` + `payment_state`.
- v13 payment field is `invoice_payment_state` (3 values); **v14+ is
  `payment_state` (6 values)**.
- `is_invoice()` / `is_sale_document()` / `is_purchase_document()` exist
  since v13 — use them instead of hardcoded `move_type` tuples.
- No `account.move._compute_taxes()` here — use
  `_recompute_dynamic_lines()` (≤15) / dynamic-line sync (16), or a
  draft→post round-trip; never assign totals directly.
