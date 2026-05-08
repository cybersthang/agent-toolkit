---
name: odoo-17-code-patterns
description: Canonical Odoo 17 patterns — model, mixin, delegation, compute, wizard, report, controller, cron, view inheritance, OWL component. Module-agnostic; copy the snippet that fits, do not paste an entire file into chat.
---

# Odoo 17 — Patterns

ORM, performance and view rules belong in `odoo-17-backend.mdc`. This skill is **patterns only**.

## Models

- **Inherit by name**: `_inherit = 'res.partner'` — extend an existing model.
- **Mixin (abstract)**: `models.AbstractModel` + `_name = '<x>.mixin'`.
- **Delegation**: `_inherits = {'res.partner': 'partner_id'}` — composition with all fields exposed.
- **Compute**: `@api.depends(...)` — recordset is the default, no `@api.multi` needed.
- **CRUD overrides**: `super()` first, validate, then post-process. Use `@api.model_create_multi` for `create()`. Raise `UserError` for business rules.

## Compute and create

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

## Wizard

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

## Report / Controller / Cron

- **Report**: `models.AbstractModel` + `_get_report_values(self, docids, data)`.
- **Controller**: `@http.route('/path', type='json', auth='user')` + always validate input.
- **Cron**: `ir.cron` record + a method on the model (no `@api.model` needed if it operates on a recordset).

## View inheritance (Odoo 17 syntax)

```xml
<record id="view_x_form_inherit" model="ir.ui.view">
  <field name="name">x.form.inherit</field>
  <field name="model">sale.order</field>
  <field name="inherit_id" ref="sale.view_order_form"/>
  <field name="arch" type="xml">
    <xpath expr="//field[@name='partner_id']" position="after">
      <field name="custom_field" invisible="state == 'done'"/>
    </xpath>
  </field>
</record>
```

> **Note:** Odoo 17 uses `invisible="<expr>"`, `readonly="<expr>"`, `required="<expr>"` directly as Python expressions. **Do not** use `attrs="{...}"` or `states="…"` — both are removed.

## OWL component (frontend)

```javascript
/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class MyWidget extends Component {
    static template = "my_module.MyWidget";

    setup() {
        this.orm = useService("orm");
        this.state = useState({ records: [] });
        onWillStart(async () => {
            this.state.records = await this.orm.searchRead("my.model", [], ["id", "name"]);
        });
    }
}

registry.category("actions").add("my_module.my_widget", MyWidget);
```

## Performance shortcuts

- Dict lookup: `by_id = {p.id: p for p in records}`.
- Aggregations: `env['model'].read_group(domain, fields, groupby, lazy=False)`.
- Counts: `env['model'].search_count(domain)` (never `len(search(...))`).
- Batch ORM ops: `records.write({...})` once, not per record in a loop.

## Hard rules

- Never declare `_name` and `_inherit` to the same string in the same class — that is delegation, not inheritance.
- Never put `search()` / `browse(id)` inside a Python loop.
- Never edit XML inheritance arch without an `xpath` expression.
- Never override `create()` with single-record `@api.model` form — use `@api.model_create_multi(vals_list)` or batch creates will silently break.
- Never introduce `@api.multi`, `attrs="{...}"`, or `states="…"` — all three are removed in Odoo 17.
