# Odoo 17 — accounting refinements (tax engine, helpers, totals)

Load this when Step 0 detected major **17+**. The unification (v13) and
the `move_type` rename (v14) are assumed done — see
`odoo-14-account-move-unification.md`. This file covers what changed
*after* the merge stabilised.

> Verified against `github.com/odoo/odoo` branches `16.0`, `17.0`, `18.0`,
> `addons/account/models/account_tax.py` + `account_move.py`, and
> `odoo.com/documentation/17.0/.../accounting/taxes.html`.

## `_compute_taxes()` is on `account.tax`, not `account.move`

This is the most-mis-stated v17 fact. There is **no** parameterless
`account.move._compute_taxes()`. The real method is the generic tax
engine on `account.tax`:

```python
# v17 — account.tax (engine), takes prepared base_lines
@api.model
def _compute_taxes(self, base_lines, tax_lines=None,
                   handle_price_include=True, include_caba_tags=False):
    ...
```

`account.move` builds `base_lines` from its `invoice_line_ids`
internally and calls this engine; you rarely call `_compute_taxes()`
directly on `account.move`. On v17 the legacy `account.tax.compute_all()`
(single price_unit) still exists alongside it.

```python
# v17 — single-price legacy path still present on account.tax
def compute_all(self, price_unit, currency=None, quantity=1.0, product=None,
                partner=None, is_refund=False, handle_price_include=True,
                include_caba_tags=False, fixed_multiplicator=1):
    ...
```

### Safe/stable recompute pattern (any v14+)

Don't reach for engine internals. Mutate lines via the ORM and let the
move re-derive its computed totals:

```python
# v14+ portable — never assign amount_total/amount_tax (computed fields)
move.invoice_line_ids = [(1, line.id, {'price_unit': new_price})
                          for line, new_price in updates]
move.invalidate_recordset(['amount_total', 'amount_tax', 'amount_untaxed'])
total = move.amount_total            # recomputed on read
# robust alternative: draft -> action_post() round-trip re-derives tax lines
```

This survives every tax-engine refactor (v13 `_recompute_dynamic_lines`,
v16 `_sync_dynamic_line`, v17 base-lines engine, v18 rewrite below).

## v18 went further — `compute_all()` removed

If the manifest says 18+, do NOT assume the v17 surface:

```python
# v18 — base_line dicts; compute_all() is GONE
def _prepare_base_line_for_taxes_computation(self, record, **kwargs):
    ...
# helpers: _add_tax_details_in_base_line(), _batch_for_taxes_computation(),
#          _get_tax_details()
```

The new architecture builds explicit `base_line` dicts. Code calling
`compute_all()` breaks on v18. Re-check the target major's account_tax.py
before pattern-matching — flag LOW and verify.

## Rounding + price-include (concepts confirmed v17)

`account.tax` rounding is driven by the company's tax calculation
rounding method:

| `Company.tax_calculation_rounding_method` | Effect |
|---|---|
| `round_per_line` | round each line's tax, then sum (default) |
| `round_globally` | sum exact taxes, round once at the end |

`account.tax.price_include` ("Included in Price"): the price *is* the
tax-inclusive total; the engine splits it into base + tax. Manual
`subtotal * 1.10` math ignores this split and the rounding strategy →
off-by-cent drift on multi-line / mixed-tax / price-included invoices.
Always let the engine compute. (Confirmed in the v17 Taxes docs.)

## Tax-totals field is `tax_totals` (since v16, NOT new in v17)

```python
# v16+ — account.move
tax_totals = fields.Binary(
    string="Invoice Totals",
    compute='_compute_tax_totals',
    inverse='_inverse_tax_totals',
    exportable=False,
)
```

Rename timeline: `amount_by_group` (v13) → `tax_totals_json` Char
(v14–15) → `tax_totals` Binary (v16+). So on v17 the field is
`tax_totals`; a v14/15 module forward-ported here that reads
`tax_totals_json` gets `False`. Read totals from the computed money
fields (`amount_untaxed` / `amount_tax` / `amount_total`) instead of the
display widget field where possible.

## `move_type` helpers — same names, use them on v17

```python
# v13+ (identical on v17) — prefer over hardcoded move_type tuples
move.is_invoice(include_receipts=True)      # out/in_invoice, out/in_refund (+receipts)
move.is_sale_document()                     # out_invoice, out_refund (+out_receipt)
move.is_purchase_document()                 # in_invoice, in_refund (+in_receipt)
move.is_inbound()                           # money in
move.is_outbound()                          # money out
```

These are NOT new in v17 (present since v13) — but v17 is where
consultancies finally adopt them, so the lint nudge lives here. See
SKILL §4.

## State + payment_state unchanged from v14

```python
# v17 — same as v14+
# state:         draft / posted / cancel
# payment_state: not_paid / in_payment / paid / partial / reversed / invoicing_legacy
```

No `open`. `payment_state` is still a 6-value Selection — never a bool.

## Falsification recipes (v17)

```python
# 1. Confirm the engine method lives on account.tax, not account.move
hasattr(self.env['account.tax'], '_compute_taxes')      # True on v17+
hasattr(self.env['account.move'], '_compute_taxes')     # False — it's the engine's
# 2. Confirm legacy single-price path on this branch
hasattr(self.env['account.tax'], 'compute_all')         # True v17, False v18+
# 3. Confirm totals field name on this branch
'tax_totals' in self.env['account.move']._fields        # True v16+
'tax_totals_json' in self.env['account.move']._fields   # True only v14/15
# 4. Drift probe — totals after recompute must equal your manual math
before = move.amount_total
move.invalidate_recordset(['amount_total'])
assert before == move.amount_total, "manual math drifted from engine"
```

## Hard rules (v17+)

- `_compute_taxes(base_lines, ...)` is an **`account.tax`** engine method,
  not a parameterless `account.move` recompute. Don't invent
  `move._compute_taxes()`.
- Preferred recompute: mutate `invoice_line_ids` via ORM →
  `invalidate_recordset(...)` → read totals, or draft→post round-trip.
  Never assign `amount_total` / `amount_tax` directly.
- Never hand-roll `subtotal * rate` — it ignores rounding method and
  `price_include`.
- Totals display field is `tax_totals` (v16+); `tax_totals_json` is dead
  on v17.
- v18 removes `compute_all()` and rewrites the engine around
  `_prepare_base_line_for_taxes_computation()` — re-verify on 18+.
- `is_invoice()` / `is_sale_document()` / `is_purchase_document()` —
  prefer over hardcoded `move_type` tuples.
- `state` (draft/posted/cancel) and `payment_state` (6 values) are
  unchanged from v14 — no `open`, never bool.
