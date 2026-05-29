# Odoo 15 — scaffold deltas (standalone, transitional)

> odoo-15 reference (drafted v0.29). Deltas vs odoo-12 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load when Step 0 detected major = **15**. ORM scaffolding matches v17;
view syntax matches v12; the manifest `assets` dict is the v15 novelty.

## Manifest — NEW `assets` dict

```python
# __manifest__.py
{
    'name': '<Human readable>',
    'version': '15.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/<model>_views.xml',
    ],
    'assets': {
        # 'web.assets_backend': [
        #     'my_module/static/src/js/my_widget.js',
        # ],
        # 'web.assets_qweb': [           # v15 home for OWL XML templates
        #     'my_module/static/src/xml/my_widget.xml',
        # ],
    },
    'installable': True,
    'application': False,
}
```

DELTA vs v12:
- `'assets'` declared as a **dict** in the manifest (NEW in v15) — assets
  are NO LONGER injected via `<template inherit_id="web.assets_backend">`
  XML records like in v12 (web-verified).
- `web.assets_qweb` is the v15 bundle for OWL XML templates; **removed in
  v16** (templates move into `web.assets_backend`/`_frontend`).
- `'license'` is conventional (match siblings; `LGPL-3` community,
  `OEEL-1` Enterprise) — same guidance as v17.

## Model template — recordset default, `@api.model_create_multi`

```python
# models/<model>.py
from odoo import api, fields, models
from odoo.exceptions import UserError


class MyModel(models.Model):
    _name = 'my.model'
    _description = 'My Model'

    name = fields.Char(required=True)

    def action_do(self):
        self.ensure_one()
        if not self.name:
            raise UserError('Name is required')
        return True

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)
```

DELTA vs v12: no `@api.multi` (removed v13); `create()` takes `vals_list`
with `@api.model_create_multi` (v14+). Web-verified.

## View template (15 syntax — SAME as v12)

```xml
<odoo>
  <record id="view_my_model_form" model="ir.ui.view">
    <field name="name">my.model.form</field>
    <field name="model">my.model</field>
    <field name="arch" type="xml">
      <form>
        <sheet>
          <group>
            <field name="name" attrs="{'readonly': [('id','!=',False)]}"/>
          </group>
        </sheet>
      </form>
    </field>
  </record>
</odoo>
```

Use `attrs="{...}"` for conditional visibility/readonly/required — same
as v12 (removed only in v17). Do NOT use direct `invisible="<expr>"`.

## OWL component (optional, for frontend) — TRANSITIONAL

If you need a frontend widget in v15, the OWL files look like:

```
static/src/js/my_widget.js     # /** @odoo-module **/ header on line 1
static/src/xml/my_widget.xml    # root carries owl="1"
```

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
const { Component } = owl;            // global owl (OWL 1.x), NOT @odoo/owl

class MyWidget extends Component {}
MyWidget.template = "my_module.MyWidget";
registry.category("actions").add("my_module.my_widget", MyWidget);
```

Register the files in the manifest `assets` dict (JS in
`web.assets_backend`, XML in `web.assets_qweb`). The v12 jQuery
`web.Widget` path still works in v15 if you prefer a legacy widget.
See odoo-15-patterns.md "Frontend".

## Verification command

```bash
odoo-bin -u <module> --stop-after-init -d <db>
```

Resolve a non-default `odoo-bin` path from `agent-toolkit.config.json` →
`stack.odoo_bin_rel` rather than hardcoding — unchanged from v12.
