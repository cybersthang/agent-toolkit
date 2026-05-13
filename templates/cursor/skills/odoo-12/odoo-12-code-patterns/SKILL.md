---
name: odoo-12-code-patterns
description: Canonical Odoo 12 patterns — model, mixin, delegation, compute, wizard, report, controller, cron, view inheritance. Module-agnostic; copy the snippet that fits, do not paste an entire file into chat.
---

# Odoo 12 — Patterns

ORM, performance and view rules belong in `odoo-12-backend.mdc`. This skill is **patterns only**.

## Models

- **Inherit by name**: `_inherit = 'res.partner'` — extend an existing model.
- **Mixin (abstract)**: `models.AbstractModel` + `_name = '<x>.mixin'`.
- **Delegation**: `_inherits = {'res.partner': 'partner_id'}` — composition with all fields exposed.
- **Compute**: `@api.depends(...)` + `@api.multi` loop. Add `inverse=` only if the field is editable.
- **CRUD overrides**: `super()` first, validate, then post-process. Raise `UserError` for business rules.

## Wizard

```python
class MyWiz(models.TransientModel):
    _name = 'my.wiz'

    target_date = fields.Date(required=True)

    @api.multi
    def action_run(self):
        self.ensure_one()
        active_ids = self.env.context.get('active_ids') or []
        records = self.env['target.model'].browse(active_ids)
        records.write({'date': self.target_date})
        return {'type': 'ir.actions.act_window_close'}
```

## Report / Controller / Cron

- **Report**: `models.AbstractModel` + `_get_report_values(self, docids, data)`.
- **Controller**: `@http.route('/path', type='json', auth='user')` + always validate input.
- **Cron**: `ir.cron` record + `@api.model` method on the model.

## View inheritance

```xml
<record id="view_x_form_inherit" model="ir.ui.view">
  <field name="name">x.form.inherit</field>
  <field name="model">sale.order</field>
  <field name="inherit_id" ref="sale.view_order_form"/>
  <field name="arch" type="xml">
    <xpath expr="//field[@name='partner_id']" position="after">
      <field name="custom_field"/>
    </xpath>
  </field>
</record>
```

## Performance shortcuts

- Dict lookup: `by_id = {p.id: p for p in records}`.
- Aggregations: `env['model'].read_group(domain, fields, groupby, lazy=False)`.
- Counts: `env['model'].search_count(domain)` (never `len(search(...))`).
- Batch ORM ops: `records.write({...})` once, not per record in a loop.

## Hard rules

- Never declare `_name` and `_inherit` to the same string in the same class — that is delegation, not inheritance.
- Never put `search()` / `browse(id)` inside a Python loop.
- Never edit XML inheritance arch without an `xpath` expression (replacing root tags breaks downstream inheritances).
