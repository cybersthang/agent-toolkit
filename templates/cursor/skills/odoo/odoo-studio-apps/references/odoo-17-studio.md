# Odoo Studio — what it generates, and the DB-vs-code asymmetry

Reference for the `odoo-studio-apps` SKILL. Load after Step 0 detects a
Studio-built addon (Enterprise; `web_studio` in `depends`).

Studio is **Enterprise-only** (`web_studio`). On Community / `base` it
does not exist — nothing here applies. The naming and storage patterns
below are stable across the Studio-era majors; never assert a specific
version for a fact you have not opened the target's source/release notes
for. Where versions matter, the deltas are called out inline.

## What Studio writes — and where (DB, not the addon folder)

Studio actions create **database records**, not files in any addon
directory. The asymmetry that bites: a dev edits addon XML on disk, a
user keeps clicking in Studio, the two diverge.

| Studio action | Stored as (DB) | xml_id namespace |
|---|---|---|
| Custom field | `ir.model.fields`, `state='manual'` | `studio_customization.*` |
| New model | `ir.model`, name `x_<slug>` | `studio_customization.*` |
| View tweak | `ir.ui.view` (inheriting the base view) | `studio_customization.*` |
| Automation | `base.automation` + `ir.actions.server` | `studio_customization.*` |
| Report | `ir.actions.report` + QWeb `ir.ui.view` + `ir.attachment` | `studio_customization.*` |
| Menu / action | `ir.ui.menu` + `ir.actions.act_window` | `studio_customization.*` |

`ir_model_data` rows tie each artifact to the `studio_customization`
module record so a later **Export** can serialize them.

## The `x_` / `x_studio_` field-name rule

Custom (manual) fields **must** start with `x_` — Odoo enforces this for
any `state='manual'` field. Studio defaults the technical name to
`x_studio_<label-slug>` (derived from the field Label). Keep the prefix:

- `x_` — required for ANY manual field (Studio or Technical > Models).
- `x_studio_` — Studio's default, kept so Studio fields are identifiable.

```text
Label "Customer Ref"  ->  technical name  x_studio_customer_ref
```

Verified: odoo.com/documentation/.../studio/fields.html ("technical name
of a new field added using Studio is by default prefixed by `x_studio_`";
"keep at least the `x_` prefix, which is required for any custom field").

## DB-vs-code asymmetry — the silent failure class

```text
Disk (addon)            Database
------------            --------
(nothing)        <----  x_studio_customer_ref   (ir.model.fields, manual)
(nothing)        <----  studio_customization.<hash>  (ir.ui.view)
```

Consequences:
- A fresh DB or `-u` that re-declares a model **drops** manual fields not
  present in code — user data in those columns is lost.
- `studio_customization.*` is **reserved** by Studio: code that claims an
  xml_id in that namespace collides with the next Studio edit.
- Studio's "computed" field is a `safe_eval` expression in
  `ir.model.fields.compute`; its `depends` is inferred (shallow) — dotted
  paths silently miss recompute. Promote to a real `@api.depends`.

## Exporting Studio customizations to a proper module

The **only** sanctioned DB -> disk path. Activate the Studio toggle on the
dashboard, open **Customizations**, click **Export** -> a `.zip`
(historically `customizations.zip`) containing `__manifest__.py`, the
model definitions, and the UI customizations as XML.

```bash
unzip -o customizations.zip -d /tmp/studio_export
ls /tmp/studio_export            # __manifest__.py  models/  *.xml ...
```

Two gotchas (both confirmed on odoo.com Studio docs):

1. **Dependencies are NOT added.** "Studio does not add the underlying
   modules as dependencies of the exported module" — the destination DB
   must already have the same apps installed, or add them to `depends`
   by hand after export.
2. **Data is NOT included by default.** The export ships *customizations*
   (models/fields/views), not the *records* in those models. To carry
   records, tick **Include Data** (and **Include Demo Data** for demo-
   flagged rows, which auto-enables Include Data). This **Include Data**
   toggle is the newer Studio export behaviour — verify the toggle's
   presence on your target major before relying on it.

## Migrating a Studio app to a code-owned module (in order)

```text
1. Export from the SOURCE (prod) DB   -> capture live DB state
2. Diff export vs your code addon     -> find DB-only artifacts
3. Promote out of studio_customization.* namespace:
     field:      x_studio_<n> -> <n> in models/*.py (keep x_studio_<n>
                 one cycle; copy values in migrations/<ver>/post-*.py)
     view:       rewrite inheritance with a CODE-owned xml_id, anchored
                 on stable base-Odoo nodes (never on x_studio_* fields)
     automation/ rebuild in code; delete the studio_customization record
     report:       in a pre-init migration
4. Lock Studio for the model so the two can't diverge again
```

Pre-flight before relying on the diff/migration helpers: open an actual
export's data XML AND an OCA module's `migrations/` layout for the target
major — both the export serialization and the migration directory shape
have shifted between majors.

## Locking Studio after promotion

- **Per field:** set `ir.model.fields.studio = False` on promoted fields.
- **Org-wide:** restrict `web_studio.group_studio_manager` to chosen devs.

Record the WHY (`/adr-add`) so a future dev does not re-enable Studio and
silently re-open the divergence.

## Hard rules (Studio-specific)

- Studio writes to the DB, not the addon folder — never assume a Studio
  artifact is in version control until it has been Exported.
- Never hand-edit a `studio_customization` addon without a same-day
  Export from the same DB.
- Never claim an xml_id in the `studio_customization.*` namespace from
  your own code.
- Never `xpath`-anchor on an `x_studio_*` field — Studio renames break
  the anchor with no upgrade error.
- After Export, manually fix `depends` (Studio omits them) and decide on
  **Include Data** if records must travel.
- Promote Studio "computed" formulas to `_compute` with explicit
  `@api.depends` for any dotted dependency.

## Sources verified

- `https://www.odoo.com/documentation/18.0/applications/studio/models_modules_apps.html`
  — Export menu, `studio_customization` module, deps not added, Include Data.
- `https://www.odoo.com/documentation/19.0/applications/studio/fields.html`
  and 18.0 fields page — `x_studio_` default prefix, `x_` requirement.
- `https://www.odoo.com/knowledge/article/25544` — Studio Export ->
  `customizations.zip`, contents (models + UI as XML).
