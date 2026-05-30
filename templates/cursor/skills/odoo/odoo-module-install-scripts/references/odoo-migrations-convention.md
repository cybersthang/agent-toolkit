# Odoo — `migrations/<version>/{pre,post,end}-*.py` convention

For *upgrades* (manifest `version` bumped), manifest hooks are not enough:
Odoo auto-runs scripts from the module's `migrations/` folder. Unlike the
init hooks, the migration `migrate()` signature is **stable** — it has
always taken `(cr, version)`, including in v17/v18 (verified against
`odoo/modules/migration.py`). The cursor was NOT switched to `env`.

## Directory layout

```
my_module/
  __manifest__.py            # version = '17.0.1.2.0'
  migrations/                # 'upgrades/' is also accepted (since v13)
    17.0.1.2.0/
      pre-migrate.py         # schema-level: DDL on the OLD schema
      post-migrate.py        # record-level: data transforms / recompute
      end-migrate.py         # rarely needed: after EVERY module's post phase
```

- The version folder name MUST equal the manifest `version` exactly:
  `<odoo_major>.0.<x>.<y>.<z>` — e.g. `17.0.1.2.0`, **not** `1.2.0`.
  The major-version prefix is required so the script runs only under that
  server series. Folders are validated against an internal `VERSION_RE`;
  a folder named `tests` is skipped.
- File name MUST start with `pre`, `post`, or `end`. The `-*` suffix is
  free text used only for ordering — `pre-10-foo.py`, `pre-20-bar.py`.
- Within a phase, files run in **lexical** order, e.g.
  `pre-10-do_something.py` → `pre-20-something_else.py` →
  `post-do_something.py` → `post-something.py` → `end-01-x.py` → `end-x.py`.

## Phase semantics

| File | Fires | Safe | NOT safe |
|---|---|---|---|
| `pre-*.py` | BEFORE the new schema is loaded | `ALTER TABLE`, `DROP CONSTRAINT`, `RENAME COLUMN`, raw SQL on still-old schema | ORM on fields that this upgrade adds/renames |
| `post-*.py` | AFTER the module + deps are loaded and updated | Record-level ORM, `_compute` triggers, data backfill | Schema DDL — already too late; use `pre-` |
| `end-*.py` | AFTER ALL modules in the upgrade batch finish their post phase | Cross-module fixups | Anything depending on intra-module ordering |

## `migrate()` signature (VERIFIED — `cr`, not `env`)

```python
# my_module/migrations/17.0.1.2.0/pre-migrate.py
import logging
_logger = logging.getLogger(__name__)

def migrate(cr, version):
    # `version` = the version CURRENTLY recorded in ir_module_module
    #             (the OLD value), or a falsy value on fresh install.
    if not version:
        return                                   # not an upgrade — skip
    _logger.info("my_module: pre-migrate from %s", version)
    cr.execute("ALTER TABLE my_model DROP COLUMN IF EXISTS legacy_field")
```

```python
# my_module/migrations/17.0.1.2.0/post-migrate.py
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})  # build env yourself — only cr is passed
    env['my.model'].search([])._recompute_field()
```

The official upgrade-scripts reference states the parameters verbatim:
`cr` — current database cursor; `version` — installed version of the
module. The runtime error message is
`Each <stage>-upgrade file must have a 'migrate(cr, installed_version)' function`.

> Migration scripts get a raw `cr` on EVERY supported version. Even on
> v17+, where init hooks receive `env`, the migration runner still passes
> the cursor — build your own `Environment` when you need the ORM.

## Idempotency contract (NON-NEGOTIABLE)

Every migration MUST be safe to re-run — a failed-then-retried upgrade can
re-execute it, and reviewers copy scripts to sister branches and run twice.

```python
# DDL — always IF [NOT] EXISTS
cr.execute("ALTER TABLE my_model DROP COLUMN IF EXISTS legacy_field")
cr.execute("CREATE INDEX IF NOT EXISTS my_model_partner_idx ON my_model(partner_id)")

# Data — sentinel guard when there is no schema artifact to introspect
from odoo import api, SUPERUSER_ID
def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    key = 'my_module.migration_17_0_1_2_0_applied'
    if env['ir.config_parameter'].get_param(key):
        return                                   # already applied — no-op
    env['my.model'].search([])._migrate_legacy()
    env['ir.config_parameter'].set_param(key, '1')
```

For non-trivial column renames / table moves, prefer OpenUpgrade's
`openupgradelib` helpers (`rename_columns`, `rename_tables`,
`logged_query`) over hand-rolled SQL — they are themselves idempotent.

## Falsification — re-run safety

```python
# eval_orm_expression — load post-migrate.py, run migrate() twice;
# the second call MUST be a no-op (counts unchanged).
import importlib.util
spec = importlib.util.spec_from_file_location(
    "mig", '/.../my_module/migrations/17.0.1.2.0/post-migrate.py')
mig = importlib.util.module_from_spec(spec); spec.loader.exec_module(mig)
mig.migrate(env.cr, '17.0.1.1.0'); first  = env['my.model'].search_count([('migrated','=',True)])
mig.migrate(env.cr, '17.0.1.1.0'); second = env['my.model'].search_count([('migrated','=',True)])
assert first == second, "Migration is not idempotent"
```

## Hard rules

- Folder name == manifest `version`, full `<major>.0.x.y.z` form.
- File name starts with `pre` / `post` / `end`; order within a phase is
  lexical on the `-*` suffix.
- `migrate(cr, version)` on every version — only `cr` is passed; build the
  ORM `Environment` yourself when needed.
- DDL belongs in `pre-`, record/ORM work in `post-`, cross-module fixups in
  `end-`.
- Every script must be re-run safe: DDL uses `IF [NOT] EXISTS`; data ops use
  a sentinel or a needs-migration predicate.
- Guard on the `version` argument — return early on fresh install (falsy)
  or when the recorded version is already at/above the target.

## Sources

- Upgrade scripts reference, Odoo 17.0 (path format
  `$module/migrations/$version/{pre,post,end}-*.py`, `migrate(cr, version)`
  parameters, phase semantics, lexical ordering) —
  https://www.odoo.com/documentation/17.0/developer/reference/upgrades/upgrade_scripts.html
- `odoo/modules/migration.py` @ 17.0 and 18.0 (`mod.migrate(cr,
  installed_version)`, `migrations/` + `upgrades/` discovery, `VERSION_RE`)
  — https://github.com/odoo/odoo
- OpenUpgrade migration-files convention (OCA) —
  https://oca.github.io/OpenUpgrade/070_migration_files.html
