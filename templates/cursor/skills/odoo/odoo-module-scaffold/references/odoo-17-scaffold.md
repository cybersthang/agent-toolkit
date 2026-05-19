# Odoo 17 — scaffold deltas (head of 17→18→19→20 cascade)

## Manifest

```python
# __manifest__.py
{
    'name': '<Human readable>',
    'version': '17.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/<model>_views.xml',
    ],
    'assets': {
        # 'web.assets_backend': [
        #     'my_module/static/src/components/my_widget.js',
        #     'my_module/static/src/components/my_widget.xml',
        # ],
    },
    'installable': True,
    'application': False,
}
```

- `'license'` field is conventional (match project — `LGPL-3` for
  community, `OEEL-1` for Enterprise).
- `'assets'` declared as a dict (not via XML records like in 12).

## Model template

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

- No `@api.multi` — recordset is default.
- `create()` takes `vals_list` with `@api.model_create_multi`.

## View template (17 syntax)

```xml
<odoo>
  <record id="view_my_model_form" model="ir.ui.view">
    <field name="name">my.model.form</field>
    <field name="model">my.model</field>
    <field name="arch" type="xml">
      <form>
        <sheet>
          <group>
            <field name="name" readonly="id != False"/>
          </group>
        </sheet>
      </form>
    </field>
  </record>
</odoo>
```

- Use `invisible="<expr>"`, `readonly="<expr>"`, `required="<expr>"`
  directly. **Never** `attrs="{...}"` or `states="..."` (both removed).

## OWL component (optional, for frontend)

If you need a frontend widget:

```
static/src/components/my_widget.js
static/src/components/my_widget.xml
```

Register the assets via `'assets'` dict in the manifest. See
`odoo-code-patterns` `references/odoo-17-patterns.md` for the OWL
component template.

## Verification command

```bash
odoo-bin -u <module> --stop-after-init -d <db>
```

`-d <db>` is now explicit (odoo.conf may not auto-resolve in some 17
setups).
