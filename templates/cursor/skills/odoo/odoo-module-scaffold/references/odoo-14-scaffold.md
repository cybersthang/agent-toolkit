> odoo-14 reference (drafted v0.29). Deltas vs odoo-12-scaffold.md web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

# Odoo 14 — scaffold deltas (standalone)

## Manifest

```python
# __manifest__.py
{
    'name': '<Human readable>',
    'version': '14.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/<model>_views.xml',
        'views/assets.xml',          # asset bundle inheritance (see below)
    ],
    'installable': True,
    'application': False,
}
```

- `'license'` is conventional in 14 (project may match sibling manifests —
  `LGPL-3` for community, `OEEL-1` for Enterprise).
- **No `'assets'` dict** — the manifest `'assets'` key arrived in **Odoo 15**
  (verified). In 14 assets are injected via XML records inheriting
  `web.assets_backend` / `web.assets_frontend`.

## Model template (recordset-default, like 17 — NOT like 12)

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

- **No `@api.multi`** — removed in 13 (verified `odoo/api.py` 14.0).
  Recordset is the default.
- `create()` override uses `@api.model_create_multi` + `vals_list`
  (decorator present in 14, verified). This is the biggest delta vs the
  v12 scaffold.

## View template (14 syntax — `attrs`, same as 12)

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

- Use `attrs="{...}"` for conditional visibility/readonly/required. The
  direct `invisible="<expr>"` syntax is 17+ and will NOT parse in 14.
- Unchanged from v12 — see odoo-12-scaffold.md "View template".

## Asset bundle (14 — XML, NOT manifest dict)

```xml
<!-- views/assets.xml -->
<odoo>
  <template id="assets_backend" inherit_id="web.assets_backend">
    <xpath expr="." position="inside">
      <script type="text/javascript"
              src="/my_module/static/src/js/my_widget.js"/>
      <link rel="stylesheet" type="text/scss"
            href="/my_module/static/src/scss/my_module.scss"/>
    </xpath>
  </template>
</odoo>
```

- This XML-inheritance form is the 14 way (verified: manifest `'assets'`
  dict is 15+).
- For a custom backend widget, the legacy `web.Widget`/jQuery form is the
  default in 14. OWL exists in 14 (OWL 1.4.11) but most backend widgets are
  still legacy.

### OWL component scaffold (14 — `odoo.define` + global `owl`, NOT ES6)

Verified against a real 14.0 component
(`addons/mail/static/src/components/messaging_menu/messaging_menu.js`): in 14
OWL components are NOT ES6 modules. The `/** @odoo-module **/` header and
`import`/`export` are **15+ only** (14 has no JS transpiler — verified: no
`odoo/tools/js_transpiler.py` and no `is_odoo_module` in 14.0
`assetsbundle.py`). Scaffold a 14 OWL component as:

```
my_module/
  static/src/
    components/my_widget/
      my_widget.js      # odoo.define(...) wrapper, no /** @odoo-module **/
      my_widget.xml      # OWL QWeb template <templates><t t-name="...">
```

```javascript
// my_module/static/src/components/my_widget/my_widget.js
odoo.define('my_module/static/src/components/my_widget/my_widget.js', function (require) {
'use strict';

const { Component } = owl;          // global `owl` (UMD), NOT import from "@odoo/owl"

class MyWidget extends Component {}
MyWidget.template = 'my_module.MyWidget';

return MyWidget;
});
```

Register both the `.js` and the OWL `.xml` template via the XML asset bundle
above (the `.xml` template goes in `web.assets_backend`'s `qweb` list / a
`<template>` with the OWL templates).

## Verification command

```bash
odoo-bin -u <module> --stop-after-init   # 14-era; -d implicit from odoo.conf
```

If your project uses a non-default `odoo-bin` path (Enterprise overlay,
fork with custom server directory, etc.), resolve it from
`agent-toolkit.config.json` → `stack.odoo_bin_rel` rather than hardcoding.
