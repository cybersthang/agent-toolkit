# OpenUpgrade + `openupgradelib` helper catalog

OCA's **OpenUpgrade** is the community-driven upgrade pipeline for
Community Edition. Two distinct OCA repos:

| Repo | Pip / addon | What it is |
|---|---|---|
| [`OCA/openupgradelib`](https://github.com/OCA/openupgradelib) | `pip install openupgradelib` → `from openupgradelib import openupgrade` | **Library** of helper functions called from any `migrations/<v>/*.py`. |
| [`OCA/OpenUpgrade`](https://github.com/OCA/OpenUpgrade) | `openupgrade_scripts` addon on the addons path | Per-version migration **scripts for standard Odoo addons**. One branch per major (`13.0`, `14.0`, …). |

Use `openupgradelib` in YOUR addons' migrations (Path A). Install
`openupgrade_scripts` to migrate Odoo's OWN addons (Path B). See
`odoo-upgrade-path.md`.

## Why helpers, not raw SQL

`ALTER TABLE … RENAME COLUMN` touches PG only. A rename must ALSO update
`ir.model.fields`, `ir.model.data`, `ir.ui.view`, stored field
translations, `ir.filters`, and `ir.exports`. The helpers do that
bookkeeping atomically (SKILL.md §3 Anti-Pattern E). Never hand-roll.

## Two call styles

```python
# Style 1 — raw cursor (pre-migration; env not yet usable)
def migrate(cr, version):
    if not version:
        return                       # fresh install, not an upgrade
    from openupgradelib import openupgrade
    openupgrade.rename_columns(cr, {'my_table': [('old', 'new')]})

# Style 2 — @migrate decorator (OCA preferred; sets up env, logs, gates)
from openupgradelib import openupgrade

@openupgrade.migrate()               # injects env, auto version-gate + log
def migrate(env, version):           # NOTE: env, not cr — use env.cr for SQL
    openupgrade.logged_query(env.cr, "UPDATE my_table SET x = 1 WHERE x IS NULL")
```

`@openupgrade.migrate()` handles the `if not version: return` gate and
logs entry/exit — strictly preferred over hand-rolled
`api.Environment(cr, SUPERUSER_ID, {})`.

## Rename helpers (the core use case)

```python
# Columns — pre-migration. dict: {table: [(old, new), ...]}
openupgrade.rename_columns(cr, {'sale_order': [('old_field', 'new_field')]})

# Tables (+ their sequences) — pre-migration. dict: {old: new}
openupgrade.rename_tables(cr, {'old_table': 'new_table'})

# Models — pre-migration. Updates relation fields pointing at the model.
# list of (old_model, new_model). NOTE: rename the table separately if it changed.
openupgrade.rename_models(cr, [('payment.acquirer', 'payment.provider')])

# Fields — FULL rename (column + ir.model.fields + ir.model.data + views +
# translations + filters + exports). Takes ENV. list of
# (model, table, old_field, new_field).
openupgrade.rename_fields(env, [('sale.order', 'sale_order', 'old', 'new')])

# XML IDs — pre-migration. list of (old_xmlid, new_xmlid). allow_merge=True
# folds onto an existing target id.
openupgrade.rename_xmlids(cr, [('module.old_id', 'module.new_id')])
```

Rule of thumb: in **pre-migration** rename columns/tables/models/xmlids
(cursor-based, schema-level, before ORM loads). Use `rename_fields`
(env-based) when you want the complete metadata sweep including views and
translations.

## Existence guards (idempotency)

```python
if openupgrade.column_exists(cr, 'sale_order', 'new_field'):
    ...                                            # safe to read/transform
if not openupgrade.table_exists(cr, 'new_table'):
    ...                                            # create / skip accordingly
```

Pair these with `IF EXISTS` / `IF NOT EXISTS` in raw SQL (SKILL.md §2
Idempotency) — migrations may re-run during recovery.

## Logged query (always log mutations)

```python
# Logs the query + affected-row count at DEBUG. The forensic trail when an
# upgrade dies halfway (SKILL.md §2).
openupgrade.logged_query(
    cr,
    "UPDATE %(t)s SET state = %%s WHERE state = %%s" % {'t': 'account_move'},
    ('posted', 'open'),
)
# skip_no_result=True silences the warning when zero rows match.
```

`logged_query` is the OpenUpgrade-idiomatic replacement for bare
`cr.execute()` — use it for every data mutation so the upgrade log shows
what ran and how many rows changed.

## Column / field pre-population (avoid stored-compute storms)

```python
# Pre-create a PG column so Odoo's loader does NOT recompute a new stored
# field across millions of rows on first boot. add_fields also creates the
# ir.model.fields + ir.model.data entries. Both take env.
openupgrade.add_columns(env, {'my_module': [('my.model', 'new_total', 'numeric')]})
openupgrade.add_fields(env, [('my.model', 'my_table', 'new_total', 'float', False, 'my_module')])
```

This is the standard trick when a new major adds a stored computed field:
fill the column in pre-migration, then the ORM trusts it instead of
recomputing.

## Data + value mapping

```python
# Load an XML/CSV/YAML data file shipped inside your migration dir.
openupgrade.load_data(env.cr, 'my_module', 'migrations/17.0.1.0.0/noupdate.xml')

# Remap old selection/state values to new ones (model OR table).
openupgrade.map_values(
    cr, 'state', 'state',
    [('open', 'posted'), ('paid', 'posted')],
    table='account_move',
)

# Set defaults on newly-required fields (use_orm=True to honor compute/related).
openupgrade.set_defaults(cr, env.registry, {'my.model': [('new_field', 'X')]})
```

## Safe deletion

```python
# Remove obsolete records by xml id without tripping FK / NOT NULL constraints.
openupgrade.delete_records_safely_by_xml_id(
    env, ['my_module.obsolete_record'], delete_childs=True,
)
```

## Helper → bookkeeping it performs

| Helper | PG column | `ir.model.fields` | `ir.model.data` | Views | Translations |
|---|:--:|:--:|:--:|:--:|:--:|
| `rename_columns` | yes | no | no | no | no |
| `rename_tables` | table+seq | no | no | no | no |
| `rename_models` | no | refs | no | rel. fields | no |
| `rename_fields` | yes | yes | yes | yes | yes |
| `rename_xmlids` | no | no | yes | no | no |

`rename_columns` is the lightest (PG only) — use it only when you
separately fix the ORM metadata or the column is internal. For a
user-visible field, `rename_fields` is the safe default.

## Canonical rename data — `apriori.py`

To **verify or look up** a model, module, or field rename for a target
major **N**, read the OCA/OpenUpgrade branch **`N.0`** file
`openupgrade_scripts/apriori.py`. It is the authoritative "what changed
between N-1 and N" data — not just migration scripts. Branch **`N.0`**
holds the **(N-1) → N** deltas (e.g. branch `17.0` records what changed
going from 16 to 17).

`apriori.py` defines these dicts:

| Dict | Maps |
|---|---|
| `renamed_models` | old model name → new model name |
| `merged_models` | model folded into another → target model |
| `renamed_modules` | old module (technical) name → new module name |
| `renamed_fields` | per-model field renames |

```python
# 16.0/apriori.py   — confirmed entry
renamed_models = {"payment.acquirer": "payment.provider", ...}
# 17.0/apriori.py   — confirmed entry
renamed_models = {"mail.channel": "discuss.channel", ...}
```

For **field-level** diffs, also read the per-module
`openupgrade_analysis.txt` shipped alongside each addon's migration in the
same branch — it records the column/field-level changes module by module.

Raw URL pattern (substitute the target major for `<N>`):

```
https://raw.githubusercontent.com/OCA/OpenUpgrade/<N>.0/openupgrade_scripts/apriori.py
```

Chain the lookups across every major between source and target (one
`apriori.py` per major), the same way the upgrade itself chains.

## Hard rules

- Never `ALTER TABLE … RENAME` directly — use `rename_columns` /
  `rename_fields` (SKILL.md §3-E). If `openupgradelib` is unavailable,
  replicate the bookkeeping (`ir.model.fields`, `ir.model.data`, views,
  translations) by hand — never PG-only.
- Prefer `@openupgrade.migrate()` over manual `api.Environment(...)`.
- Mutate via `logged_query`, not bare `cr.execute`, for the audit trail.
- Guard every helper with `if not version: return` (or let the decorator
  do it) — fresh installs must NOT run migration logic.
- Pin the OCA branch to the EXACT target major (`OpenUpgrade` `17.0`
  branch for a v17 target); scripts are version-keyed.

> Sources: [`OCA/openupgradelib` API](https://oca.github.io/openupgradelib/API.html),
> [`OCA/OpenUpgrade` docs](https://oca.github.io/OpenUpgrade/),
> [openupgradelib on PyPI](https://pypi.org/project/openupgradelib/).
> Verify signatures against the API page — minor signatures shift between
> library releases.
