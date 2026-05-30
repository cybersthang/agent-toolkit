# Odoo 13 — pattern deltas (standalone)

> odoo-13 reference (drafted v0.29). Deltas vs odoo-12-patterns.md web-verified where cited; `<!-- VERIFY -->` items need DEV confirmation.

Standalone reference: 13 does NOT cascade from 17. Load this when Step 0
detected major = **13**. Odoo 13 is close to v12 EXCEPT for a large ORM
refactor — `@api.multi`/`@api.one` are **gone**, and `create()` is now
multi-record. Frontend and views are still v12-shaped.

## Compute + CRUD — recordset is the default, `@api.multi` is REMOVED

```python
from odoo import api, fields, models
from odoo.exceptions import UserError


class MyModel(models.Model):
    _name = 'my.model'
    _description = 'My Model'

    name = fields.Char(required=True)
    line_ids = fields.One2many('my.line', 'parent_id')
    total = fields.Monetary(compute='_compute_total', store=True)

    @api.depends('line_ids.price')
    def _compute_total(self):
        for record in self:
            record.total = sum(record.line_ids.mapped('price'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._post_create_hook()
        return records
```

Key changes vs. Odoo 12 (verified against `odoo/odoo` 13.0 `odoo/api.py`
and `odoo/models.py`):
- `@api.multi`, `@api.one`, `@api.cr`, `@api.model_cr`, `@api.returns`'s
  positional sibling — `multi`/`one` are **absent from `odoo/api.py` in
  13.0** (not no-ops, removed). Methods iterate `self` by default; loop
  with `for rec in self:`. (Source: 13.0 `odoo/api.py` defines only
  `model`, `model_create_single`, `model_create_multi`, `depends`,
  `depends_context`, `constrains`, `onchange`, `returns`.)
- `@api.returns` is **still present** in 13.0 `odoo/api.py` — keep it on
  methods like `name_create` overrides that must return a recordset.
- `BaseModel.create` in 13.0 is decorated `@api.model_create_multi` and
  takes `vals_list` (Source: 13.0 `odoo/models.py` line ~3724). Override
  with `@api.model_create_multi` + `vals_list`. The single-record
  `@api.model` `create(vals)` form still *works* (the decorator
  normalises a single dict) but breaks batch inserts — prefer the multi
  form in new code. `@api.model_create_single` exists for the rare case
  you must keep single-record semantics.
- `@api.depends_context(...)` is available in 13.0 (`odoo/api.py`
  line ~209) — use it for company/locale-sensitive computes (see
  multi-company reference).

## Wizard — no `@api.multi` decorator

```python
class MyWiz(models.TransientModel):
    _name = 'my.wiz'

    target_date = fields.Date(required=True)

    def action_run(self):
        self.ensure_one()
        active_ids = self.env.context.get('active_ids') or []
        records = self.env['target.model'].browse(active_ids)
        records.write({'date': self.target_date})
        return {'type': 'ir.actions.act_window_close'}
```

Delta vs v12: drop the `@api.multi` decorator (it no longer exists). The
body is otherwise identical.

## Accounting — `account.invoice` is GONE, merged into `account.move`

In 13.0 `account.invoice`, `account.invoice.line` and
`account.invoice.tax` were **removed** and merged into `account.move` /
`account.move.line` (Source: 13.0 PR #33797; `addons/account/models/account_move.py`).

```python
# v13 — create a customer invoice via account.move (NOT account.invoice)
move = self.env['account.move'].create({
    'type': 'out_invoice',            # NOT 'move_type' — see note below
    'partner_id': partner.id,
    'invoice_line_ids': [(0, 0, {
        'product_id': product.id,
        'quantity': 1,
        'price_unit': 100.0,
    })],
})
move.action_post()                    # replaces account.invoice.invoice_validate / confirm wizard
```

- The discriminator field on `account.move` in 13.0 is **`type`**
  (values `entry`, `out_invoice`, `in_invoice`, `out_refund`,
  `in_refund`, `out_receipt`, `in_receipt`). Source: 13.0
  `account_move.py` line ~106 `type = fields.Selection(...)`. The rename
  to **`move_type`** happens in **v14**, not 13 — do NOT use `move_type`
  in v13 code.
- Invoice lines live on `invoice_line_ids` (One2many to
  `account.move.line`, Source: line ~214).
- `account.invoice.confirm` and `account.invoice.refund` wizards were
  removed; refunds go through `account.move.reversal` (action
  `account.action_view_account_move_reversal`). Source: 13.0
  `account_move.py` line ~2436.

See `odoo-account-move-overhaul/SKILL.md` for the full migration surface.

## View — conditional visibility uses `attrs` / `states`

Unchanged from v12 — see odoo-12-patterns.md §"View — conditional
visibility uses `attrs`". `attrs="{...}"` and `states="..."` are the
**correct** v13 idioms (verified: removed only in 17+). Direct
`invisible="<expr>"` syntax does NOT work in 13.

## Frontend — jQuery + web.Widget

Unchanged from v12 — see odoo-12-patterns.md §"Frontend — jQuery +
web.Widget". The 13.0 web client is still `odoo.define(...)` +
`web.Widget` + QWeb; assets register via XML inheritance of
`web.assets_backend` / `web.assets_frontend`. OWL ships in the 13.0
source tree but the backend web client is NOT built on it — treat
new-code frontend exactly as v12 (jQuery), not as v17 (OWL).

## Hard rules (Odoo 13 specific)

- Never `@api.multi` / `@api.one` — both removed in 13. Iterate `self`.
- `create()` → `@api.model_create_multi` + `vals_list` in new overrides.
- Accounting: use `account.move` (+ field `type`, `invoice_line_ids`),
  never `account.invoice` / `account.invoice.line`.
- `attrs="{...}"` is the only conditional-visibility syntax (NOT v17
  Python-expression attributes).
- No OWL for frontend — jQuery + `web.Widget`, assets via XML.
- Controller route type is `'json'` (unchanged from v12; renamed
  `'jsonrpc'` only in 19+).
