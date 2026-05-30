> odoo-14 reference (drafted v0.29). Deltas vs odoo-12-patterns.md web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

# Odoo 14 — pattern deltas (standalone)

Standalone reference: 14 does NOT cascade from 17. Load this when Step 0
detected major = **14**.

**Mental model**: Odoo 14 is much CLOSER to 17 than to 12 on the ORM/API
surface. `@api.multi` and `@api.one` were **removed in Odoo 13** (verified:
`odoo/odoo` 14.0 `odoo/api.py` has no `multi`/`one` decorator), so 14 is
recordset-by-default just like 17. The two big things that still look like
12 are the **view layer** (`attrs`/`states` are still the idiom) and the
**asset declaration** (XML inheriting `web.assets_backend`, not the
manifest `'assets'` dict). OWL exists but the web client is mostly the
legacy `web.Widget` framework.

## Compute + CRUD — recordset is the default (like 17, NOT like 12)

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

Key rules (verified against `odoo/odoo` 14.0 `odoo/api.py`,
`odoo/models.py`):
- **No `@api.multi`** — removed in 13. Methods iterate `self` (a recordset)
  by default; do NOT add `@api.multi` (import-time error). This is the
  biggest delta vs the v12 file.
- **No `@api.one`** — removed in 13.
- **`@api.model_create_multi`** EXISTS (api.py line ~356) and the base
  `create()` is `create(self, vals_list)`. The decorated method may be
  called with a single dict OR a list of dicts; it always receives a list.
  This is the recommended override form for new code in 14.
- `@api.model` still applies to class-level methods not bound to a
  recordset; `@api.depends`, `@api.constrains`, `@api.onchange`,
  `@api.depends_context`, `@api.returns` all present in 14.
- `ensure_one()` whenever a method assumes a single record.

## Wizard — no decorator on action methods (like 17)

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

No `@api.multi` (unlike the v12 wizard). Otherwise unchanged from
v12 — see odoo-12-patterns.md "Wizard".

## View — conditional visibility STILL uses `attrs` / `states` (like 12)

```xml
<xpath expr="//field[@name='partner_id']" position="after">
  <field name="custom_field"
         attrs="{'invisible': [('state','=','done')],
                 'readonly': [('state','=','done')]}"/>
</xpath>
```

Verified against `odoo/odoo` 14.0 `addons/base/models/ir_ui_view.py`
(parses `node.get('attrs')` and `node.get('states')`): both `attrs="{...}"`
and `states="..."` are the **correct, canonical** idiom in 14. The direct
`invisible="<py expr>"` form does NOT exist in 14 — that arrived with the
view-syntax overhaul in **Odoo 17**. So the view layer is unchanged from
v12 — see odoo-12-patterns.md "View".

## Frontend — jQuery + web.Widget is still the default; OWL is NEW

OWL was first shipped in **Odoo 14**, but in 14 the backend web client is
still mostly the legacy `web.Widget`/jQuery framework with OWL coexisting
behind a legacy-adapter. For most custom widgets in 14 you will still write
the legacy form:

```javascript
odoo.define('my_module.MyWidget', function (require) {
"use strict";

var Widget = require('web.Widget');

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

Delta vs v12: OWL components *do* exist in 14 (the `owl` runtime is
bundled — OWL **1.4.11**, verified `addons/web/static/lib/owl/owl.js` 14.0).
In 14 OWL is exposed as a **global namespace**, NOT an ES module: the
library is a UMD bundle ending in `(this.owl = this.owl || {})`, so a 14
component pulls the class via `const { Component } = owl;` — there is **no**
`import { Component } from "@odoo/owl"` in 14 (that ESM path is 15+). And
the `/** @odoo-module **/` header is a **no-op comment in 14** (the
transpiler that honors it arrived in 15 — see "Hard rules" below); a 14
component is still wrapped in `odoo.define(...)`. Verified against a real
14.0 component, `addons/mail/static/src/components/messaging_menu/messaging_menu.js`:

```javascript
odoo.define('my_module/static/src/components/my_widget/my_widget.js', function (require) {
'use strict';

const { Component } = owl;          // global owl namespace — NOT @odoo/owl
const { useState } = owl.hooks;     // hooks live under owl.hooks in 1.x

class MyWidget extends Component {}
MyWidget.template = 'my_module.MyWidget';

return MyWidget;
});
```

When in doubt for a 14 widget, prefer the legacy `web.Widget` form above
(always valid in 14).

## Hard rules (Odoo 14 specific)

- **Never `@api.multi` / `@api.one`** — removed in 13. Recordset is the
  default in 14.
- `create()` override should be `@api.model_create_multi` with a
  `vals_list` signature (single-record `@api.model create(vals)` still runs
  but loses batch semantics — flag as inconsistency).
- `attrs="{...}"` / `states="..."` are the ONLY way to do conditional
  visibility in 14 — the `invisible="<expr>"` direct syntax is 17+.
- Frontend: legacy `web.Widget`/jQuery is still the default in 14; OWL
  exists but is not yet the standard for custom backend widgets.
- Assets are declared via XML inheriting `web.assets_backend` — the
  manifest `'assets'` dict is **15+** (verified: assets dict introduced in
  Odoo 15). See odoo-14-scaffold.md.
- Controller route: `@http.route(..., type='json')` (renamed `'jsonrpc'`
  in 19+, but 14 uses `'json'`).
