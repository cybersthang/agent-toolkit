# Odoo 16 — pattern deltas (neighbour = v17)

> odoo-16 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load this when Step 0 detected major = **16**. Odoo 16 is the FIRST
mainstream OWL 2.x web framework release (OWL 2.0 shipped Oct 2022
alongside 16.0 — verified: odoo/owl v2.0.0 ~Oct 2022, and odoo/odoo
#106898 bumps owl 2.0.1→2.0.2 on the saas-16.1 line). The component
author API is therefore the SAME as v17. The big v16→v17 break is the
*view layer* (`attrs`/`states` removal, `<tree>`→`<list>`), NOT the
frontend runtime. Read `odoo-17-patterns.md` as the structural base;
this file only records where 16 diverges from 17.

## Compute + CRUD — recordset is the default

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

- `@api.multi` is REMOVED (since v13) — recordset is the default. Same
  as v17 — see `odoo-17-patterns.md` §Compute + CRUD.
- `@api.model_create_multi(vals_list)` is the batch-safe `create`
  override — unchanged from v17.

### Display name — `name_get()` in 16.0; deprecated mid-16.x (DELTA vs 17)

```python
# v16.0 — override name_get (display_name is computed from it)
def name_get(self):
    result = []
    for record in self:
        result.append((record.id, f"[{record.code}] {record.name}"))
    return result
```

- In **16.0** `name_get()` is the supported override for the displayed
  label; `display_name` is computed from it.
- **Minor-version nuance**: `name_get()` was **deprecated in saas-16.4**
  in favour of overriding `_compute_display_name` (verified: odoo/odoo
  PR #122085 landed on saas-16.4, per the saas-16.4 ORM changelog). It
  is **fully removed in 17.0** (commit 3c62ca1, 17.0).
- Practical rule: on **16.0** stable, write `name_get()`. If the target
  is a **16.4+ SaaS** build, `_compute_display_name` is the forward
  form. Confirm the exact 16 minor before asserting either in a
  customer-facing report.

## Wizard — no decorator on action methods

Unchanged from v17 — see `odoo-17-patterns.md` §Wizard. (`@api.multi`
already gone; `ensure_one()` + `self.env.context.get('active_ids')`.)

## View — `attrs="{...}"` / `states="..."` ARE STILL USED (DELTA vs 17)

```xml
<xpath expr="//field[@name='partner_id']" position="after">
  <field name="custom_field"
         attrs="{'invisible': [('state','=','done')],
                 'readonly': [('state','=','done')],
                 'required': [('state','=','draft')]}"/>
</xpath>
```

- **`attrs="{...}"` and `states="..."` are VALID in 16.** The inline
  Python-expression syntax (`invisible="state == 'done'"`) that v17
  mandates does NOT exist in 16. (Verified: official forum/blog sources
  state the removal is "since 17.0".) This is the single biggest
  view-layer divergence from v17.
- `<tree>` is the list-view tag in 16. The `<tree>`→`<list>` rename is
  a v17+ change — do not emit `<list>` in 16 views.
- Inheritance via `<xpath expr position="...">` — unchanged from v17.

## Frontend — OWL 2.x component (SAME author API as v17)

```javascript
/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class MyWidget extends Component {
    static template = "my_module.MyWidget";

    setup() {
        this.orm = useService("orm");
        this.state = useState({ records: [] });
        onWillStart(async () => {
            this.state.records = await this.orm.searchRead("my.model", [], ["id", "name"]);
        });
    }
}

registry.category("actions").add("my_module.my_widget", MyWidget);
```

- `/** @odoo-module **/` header + `import { ... } from "@odoo/owl"` +
  `setup()` hooks + `static template` — all present in 16 (verified:
  Odoo 16 "Discover the JS framework" tutorial uses exactly this form).
- OWL XML templates in 16 are declared with the `owl="1"` attribute on
  the `<templates>` root (verified: Odoo 16 OWL tutorial). v17 keeps
  this too; do not treat it as a 16-only quirk.
- `t-out` (not `t-raw`) is the OWL 2.x output directive — same as v17.
- `web.Widget`/jQuery legacy still ships in 16 (the webclient is only
  partially OWL; the full view/field OWL rewrite is v17), but for NEW
  code use OWL — same guidance as v17.

## Hard rules (Odoo 16 specific)

- Never `@api.multi` — gone since v13 (same as v17).
- `@api.model_create_multi(vals_list)` for `create` overrides (same as v17).
- **DO use `attrs="{...}"` / `states="..."` in 16 views** — the inline
  `invisible="<expr>"` syntax is v17+. (Reverse of the v17 hard rule.)
- **DO use `<tree>`**, not `<list>` (v17+ rename).
- On **16.0** override `name_get()` for display labels; on **16.4+**
  SaaS prefer `_compute_display_name` (deprecation landed saas-16.4,
  removal 17.0). v17 mandates `_compute_display_name`.
- OWL component authoring is identical to v17 — `@odoo/owl` imports,
  `setup()`, hooks.
- Controller route type is still `'json'` in 16 (renamed `'jsonrpc'` in
  19+ — see `odoo-19-patterns.md`). Unchanged from v17.
