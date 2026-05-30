# Community inventory — depth reference

Companion to `SKILL.md` §2 (Stock move chain reservation). All examples
use placeholders — discover real model names via
`codebase.search_model_definitions`.

## `stock.move` state machine

```
draft ──_action_confirm()──► confirmed ──_action_assign()──► assigned
  │                              │                              │
  │                              │ (no quants available)         │ _action_done()
  │                              │ stays at confirmed           │
  │                              ▼                              ▼
  │                          waiting (waiting for upstream)    done
  │                              │
  └─────────── _action_cancel() ──┴──► cancel
```

| State | Meaning | Community-specific note |
|---|---|---|
| `draft` | Created, not pushed to picking | Same on Enterprise |
| `confirmed` | Pushed; reservation attempt pending | Same |
| `waiting` | Blocked on upstream (e.g. MTO chain) | Enterprise auto-resolves via `mrp_workorder` planning; Community blocks until human intervention |
| `assigned` | Reserved against `stock.quant` | Same |
| `done` | Picked + delivered | Same |
| `cancel` | Cancelled (frees reservation) | Same |

## Reservation engine internals (Community-safe)

`stock.move._action_assign()` walks `move_line_ids` and for each move
calls `_get_available_quantity(location_id, ...)` which:

1. Searches `stock.quant` filtered by `location_id` (NOT just
   `product_id`) — this is the warehouse scope.
2. Applies the warehouse's removal strategy (FIFO / LIFO / FEFO from
   `stock.location.removal_strategy_id`).
3. Honors `lot_id` if the product is tracked by lot/serial.
4. Honors `owner_id` if the consignment module is active.

Multi-warehouse code that hand-rolls quant search MUST replicate all
four filters or fall back to delegating to `action_assign()`.

## Lot / serial tracking pitfalls

Community ships `stock_production_lot` (lot model) but NOT the
Enterprise `quality` / `stock_barcode` extensions. The common bug:

```python
# BAD: creates lot but doesn't link to the move_line
def receive_batch(self, picking, lot_name):
    lot = self.env['stock.production.lot'].create({
        'name': lot_name,
        'product_id': picking.move_ids[0].product_id.id,
        'company_id': picking.company_id.id,
    })
    picking.button_validate()  # validation fails: missing lot on move_line
```

```python
# GOOD: assign lot to move_line BEFORE button_validate
def receive_batch(self, picking, lot_name):
    move = picking.move_ids[0]
    lot = self.env['stock.production.lot'].create({
        'name': lot_name,
        'product_id': move.product_id.id,
        'company_id': picking.company_id.id,
    })
    # ensure a move_line exists; create if reservation didn't
    if not move.move_line_ids:
        move.move_line_ids = [(0, 0, {
            'product_id': move.product_id.id,
            'product_uom_id': move.product_uom.id,
            'location_id': move.location_id.id,
            'location_dest_id': move.location_dest_id.id,
            'qty_done': move.product_uom_qty,
        })]
    move.move_line_ids.write({'lot_id': lot.id})
    picking.button_validate()
```

## FIFO / FEFO removal strategy (Community)

Set on the **location** (not the product). The default `stock.location`
removal strategy is `inherit` from parent, which on the standard
`WH/Stock` resolves to FIFO. To enable FEFO (expiration-first), the
`product_expiry` module must be installed (it ships with Community in
recent majors — confirm availability on the target Odoo version
before assuming a fresh install has it).

```python
def set_fefo_for_warehouse(self, warehouse):
    if not self.env['ir.module.module']._installed('product_expiry'):
        raise UserError(_("Install product_expiry first"))
    fefo = self.env.ref('stock.removal_fefo')
    warehouse.lot_stock_id.write({'removal_strategy_id': fefo.id})
```

## Negative stock pitfall

Without `mrp_workorder` backflush guards, Community lets `stock.move`
go through with `qty_available < 0` if the reservation gate is
bypassed (e.g. force-validated picking). To detect:

```python
def find_negative_quants(self):
    return self.env['stock.quant'].search([
        ('quantity', '<', 0),
        ('location_id.usage', '=', 'internal'),
    ])
```

Treat any hit as a P0 — Community has no auto-correction.

## Sibling references

- `references/community-vs-enterprise-detection.md` — `_has_module()`.
- `odoo-multi-company` skill — `company_id` scoping for `stock.move`.
- `odoo-performance` skill — `stock.quant` table grows linearly with
  reservations; cite `odoo-performance` references for the indexing
  strategy on `(product_id, location_id, quantity)`.
