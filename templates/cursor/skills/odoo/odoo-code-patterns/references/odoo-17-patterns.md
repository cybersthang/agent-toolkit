# Odoo 17 — pattern deltas (head of 17→18→19→20 cascade)

Load this when Step 0 detected major = **17** (or **16** as transitional
with a LOW flag). The Odoo 18 / 19 / 20 references cascade *on top of*
this file — they override only the deltas.

## Compute + CRUD — recordset is the default

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

Key changes vs. Odoo 12:
- `@api.multi` is REMOVED. Recordset is the default — every method that
  iterates `self` already operates on a recordset.
- `create()` takes a LIST of vals dicts and is decorated with
  `@api.model_create_multi(vals_list)`. Single-record `@api.model` form
  on `create()` silently breaks batch inserts.
- `name_get()` is deprecated (still works in 17, gone-by-default in 18).
  Use `_compute_display_name()` going forward.

## Wizard — no decorator on action methods

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

## View — `invisible="<expr>"` directly on `<field>`

```xml
<xpath expr="//field[@name='partner_id']" position="after">
  <field name="custom_field"
         invisible="state == 'done'"
         readonly="state == 'done'"
         required="not state"/>
</xpath>
```

- `attrs="{...}"` is **REMOVED in Odoo 17** — using it raises a parse
  error.
- `states="..."` is **REMOVED in Odoo 17**.
- Use Python expressions directly as the attribute value.

## Frontend — OWL component

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

The `/** @odoo-module **/` header is the OWL signal — never omit it.
`web.Widget` / jQuery patterns from Odoo 12 do not work here.

## Hard rules (Odoo 17 specific)

- Never `@api.multi` — gone.
- Never single-record `@api.model` `create(vals)` — use `@api.model_create_multi(vals_list)`.
- Never `attrs="{...}"` or `states="..."` — both removed.
- Never `web.Widget` / jQuery for frontend in new code — OWL only.
- Controller route type is still `'json'` in 17 — see `odoo-19-patterns.md`
  for the rename to `'jsonrpc'`.
