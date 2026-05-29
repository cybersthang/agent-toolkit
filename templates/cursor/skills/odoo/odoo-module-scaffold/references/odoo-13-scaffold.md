# Odoo 13 — scaffold deltas (standalone)

> odoo-13 reference (drafted v0.29). Deltas vs odoo-12-scaffold.md web-verified where cited; `<!-- VERIFY -->` items need DEV confirmation.

Load when Step 0 detected major = **13**. The manifest and view shapes
match v12; the model template differs (no `@api.multi`,
`@api.model_create_multi` for `create`).

## Manifest

```python
# __manifest__.py
{
    'name': '<Human readable>',
    'version': '13.0.1.0.0',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/<model>_views.xml',
    ],
    'installable': True,
    'application': False,
}
```

- `version` prefix is `13.0.…`.
- No `'assets'` manifest-dict key in 13 — asset bundles inject via XML
  inheritance of `web.assets_backend` / `web.assets_frontend` (the
  `assets` dict key arrived in v15). Same as v12.
- `'license'` field still optional by convention — match sibling
  manifests.

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

Deltas vs v12 (verified against 13.0 `odoo/api.py` / `odoo/models.py`):
- **No `@api.multi`** on recordset-iterating methods — removed in 13.
- `create()` is the multi-record form: `@api.model_create_multi` +
  `vals_list`, not single-record `@api.model create(vals)`.

## View template (13 syntax)

Unchanged from v12 — see odoo-12-scaffold.md §"View template (12
syntax)". Use `attrs="{...}"` for conditional visibility/readonly/required;
the direct `invisible="<expr>"` syntax is 17+. No OWL `static/src/`;
add `static/src/js/` only for a jQuery `web.Widget`.

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

## Verification command

Unchanged from v12 — see odoo-12-scaffold.md §"Verification command":

```bash
odoo-bin -u <module> --stop-after-init   # 13-era; -d implicit from odoo.conf
```

Resolve a non-default `odoo-bin` from `agent-toolkit.config.json` →
`stack.odoo_bin_rel` rather than hardcoding. Odoo 13 requires Python
**>= 3.6** (verified: 13.0 minimum bumped from 3.5 in v12); use the
project's `{{PYTHON_BIN}}`.
