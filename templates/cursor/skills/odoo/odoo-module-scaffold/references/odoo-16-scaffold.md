# Odoo 16 — scaffold deltas (neighbour = v17)

> odoo-16 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Structural model is `odoo-17-scaffold.md`. Load when Step 0 detected
major = **16**. Only divergences from v17 are spelled out below.

## Manifest

```python
# __manifest__.py
{
    'name': '<Human readable>',
    'version': '16.0.1.0.0',
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

- `'version'` is `16.0.x.y.z`.
- `'assets'` declared as a dict — same as v17 (the v15+ form, not the
  v12-era XML asset records).

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

    # v16 display label: override name_get (NOT _compute_display_name)
    def name_get(self):
        return [(rec.id, f"[{rec.id}] {rec.name}") for rec in self]
```

- No `@api.multi`; `create()` takes `vals_list` — same as v17.
- **DELTA vs 17**: override `name_get()` for the display label on
  **16.0**. `name_get` is deprecated from **saas-16.4** in favour of
  `_compute_display_name` (verified: odoo/odoo PR #122085 on saas-16.4)
  and removed in 17.0. Use `name_get` for 16.0 stable; switch to
  `_compute_display_name` if targeting 16.4+ SaaS.

## View template (16 syntax — DELTA vs 17)

```xml
<odoo>
  <record id="view_my_model_form" model="ir.ui.view">
    <field name="name">my.model.form</field>
    <field name="model">my.model</field>
    <field name="arch" type="xml">
      <form>
        <sheet>
          <group>
            <field name="name"
                   attrs="{'readonly': [('id','!=',False)]}"/>
          </group>
        </sheet>
      </form>
    </field>
  </record>

  <record id="view_my_model_tree" model="ir.ui.view">
    <field name="name">my.model.tree</field>
    <field name="model">my.model</field>
    <field name="arch" type="xml">
      <tree>
        <field name="name"/>
      </tree>
    </field>
  </record>
</odoo>
```

- **Use `attrs="{...}"` / `states="..."`** for conditional
  visibility/readonly/required in 16. The inline `invisible="<expr>"`
  syntax is **17+** and does NOT work in 16 (verified: removal/replacement
  is "since 17.0").
- **Use `<tree>`** for the list view — `<list>` is the v17 rename.

## OWL component (optional, for frontend)

Same as v17 — OWL 2.x author API is identical (`@odoo/owl` imports,
`setup()`, `static template`, `/** @odoo-module **/`). See
`odoo-code-patterns/references/odoo-16-patterns.md` §Frontend. Register
assets via the `'assets'` dict in the manifest.

OWL XML template root carries `owl="1"`:

```xml
<templates xml:space="preserve">
  <t t-name="my_module.MyWidget" owl="1">
    <div class="o_my_widget"><t t-esc="state.value"/></div>
  </t>
</templates>
```

## Verification command

```bash
odoo-bin -u <module> --stop-after-init -d <db>
```

- Requires Python **3.7+** (verified: Odoo 16 install docs; Ubuntu 22.04
  ships 3.10 which is the common runtime, but 3.7 is the documented
  minimum — do not assert 3.10 as a hard floor). PostgreSQL 12+.
