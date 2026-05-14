---
name: odoo-12-module-scaffold
description: Scaffold a new Odoo 12 module under any addon root. Module-agnostic; the prefix and target path come from the user, never hard-coded. Open this skill only when scaffolding.
---

# Odoo 12 — Scaffold Module

## Inputs to confirm before writing files

1. **Module name** (snake_case). Honour the local convention (e.g. `nakivo_*` only when the target root is the NAKIVO custom layer).
2. **Addon root** (e.g. `nakivo/`, `base_addons/`, `OCA/`). Ask if ambiguous — never assume.
3. **`depends`** list. Read existing siblings via `codebase.discover_modules` if unsure.
4. **Whether mail / chatter is needed** (drives manifest depends and form layout).

## Minimum layout

```
<root>/<module>/
  __manifest__.py
  __init__.py
  models/
    __init__.py
  views/
    *.xml
  security/
    ir.model.access.csv          # one line per new model
    security.xml                  # only if module-private groups
```

## Manifest essentials

- `'data'` order: `security/` first, then `data/`, then `views/`, then menus. Files load top-to-bottom, so referenced XML IDs must already exist.
- `'depends'`: only what the module actually imports / inherits.
- `'version'`: `12.0.<major>.<minor>.<patch>` in the project's existing pattern.
- `'installable': True`.

## Templates

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
```

```xml
<!-- views/<model>_views.xml -->
<odoo>
  <record id="view_my_model_form" model="ir.ui.view">
    <field name="name">my.model.form</field>
    <field name="model">my.model</field>
    <field name="arch" type="xml">
      <form>
        <sheet>
          <group><field name="name"/></group>
        </sheet>
      </form>
    </field>
  </record>
</odoo>
```

```csv
# security/ir.model.access.csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.model.user,model_my_model,base.group_user,1,1,1,1
```

## Verification

1. `-u <module> --stop-after-init` against the dev DB.
2. Confirm XML IDs are unique inside the module.
3. If the module touches existing models, run `codebase.find_inheritance_chain` to confirm there are no naming collisions across addon roots.

## Hard rules

- Never copy module names from a sibling without re-checking that the addon root matches.
- Never silently adopt a prefix (`nakivo_`, `oca_`, `web_`) — confirm with the user.
- Never inline data files referenced by a manifest before they exist on disk.
