# Odoo 15 — pattern deltas (standalone, transitional)

> odoo-15 reference (drafted v0.29). Deltas vs odoo-12 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Standalone reference: 15 does NOT cascade from 17. Load this when Step 0
detected major = **15**. Nearest-neighbour template is v12, but v15 sits
in the middle: the **ORM/decorator surface already matches v17** while
the **view syntax still matches v12**. Read the deltas carefully.

## Compute + CRUD — recordset is default, `@api.multi` is GONE

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

DELTA vs v12 (these are the v17-style idioms, already true in v15):
- `@api.multi` is **REMOVED** — removed in Odoo 13, so it does not exist
  in v15. Recordset is the default; do NOT add it
  (basis: api decorators removed in v13, web-verified).
- `create()` takes a **LIST** of vals dicts with `@api.model_create_multi`
  (introduced v14, present in v15). The single-record `@api.model`
  `create(vals)` v12 form silently breaks batch inserts here.
- `@api.one` — removed in v13; not available.

## Wizard — no `@api.multi` on action methods

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

DELTA vs v12: no `@api.multi` decorator (see above).

## View — conditional visibility STILL uses `attrs` (UNCHANGED from v12)

```xml
<xpath expr="//field[@name='partner_id']" position="after">
  <field name="custom_field"
         attrs="{'invisible': [('state','=','done')],
                 'readonly': [('state','=','done')]}"/>
</xpath>
```

`attrs="{...}"` and `states="..."` are the **correct v15 idioms** — both
are removed only in **Odoo 17**, so they remain valid in v15
(web-verified: "Since 17.0, attrs and states are no longer used"). The
direct `invisible="<expr>"` Python-expression form does NOT work in v15.
Unchanged from v12 — see odoo-12-patterns.md "View" section.

## Frontend — TRANSITIONAL: OWL (1.x era) introduced, jQuery still present

v15 is the first version where you write OWL components in custom modules,
but the legacy `web.Widget` / jQuery stack is still shipped and used by
core. Both coexist.

NEW in v15 — the `/** @odoo-module **/` ES6-style module header. This
replaces `odoo.define(...)` (which still works) and is transpiled
server-side by `odoo/tools/js_transpiler.py` (NOT Babel) — web-verified.

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";

const { Component, useState } = owl;   // OWL exposed on the global `owl`

class MyWidget extends Component {
    setup() {
        this.state = useState({ records: [] });
    }
}
MyWidget.template = "my_module.MyWidget";  // template carries owl="1" attr

registry.category("actions").add("my_module.my_widget", MyWidget);
```

v15 OWL specifics (web-verified deltas vs the v17 template):
- OWL is the **1.x era** in v15; the global is `owl` (e.g.
  `const { useState } = owl.hooks;` / `owl.Component`). The modern
  `import { Component } from "@odoo/owl"` package import is the **OWL 2 /
  v16+** form — do NOT use it in v15.
  <!-- VERIFY(odoo-15): exact bundled OWL version string (docs say "all versions since 14 share the same Owl version" but do not print the number; confirm it is a 1.x tag, not 2.x) -->
- OWL QWeb templates must carry the `owl="1"` attribute on the root
  `<templates>`/`<t>` node (web-verified, 15.0 owl_components docs).
- Components register via `registry.category("<cat>").add(...)` — same
  registry mechanism that carries into v17.

The v12 jQuery `web.Widget.extend({...})` pattern is STILL valid in v15
for legacy widgets — see odoo-12-patterns.md "Frontend" section.

## Manifest assets — NEW `assets` dict (vs v12 XML asset records)

```python
'assets': {
    'web.assets_backend': [
        'my_module/static/src/js/my_widget.js',
    ],
    'web.assets_qweb': [          # v15-only bundle for OWL XML templates
        'my_module/static/src/xml/my_widget.xml',
    ],
},
```

DELTA vs v12: assets are declared in `__manifest__.py` under the `assets`
key (NEW in v15), not via `<template inherit_id="web.assets_backend">`
XML records. The `web.assets_qweb` bundle is the v15 home for OWL XML
templates; it is **removed in v16** (templates move into
`web.assets_backend`/`_frontend`) — web-verified.

## Hard rules (Odoo 15 specific)

- Never `@api.multi` / `@api.one` — removed in v13.
- `create()` is `@api.model_create_multi(vals_list)` — list form.
- `attrs="{...}"` / `states="..."` are STILL the only conditional-view
  syntax in v15 — do NOT use direct `invisible="<expr>"` (that is v17+).
- OWL is v15's new frontend layer but jQuery + `web.Widget` coexist;
  use the `owl` global, not the `@odoo/owl` package import (that is v16+).
- Declare assets in the manifest `assets` dict, not via XML records.
- Controller route is `type='json'` (renamed `'jsonrpc'` in 19+) —
  unchanged from v12.
