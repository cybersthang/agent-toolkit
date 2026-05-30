# Odoo 12 — scaffold deltas (standalone)

## Manifest

```python
# __manifest__.py
{
    'name': '<Human readable>',
    'version': '12.0.1.0.0',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/<model>_views.xml',
    ],
    'installable': True,
    'application': False,
}
```

- No `'license'` field required in Odoo 12 conventions (project may
  still set one — match sibling manifests).
- No `'assets'` section (asset bundles inject via XML records in 12).

## Model template

```python
# models/<model>.py
from odoo import api, fields, models
from odoo.exceptions import UserError


class MyModel(models.Model):
    _name = 'my.model'
    _description = 'My Model'

    name = fields.Char(required=True)

    @api.multi
    def action_do(self):
        self.ensure_one()
        if not self.name:
            raise UserError('Name is required')
        return True

    @api.model
    def create(self, vals):
        return super().create(vals)
```

- `@api.multi` on recordset-iterating methods.
- `create(vals)` single-record signature with `@api.model`.

## View template (12 syntax)

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

- Use `attrs="{...}"` for conditional visibility/readonly/required.
- No frontend `static/src/` for OWL (Odoo 12 uses jQuery; only add
  `static/src/js/` if you need a jQuery web widget).

## Verification command

```bash
odoo-bin -u <module> --stop-after-init   # 12-era; -d implicit from odoo.conf
```

If your project uses a non-default `odoo-bin` path (Enterprise overlay,
fork with custom server directory, etc.), resolve it from
`agent-toolkit.config.json` → `stack.odoo_bin_rel` rather than hardcoding.
