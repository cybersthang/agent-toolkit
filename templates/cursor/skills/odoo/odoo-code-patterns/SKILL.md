---
name: odoo-code-patterns
description: Canonical Odoo patterns — model, mixin, delegation, compute, wizard, report, controller, cron, view inheritance, OWL component. Version-aware: Step 0 detects the addon's Odoo version from `__manifest__.py`, then loads `references/odoo-<N>-patterns.md` (12 standalone; 17→18→19→20 cascade). Module-agnostic; copy the snippet that fits, do not paste an entire file into chat. Open whenever the user asks "viết theo pattern X", "follow project style", "Odoo pattern for Y".
---

# Odoo — Code Patterns (version-aware)

This skill lists the patterns that are **shared across all Odoo versions**. Anything that differs between 12 / 17 / 18 / 19 / 20 lives in `references/odoo-<N>-patterns.md` and is loaded after Step 0 detects the target version.

ORM, performance and view *rules* (must / must-not) live in `.cursor/rules/odoo-<N>/odoo-<N>-backend.mdc`. This skill is **patterns only** — copy-pasteable snippets.

## 0. Version detection (MANDATORY first step)

Same protocol as `odoo-code-review`:

1. **`__manifest__.py` `version` field** — read via `codebase.read_manifest({module_path})`. Pattern `^(\d+)\.0\.`.
2. **Fallback signals** (only if manifest is missing/unparseable):
   - `@api.multi` decorator → ≤13 (treat as 12 in our scope).
   - `attrs="{...}"` / `states="..."` in view XML → ≤13.
   - `@api.model_create_multi` decorator → ≥14.
   - `invisible="<py expr>"` on `<field>` → ≥17.
   - `/** @odoo-module **/` header → ≥15 (OWL era).
   - `search(domain=...)` keyword → ≥18.
   - `aggregator='sum'` field declaration → ≥18.
   - `@http.route(type='jsonrpc')` → ≥19.
3. **Ask the user** only if signals are inconclusive.

Then load the matching reference:

| Detected major | Reference (newest first; cascade) |
|---|---|
| 12 | `references/odoo-12-patterns.md` (standalone) |
| 13 / 14 / 15 / 16 | apply `odoo-17-patterns.md` + flag MEDIUM "transition era — v13-16 keep `attrs=`/`states=` valid, OWL adoption staged (v14 v1 introduced, v16 v2 mature), `_check_company_auto` mainstream only 16+, `account.invoice` lives v12-13 then merged into `account.move` from v14. Cross-check the dedicated `odoo-<N>` rule pack (now shipping for every v13-20) before applying." |
| 17 | `references/odoo-17-patterns.md` |
| 18 | `references/odoo-18-patterns.md` ← 17 |
| 19 | `references/odoo-19-patterns.md` ← 18 ← 17 |
| 20 | `references/odoo-20-patterns.md` ← 19 ← 18 ← 17 (pre-GA stub) |
| 21+ | apply 20 stub + flag LOW "newer than skill — verify each pattern" |
| Mixed monorepo | detect **per module**, load each module's matching chain, label findings `(v<N>)` |

If you skip Step 0 → wrong decorator / wrong view syntax / wrong frontend stack. Restart.

## 1. Shared patterns (apply to ALL Odoo versions)

### Models — inheritance shapes

- **Inherit by name**: `_inherit = 'res.partner'` — extend an existing model.
- **Mixin (abstract)**: `models.AbstractModel` + `_name = '<x>.mixin'`.
- **Delegation**: `_inherits = {'res.partner': 'partner_id'}` — composition with all fields exposed.

### Compute fields

- `@api.depends(...)` for stored / computed-on-read fields.
- Iterate over `self` (a recordset) — every version of Odoo supports the `for record in self:` form. The `@api.multi` decorator above is **version-specific** (see reference).
- Add `inverse=` only if the field is editable.

### CRUD overrides

- Call `super()` first.
- Validate input.
- Post-process.
- Raise `UserError` for business rules; never bare `Exception`.

The decorator signature for `create()` **differs by version** (`@api.model` single-record in 12, `@api.model_create_multi(vals_list)` in 17+). See reference.

### Report / Controller / Cron

- **Report**: `models.AbstractModel` + `_get_report_values(self, docids, data)`.
- **Controller**: `@http.route('/path', type='json', auth='user')` + always validate input. (Type names rename in 19+ — see reference.)
- **Cron**: `ir.cron` record + a method on the model.

### View inheritance

```xml
<record id="view_x_form_inherit" model="ir.ui.view">
  <field name="name">x.form.inherit</field>
  <field name="model">sale.order</field>
  <field name="inherit_id" ref="sale.view_order_form"/>
  <field name="arch" type="xml">
    <xpath expr="//field[@name='partner_id']" position="after">
      <field name="custom_field"/>
    </xpath>
  </field>
</record>
```

The conditional-visibility syntax (`attrs="..."` vs `invisible="<expr>"`) **differs by version** — see reference.

### Performance shortcuts (all versions)

- Dict lookup: `by_id = {p.id: p for p in records}`.
- Aggregations: `env['model'].read_group(domain, fields, groupby, lazy=False)`.
- Counts: `env['model'].search_count(domain)` (never `len(search(...))`).
- Batch ORM ops: `records.write({...})` once, not per record in a loop.

### Universal hard rules

- Never declare `_name` and `_inherit` to the same string in the same class — that is delegation, not inheritance.
- Never put `search()` / `browse(id)` inside a Python loop.
- Never edit XML inheritance arch without an `xpath` expression (replacing root tags breaks downstream inheritances).
- Never bypass `lookup_canonical_decision` for recurring "how do we do X in this project" answers.

## 2. Version-specific patterns

After Step 0, load `references/odoo-<detected>-patterns.md` for:
- The correct `create()` decorator + signature.
- The correct compute-method form (`@api.multi` vs implicit recordset).
- Conditional-visibility syntax in views (`attrs=` vs `invisible="<expr>"`).
- Frontend snippet (jQuery / web.Widget in 12; OWL component in 15+).
- Controller route type rename in 19+.
- ORM signature rename (`args=` → `domain=` in 18+).

## Sibling skills

- `odoo-code-review` — the gate for findings (same version-detection protocol).
- `odoo-codebase-discovery` — call before this skill to locate the target module + read its manifest.
- `odoo-module-scaffold` — when creating a NEW module (also version-aware).
- `<stack>-deterministic-answers` — cite canonical_decisions before re-deriving "which decorator do we use".
