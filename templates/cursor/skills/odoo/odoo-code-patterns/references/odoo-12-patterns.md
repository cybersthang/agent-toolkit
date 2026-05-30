# Odoo 12 — pattern deltas (standalone)

Standalone reference: 12 does NOT cascade from 17. Load this when Step 0
detected major = **12**.

## Compute + CRUD — recordset is NOT default

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
    @api.multi
    def _compute_total(self):
        for record in self:
            record.total = sum(record.line_ids.mapped('price'))

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._post_create_hook()
        return record
```

Key rules:
- `@api.multi` on every method that iterates `self`.
- `@api.one` exists but is deprecated — never use in new code.
- `create()` override commonly takes ONE `vals` dict in 12-era code; loop
  yourself if you need batch behaviour. (`@api.model_create_multi` does exist
  in v12 and is the batch-safe form, but single-record overrides are typical here.)

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

## View — conditional visibility uses `attrs`

```xml
<xpath expr="//field[@name='partner_id']" position="after">
  <field name="custom_field"
         attrs="{'invisible': [('state','=','done')],
                 'readonly': [('state','=','done')]}"/>
</xpath>
```

`states="..."` is also legal in 12 for conditional visibility tied to a
state field. Both `attrs` and `states` are **removed in Odoo 17+**.

## Frontend — jQuery + web.Widget

```javascript
odoo.define('my_module.MyWidget', function (require) {
"use strict";

var Widget = require('web.Widget');
var AbstractWebClient = require('web.AbstractWebClient');

var MyWidget = Widget.extend({
    template: 'my_module.MyWidget',

    start: function () {
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            self.$('.btn').on('click', self._onClick.bind(self));
        });
    },
});

return MyWidget;
});
```

OWL does not exist in Odoo 12. Frontend is jQuery + QWeb templates.

## Hard rules (Odoo 12 specific)

- Always `@api.multi` on recordset-iterating methods.
- `create()` is single-record (`@api.model`, `vals` not `vals_list`).
- `attrs="{...}"` is the only way to do conditional visibility — direct
  `invisible="<expr>"` syntax does NOT work in 12.
- No OWL frontend — use jQuery + `web.Widget`.
- Controller route: `@http.route(..., type='json')` (renamed `'jsonrpc'`
  in 19+, but 12 uses `'json'`).
