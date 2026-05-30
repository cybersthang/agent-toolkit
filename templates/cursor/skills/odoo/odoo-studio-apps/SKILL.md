---
name: odoo-studio-apps
description: Odoo Studio (Enterprise no-code builder) anti-patterns — DB-stored `studio_*` fields/views/reports drift from filesystem addons, hand-editing Studio XML, promoting Studio apps to code without Export, mixing Studio + dev fields on one view, Studio reports referencing user-specific paths. Version-aware: Step 0 detects Odoo major from `__manifest__.py` (Studio exists 13+, mainstream 14+, Owl-tighter 17/18+), then loads `references/odoo-17-studio.md`. Open whenever the user says "studio", "no-code", "Studio app", "studio export", "custom field", "studio fields", or grep-matches `studio_*` xml_ids / field names.
license: MIT
---

# Odoo — Studio Apps Anti-Patterns (version-aware)

Odoo Studio (Enterprise) writes new models / fields / views / automations
/ reports **into the database** (`ir.model.fields`, `ir.ui.view`,
`ir.actions.report`, `ir_model_data`, `ir_attachment`), NOT into the
addon folder on disk. That asymmetry is the silent class: dev edits
the addon XML, user keeps editing in Studio, the two diverge — next
`-u` upgrade or DB reset loses one side.

Top 5 anti-patterns when evolving a Studio-built app via code, with
falsification recipes + invariant suggestions for `invariant_guard`.

Pair with `odoo-code-review`, `odoo-multi-company`, `odoo-data-verification`.

## 0. Version detection (MANDATORY first step)

Same protocol as `odoo-multi-company`. Studio-specific signals augment:

1. **`__manifest__.py` `version`** via `codebase.read_manifest`. Pattern `^(\d+)\.0\.`. Studio Exports have `web_studio` in `depends`.
2. **Studio-presence signals**: `ir.model.fields.name LIKE 'x_studio_%'`, `ir.ui.view.key LIKE 'studio_customization.%'`, `studio_customization` addon in `addons-path`.
3. **Fallback major signals**: `@api.multi` → ≤13; `attrs="..."` in Studio arch → ≤16; `invisible="<expr>"` → ≥17; `/** @odoo-module **/` in Studio JS → ≥15 (Owl).

| Detected major | Reference |
|---|---|
| 12 | BLOCKER "no Studio in v12" |
| 13 | apply `references/odoo-17-studio.md` + flag HIGH "Studio 13 early" |
| 14 / 15 / 16 | apply `references/odoo-17-studio.md` + flag LOW transitional |
| 17 | `references/odoo-17-studio.md` |
| 18 / 19 / 20 | apply `references/odoo-17-studio.md` + flag LOW "verify target major release notes" |

Studio is **Enterprise-only**: if manifest's `license` is `LGPL-3` /
`OPL-1` without `web_studio` in `depends`, the addon is not a Studio
Export — stop here.

Official docs: `https://www.odoo.com/documentation/{{VERSION}}/applications/studio/`.

## 1. Where Studio writes — disk vs DB asymmetry

| Studio action | DB target | Disk equivalent (if exported) |
|---|---|---|
| Custom field | `ir.model.fields`, `name='x_studio_<slug>'`, `state='manual'` | `<field name="x_studio_<slug>" ...>` |
| View tweak | `ir.ui.view`, `key='studio_customization.<hash>'` | `<record id="studio_<hash>" model="ir.ui.view">` |
| Automation | `base.automation` + `ir.actions.server` | XML record |
| Report | `ir.actions.report` + `ir.ui.view` (template) + `ir.attachment` (assets) | `<report ...>` + QWeb template |
| Menu / action | `ir.ui.menu` + `ir.actions.act_window` | XML record |
| Tracked in `ir_model_data` | xml_id `studio_customization.<hash>` | xml_id you control |

The `studio_customization.*` xml_id namespace is **reserved** by Studio
— code claiming it WILL collide with future Studio edits.

Export bridge: **Studio → Customizations → Export** → `.zip` with
`__manifest__.py`, `models/models.py`, `data/*.xml`. Only sanctioned
DB → disk path.

## 2. Pattern A — Hand-editing Studio-generated XML/Python (H)

**Problem.** Dev edits a `studio_*` view in XML; user keeps editing in
Studio. On next `-u <module>`, ONE side wins silently — usually XML
overwrites the DB row, throwing away user edits since last export.

**Bad:**
```xml
<!-- addons/studio_customization/views/sale_order_views.xml -->
<record id="studio_view_sale_order_form_xxxxx" model="ir.ui.view">
    <field name="inherit_id" ref="sale.view_order_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='partner_id']" position="after">
            <field name="x_studio_customer_ref"/>
            <!-- Dev added this; user added x_studio_customer_email in Studio next day -->
        </xpath>
    </field>
</record>
```

**Good.** Re-export → diff → promote out of `studio_customization.*`
namespace (see §6), then disable Studio editing for the model.

**Falsification:** (1) Studio-add `x_studio_test`, export. (2) Edit
`string` in XML ("Test" → "Test (edited)"). (3) `-u studio_customization`.
(4) Studio web UI: relabel to "Test (user)". (5) `-u` again. Bug: label
reverts to "Test (edited)".

**Invariant:**
```json
{
  "id": "studio-no-hand-edit-of-studio-namespace",
  "applies_to": ["**/studio_customization/**/*.xml", "**/studio_customization/**/*.py"],
  "rules": {"must_keep_regex": ["<!--\\s*STUDIO-GENERATED\\s*—\\s*DO NOT HAND-EDIT\\s*-->"]},
  "severity": "blocker",
  "rationale": "Hand-editing diverges from DB; next Studio edit silently overwrites. See odoo-studio-apps SKILL §2."
}
```

## 3. Pattern B — Promoting a Studio app to code without exporting first (H)

**Problem.** Dev rewrites a Studio app as code, skips Studio Export,
re-creates fields/views from scratch. Studio edits made between
scaffolding and deploy are lost — they lived only in the source DB's
`ir_model_data`.

**Bad:**
```bash
git pull origin main
./odoo-bin -u my_studio_replacement --stop-after-init
# No Studio Export from prod — user's last 2 weeks of edits gone
```

**Good:**
```bash
# 1. Studio Export from SOURCE DB
ssh prod-odoo "python tools/studio_export.py --db prod --out /tmp/studio_$(date +%F).zip"
# 2. Diff against code-first replacement
python tools/studio_diff.py --baseline /tmp/studio_$(date +%F).zip --candidate addons/my_studio_replacement/
# 3. Only proceed if no DB-only artifacts. Waive explicitly in
#    .agent-toolkit/studio_waivers.json with justification.
```

Studio Export format drifts between 14 and 18+ — read an actual
export's `data/studio_customization_data.xml` for the target major
before writing the diff helper.

**Falsification:** Two DBs: `staging` (Studio edits), `dev` (code-first).
User adds `x_studio_priority_score_color` after dev scaffold. Dev runs
`-u my_replacement` on staging-copy without re-export. Bug: field
disappears (manual fields drop on upgrade when not re-declared).

```python
# realdata_test probe
before = self.env['ir.model.fields'].search([
    ('state','=','manual'), ('name','like','x_studio_%'),
    ('model_id.model','=','my.target.model'),
])
self.env.ref('base.module_my_studio_replacement').button_immediate_upgrade()
after = self.env['ir.model.fields'].search([
    ('state','=','manual'), ('name','like','x_studio_%'),
    ('model_id.model','=','my.target.model'),
])
self.assertFalse(before - after, f"Studio fields dropped: {(before - after).mapped('name')}")
```

**Invariant:**
```json
{
  "id": "studio-export-before-deploy",
  "applies_to": ["**/deploy/**/*.sh", "**/.github/workflows/*.yml", "**/Jenkinsfile"],
  "rules": {"must_keep_regex": ["studio_export(\\.py|\\.sh)?\\s+--db\\s+\\S+"]},
  "severity": "warn",
  "rationale": "Without pre-deploy Studio Export, user-edited fields silently drop on upgrade. See odoo-studio-apps SKILL §3."
}
```

## 4. Pattern C — Adding non-Studio fields next to Studio fields in the same view (H)

**Problem.** Dev xpaths anchored on a Studio field. Studio later renames
or moves the anchor — xpath silently fails (no upgrade error, the field
just doesn't render).

**Bad:**
```xml
<record id="view_sale_order_form_dev_extend" model="ir.ui.view">
    <field name="inherit_id" ref="studio_customization.sale_order_studio_view"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='x_studio_priority']" position="after">
            <field name="dev_added_field"/>
        </xpath>
    </field>
</record>
```

**Good.** Anchor on stable, base-Odoo nodes only — inherit `sale.view_order_form`,
xpath on `//field[@name='partner_id']`. If the field MUST sit next to a
Studio field → promote the Studio field to code first (§6).

**Falsification:** Studio-add `x_studio_priority`. Code: xpath-anchor
on it. Deploy → renders. Studio-rename `x_studio_priority` →
`x_studio_urgency`. Bug: `dev_added_field` no longer renders, no error.

**Invariant:**
```json
{
  "id": "studio-no-xpath-anchor-on-studio-field",
  "applies_to": ["**/views/*.xml", "**/data/*.xml"],
  "rules": {"must_not_match_regex": ["xpath\\s+expr=\"[^\"]*@name='(?:x_)?studio_"]},
  "severity": "warn",
  "rationale": "Studio renames break anchors silently. See odoo-studio-apps SKILL §4."
}
```

## 5. Pattern D — Using Studio for fields that should be `_compute` (M)

**Problem.** Studio's "computed" field is a `safe_eval` formula in
`ir.model.fields.compute`. No `@api.depends` (Studio infers, often
wrongly), no multi-line logic, no `super()`, recompute on every read
for non-stored, un-testable.

**Bad** — Studio UI formula:
```
record['partner_id'].user_id.name if record['partner_id'].user_id else 'Unassigned'
# Stored: depends='partner_id' — missed partner_id.user_id.name
```

**Good:**
```python
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    account_manager = fields.Char(compute='_compute_account_manager', store=False)

    @api.depends('partner_id', 'partner_id.user_id', 'partner_id.user_id.name')
    def _compute_account_manager(self):
        for order in self:
            order.account_manager = (
                order.partner_id.user_id.name if order.partner_id.user_id else _('Unassigned')
            )
```

**Falsification:** Studio-add `x_studio_account_manager` with bad
formula. Order's partner has `user_id` set → renders user name. Change
`res.users.name` directly. Reload form. Bug: shows OLD name.

**Invariant** (DB probe, not regex):
```json
{
  "id": "studio-compute-needs-promotion",
  "probe": "odoo_studio_shallow_compute_probe",
  "severity": "warn",
  "rationale": "Studio's depends-inference is shallow; dotted paths silently miss recompute. See odoo-studio-apps SKILL §5."
}
```
Probe SQL:
```sql
SELECT name, model_id, compute, depends FROM ir_model_fields
WHERE state='manual' AND compute IS NOT NULL AND compute != ''
  AND (depends IS NULL OR depends NOT LIKE '%.%');
```

## 6. Pattern E — Studio reports referencing user-specific paths (M)

**Problem.** Studio Report Designer stores drag-dropped images as
`ir.attachment` referenced by **numeric ID** in QWeb. IDs are per-DB.
Export → install on fresh DB → wrong-customer logo or broken image.
Same for hard-coded `res.users` IDs.

**Bad:**
```xml
<template id="studio_customization.report_invoice_xxxxx">
    <img t-att-src="'/web/image/ir.attachment/142/datas'"/>
    Signed by: <span t-esc="env['res.users'].browse(7).name"/>
</template>
```

**Good:**
```xml
<template id="my_module.report_invoice_with_logo">
    <img t-att-src="image_data_uri(o.company_id.logo)"/>
    Signed by: <span t-esc="o.user_id.name"/>
</template>
```

Images that must travel with the addon → commit under `static/src/img/`
and reference as `my_module/static/src/img/<file>.png`.

**Falsification:** Studio-design a report with drag-dropped logo.
Export → install on fresh DB (`base` + `web_studio` only). Print. Bug:
broken-image icon — `ir.attachment/<id>` doesn't exist on fresh DB.

**Invariant:**
```json
{
  "id": "studio-no-hardcoded-attachment-id-in-report",
  "applies_to": ["**/studio_customization/**/*.xml", "**/report/*.xml"],
  "rules": {"must_not_match_regex": ["/web/image/ir\\.attachment/\\d+/", "browse\\(\\s*\\d+\\s*\\)"]},
  "severity": "warn",
  "rationale": "Numeric IDs are DB-local — Studio reports break on any other DB. See odoo-studio-apps SKILL §6."
}
```

## 7. Workflow — safely evolving a Studio app via code (IN ORDER)

**Step 1 — Studio Export (capture DB state).** Source DB: Settings →
Technical → Studio → Export → `.zip`. v17+ CLI: `odoo-bin shell` →
upgrade `studio_customization` → use Studio menu Export. Zip contains
`data/studio_customization_data.xml` with ALL DB-side artifacts.

**Step 2 — Diff against existing addon folder.**
```bash
unzip -o studio_customization.zip -d /tmp/studio_new
xmllint --format /tmp/studio_new/data/*.xml > /tmp/studio_new.xml
xmllint --format addons/studio_customization/data/*.xml > /tmp/studio_old.xml
diff -u /tmp/studio_old.xml /tmp/studio_new.xml
```
No diff → safe; DB-only artifacts → promote before deploy; code-only
→ users may have lost edits earlier.

**Step 3 — Promote to versioned addon, mark Studio fields as code-owned.**
- **Field**: copy `x_studio_<name>` → `<name>` in `models/*.py`; keep
  `x_studio_<name>` with `deprecated=True` for one cycle. Data
  migration via `migrations/<version>/post-*.py` copies values.
- **View**: rewrite inheritance with a code-owned xml_id (NOT
  `studio_customization.*`), anchoring on stable nodes (§4).
- **Automation / Report**: rebuild in code; delete the
  `studio_customization` record in a `pre-init` migration.

Migration layout shifted in 14 and 18 — read an actual OCA module's
`migrations/` on the target major before writing the pre-init.

**Step 4 — Disable Studio editing for that model.**
- **Per-field**: set `ir.model.fields.studio` flag to `False` on promoted fields.
- **Org-wide**: restrict `web_studio.group_studio_manager` to authorized devs.

Document the lock via `/adr-add` so future devs know WHY Studio is disabled here.

## 8. Cross-references

| Concern | Skill / file |
|---|---|
| Severity anchors for Studio findings | `odoo-code-review` §G + `references/odoo-<N>-rules.md` Studio section |
| Version-specific Studio reference | `references/odoo-17-studio.md` |
| Live drift probes (`ir_model_data` / `ir.model.fields`) | `odoo-data-verification` |
| Pattern snippets for promoted models | `odoo-code-patterns` |
| Multi-company guards on Studio apps | `odoo-multi-company` |
| Enterprise patterns (Studio is Enterprise-only) | `odoo-enterprise-patterns` |
| Odoo Studio official docs | `https://www.odoo.com/documentation/{{VERSION}}/applications/studio/` |

## 9. Sibling skills to call BEFORE this one

- `odoo-codebase-discovery` — locate Studio-dependent addons (`'web_studio' in depends`).
- `odoo-deterministic-answers` — `lookup_canonical_decision` for project-specific Studio rules before re-deriving.

## 10. Hard rules summary

- Never hand-edit files in a `studio_customization` addon without a same-day Studio Export.
- Never promote a Studio app to code without a pre-deploy Studio Export + diff against the production DB.
- Never anchor `xpath` on `x_studio_*` field names — anchor on base-Odoo (or code-owned) fields only.
- Never use Studio's computed-field formula for dotted dependencies — promote to `_compute` with explicit `@api.depends`.
- Never reference `ir.attachment/<numeric_id>` or `browse(<numeric_id>)` in Studio-exported reports.
