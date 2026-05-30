---
name: odoo-module-install-scripts
description: Odoo module install/upgrade automation — `__manifest__.py` `pre_init_hook` / `post_init_hook` / `uninstall_hook` signatures (cr → env delta at v15), the `migrations/<version>/<phase>.py` convention (pre-migration schema ops vs post-migration record ops), idempotency contract, Community vs Enterprise install-path divergence (modules only in `enterprise/`, runtime detection via `web_enterprise`), top 5 anti-patterns (heavy ORM in pre_init, non-idempotent migrations, `request.env` in install hooks, missing `_logger`, hard-coded `company_id=1`), falsification recipes via `eval_orm_expression`, H/M/L code-review checklist for `__init__.py` / `__manifest__.py` / `migrations/**/*.py`. Open whenever the user says "install", "upgrade", "migration", "migrate", "module install", "pre_init_hook", "post_init_hook", "uninstall_hook", "cài đặt", "nâng cấp", or when code-review surfaces a manifest/migration finding.
license: MIT
---

# Odoo — Module Install / Upgrade Scripts

Install-time bugs are the most expensive class in Odoo: they fire once
per environment, can corrupt production on first deploy, and the
failure mode (`ProgrammingError`, half-applied schema, orphaned
`ir_attachment`) is irreversible without backup restore.

This skill covers lifecycle hooks, `migrations/` folder convention,
Community vs Enterprise divergence, and top 5 anti-patterns. Pair with
`odoo-code-review` (severity anchors) and `odoo-data-verification`
(probes to confirm a hook ran).

## 0. Version detection (MANDATORY first step)

Hook signatures changed at **v17** (verified against installed Odoo
source 2026-05-29: odoo-15.0 uses `def pre_init_hook(cr):` /
`def post_init_hook(cr, registry):`; odoo-16.0 still uses `(cr, registry)`;
odoo-17.0 onwards uses `(env)`). Pre-v0.27.1 docs said v15 — that
was wrong.

1. `__manifest__.py` `version` — `codebase.read_manifest({module_path})`. Pattern `^(\d+)\.0\.`.
2. Fallback signals: `(cr, registry)` / `(cr)` arity → ≤16; `(env,)` arity → ≥17; manual `api.Environment(cr, SUPERUSER_ID, {})` inside a hook → ≤16.
3. Ask the user only if signals are inconclusive.

Then load `references/odoo-pre-post-init-hooks.md` (matching §"pre-v17"
/ "v17+ canonical"; treat v18-20 as v17 + flag LOW).
Migration-folder semantics are **stable since v10** — always load
`references/odoo-migrations-convention.md`. Community vs Enterprise is
**runtime-detectable** (§3) — load `references/odoo-community-vs-enterprise.md`
whenever the addon imports from `enterprise/` or guards on
`web_enterprise`.

## 1. Module lifecycle hooks (Confidence: H)

Up to 3 hook callbacks declared in `__manifest__.py`:

| Hook | When it fires | Typical use | DB state at entry |
|---|---|---|---|
| `pre_init_hook` | BEFORE module tables/columns created | Drop legacy constraints, rename pre-existing columns, scrub stale `ir_attachment` | Old schema only |
| `post_init_hook` | AFTER all XML/CSV data files load | Seed records inexpressible in XML, trigger `_compute` recompute, register cron at runtime | Full schema + data loaded |
| `uninstall_hook` | On module remove (before tables drop) | Cleanup `ir.config_parameter` keys, archive user data, detach `ir_attachment` | Schema + data still present |

### 1.1 Signature delta (v14 vs v15+)

```python
# v12 / v13 / v14 — __init__.py at addon root
from odoo import api, SUPERUSER_ID

def pre_init_hook(cr):                          # raw cursor only
    cr.execute("ALTER TABLE my_model DROP CONSTRAINT IF EXISTS my_model_name_uniq")

def post_init_hook(cr, registry):               # build env manually
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['my.model'].search([])._compute_total()

# v15+ (canonical from v17) — env pre-built; use env.cr for raw SQL
def pre_init_hook(env): ...
def post_init_hook(env): ...
def uninstall_hook(env): ...
```

Cross-version addons (v14 + v17): branch on
`len(inspect.signature(...).parameters)`, not `odoo.release.version`
(brittle across saas-N).

### 1.2 `__manifest__.py` wiring

```python
{
    'name': "My Module", 'version': '17.0.1.0.0',
    'depends': ['base', 'mail'],
    'data': ['security/ir.model.access.csv', 'views/my_model_views.xml'],
    'pre_init_hook': 'pre_init_hook',       # function NAME, not a callable
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
}
```

The string MUST match a top-level callable in `__init__.py`. Odoo uses
`getattr(<module>, <hook_name>)` — typos fail silently (`AttributeError`
swallowed; hook simply doesn't run).

### Falsification — did the hook actually run?

```python
# eval_orm_expression
assert env['ir.module.module'].search([('name','=','my_module')]).state == 'installed'
assert env['ir.config_parameter'].get_param('my_module.installed_at'), \
    "post_init_hook never ran — manifest hook key likely typo"
```

If the manifest hook string is wrong, **install still succeeds** —
that's the trap. Always pair a manifest hook with a probe-able side
effect (`set_param`, sentinel record) so absence is detectable.

## 2. `migrations/<version>/<phase>.py` convention (Confidence: H)

For *upgrades* (manifest version bumped), manifest hooks are NOT
enough — Odoo also auto-runs scripts from `migrations/`.

### 2.1 Directory layout

```
my_module/
  __manifest__.py        # version = '17.0.1.0.1'
  migrations/
    17.0.1.0.1/
      pre-migration.py   # schema-level (DROP COLUMN, RENAME, fix constraints)
      post-migration.py  # record-level (data transforms, recompute)
      end-migration.py   # rarely used; after every module's post-migration
```

Version dir MUST match manifest `version` exactly (`17.0.1.0.1` — full
`<major>.0.<x>.<y>.<z>`, not just `1.0.1`).

### 2.2 Phase semantics

| File | Fires | Safe | NOT safe |
|---|---|---|---|
| `pre-migration.py` | BEFORE new schema loaded | `ALTER TABLE`, `DROP CONSTRAINT`, `RENAME COLUMN`, raw SQL | ORM on removed/renamed fields |
| `post-migration.py` | AFTER new schema + data re-applied | Record-level ORM, compute triggers | Schema DDL (use pre-) |
| `end-migration.py` | After ALL modules in upgrade batch finish post-migration | Cross-module fixups | Intra-module ordering deps |

### 2.3 Hook signature (same `cr` → `env` delta)

```python
# v14- : migrations/17.0.1.0.1/pre-migration.py
def migrate(cr, version):               # version = OLD value in ir_module_module
    if version and version < '17.0.1.0.1':
        cr.execute("ALTER TABLE my_model DROP COLUMN IF EXISTS legacy_field")

# v15+ : same path
def migrate(env, version):
    if version and version < '17.0.1.0.1':
        env.cr.execute("ALTER TABLE my_model DROP COLUMN IF EXISTS legacy_field")
```

### 2.4 Idempotency contract (NON-NEGOTIABLE)

**Every migration MUST be safe to re-run.** Odoo may re-execute on a
failed-then-retried upgrade; DEV will copy-paste to a sister branch
and run twice. Defensive patterns:

```python
# DDL: always IF [NOT] EXISTS
env.cr.execute("ALTER TABLE my_model DROP COLUMN IF EXISTS legacy_field")
env.cr.execute("CREATE INDEX IF NOT EXISTS my_model_partner_idx ON my_model(partner_id)")

# Data: sentinel guard via ir.config_parameter (preferred when no DDL to introspect)
key = 'my_module.migration_17_0_1_0_1_applied'
if not env['ir.config_parameter'].get_param(key):
    env['my.model'].search([])._migrate_legacy_field()
    env['ir.config_parameter'].set_param(key, '1')
```

### Falsification — re-run safety

```python
# eval_orm_expression — load post-migration.py via importlib, run migrate() twice;
# second invocation MUST be a no-op (record counts unchanged).
import importlib.util
spec = importlib.util.spec_from_file_location("mig", '/.../migrations/17.0.1.0.1/post-migration.py')
mig = importlib.util.module_from_spec(spec); spec.loader.exec_module(mig)
mig.migrate(env, '17.0.1.0.0'); first  = env['my.model'].search_count([('migrated','=',True)])
mig.migrate(env, '17.0.1.0.0'); second = env['my.model'].search_count([('migrated','=',True)])
assert first == second, "Migration is not idempotent"
```

## 3. Community vs Enterprise install paths (Confidence: H)

Most mixed-tier bugs trace back to "the addon list is the same in
Community and Enterprise." **It is not.**

### 3.1 What differs

| Concern | Community | Enterprise |
|---|---|---|
| Addon paths | `odoo/addons/`, OCA | additionally `enterprise/` (separate repo/submodule) |
| EE-only modules | — | `studio`, `voip`, `marketing_automation`, `documents`, `helpdesk`, `account_accountant`, `web_enterprise`, `sale_subscription`, … |
| Theme | `web` | `web_enterprise` (replaces UI layer) |
| `account` | Basic invoicing | Full accountant (depreciation, follow-up, consolidation) |
| Install order | Alphabetical within `addons_path` | Enterprise paths FIRST → EE variants win on collision |

### 3.2 Runtime detection (don't hardcode tier)

```python
def _is_enterprise(env):
    """web_enterprise is the canonical Enterprise sentinel."""
    return bool(env['ir.module.module'].search_count([
        ('name', '=', 'web_enterprise'), ('state', '=', 'installed'),
    ]))
```

Why `web_enterprise` (not `account_accountant`)? It's the **only**
module pulled in by *every* EE deployment regardless of licensed apps;
`account_accountant` is opt-in.

### 3.3 Conditional install hook + falsification

```python
def post_init_hook(env):
    if _is_enterprise(env):
        _seed_enterprise_only_records(env)   # Studio, documents.document
    else:
        _seed_community_records(env)         # degrade gracefully
```

```python
# eval_orm_expression
is_ee = _is_enterprise(env)
sentinel = env['ir.config_parameter'].get_param('my_module.tier_seeded')
assert sentinel == ('enterprise' if is_ee else 'community')
```

## 4. Top 5 anti-patterns

### 4.1 Heavy ORM ops in `pre_init_hook` — **Confidence: H**

`pre_init_hook` runs BEFORE tables exist. ORM on the module's own
models fails (table not found); ORM on other modules works but is
fragile (load order is not your friend).

```python
# Bad — my.model's table doesn't exist yet
def pre_init_hook(env): env['my.model'].search([])._compute_total()

# Good — DDL + raw SQL on PRE-EXISTING tables
def pre_init_hook(env):
    env.cr.execute("ALTER TABLE res_partner DROP CONSTRAINT IF EXISTS legacy_uniq")
```

### 4.2 Non-idempotent migration scripts — **Confidence: H**

See §2.4. Every `INSERT` without `ON CONFLICT`, every `UPDATE` without
a needs-migration predicate, every `CREATE INDEX` without `IF NOT EXISTS`
is a re-run bomb.

### 4.3 Using `request.env` in install hooks — **Confidence: H**

Hooks run in CLI / cron / web-install — no HTTP request,
`odoo.http.request` is `None`.

```python
# Bad — request is None during install
from odoo.http import request
def post_init_hook(env): user = request.env.user

# Good — use the env passed in (or api.Environment on pre-v15)
def post_init_hook(env): user = env.user
```

### 4.4 Logging without `_logger` — **Confidence: M**

Install runner pipes through the Odoo logger. Bare `print()` lands in
buffered stdout; tracebacks lose addon name.

```python
import logging
_logger = logging.getLogger(__name__)
def post_init_hook(env):
    _logger.info("my_module: seeding %d records", count)   # not print()
```

### 4.5 Hardcoded `company_id=1` in seed data — **Confidence: H**

`id=1` is convention only. In multi-company customer DBs, the primary
company may be `id=3` (1+2 template-provisioned and archived).

```python
# Bad
env['my.model'].create({'name': 'Default', 'company_id': 1})

# Good — one record per active company, scoped via with_company()
for company in env['res.company'].search([]):
    env['my.model'].with_company(company).create({
        'name': 'Default', 'company_id': company.id,
    })
```

Cross-link: `odoo-multi-company` §1 (Pattern A) — runtime flavor.

## 5. Falsification recipes — toolbox

All assume `eval_orm_expression` MCP probe is available.

```python
# Module state + recorded version
m = env['ir.module.module'].search([('name','=','my_module')])
assert m.state == 'installed'; m.latest_version

# Did pre/post_init_hook fire? (paired with a set_param sentinel)
env['ir.config_parameter'].get_param('my_module.pre_init_ran')
env['ir.config_parameter'].get_param('my_module.post_init_ran')

# Enterprise deployment?
bool(env['ir.module.module'].search_count([('name','=','web_enterprise'), ('state','=','installed')]))

# Migration <version> applied? (sentinel)
env['ir.config_parameter'].get_param('my_module.migration_17_0_1_0_1_applied')
```

Pair with `odoo-data-verification` for deeper post-install checks
(records seeded, computes triggered, cron registered).

## 6. Code-review checklist (H/M/L)

### `__manifest__.py`

| Sev | Check |
|---|---|
| H | `pre_init_hook` / `post_init_hook` / `uninstall_hook` resolve to real top-level callables in `__init__.py` |
| H | `version` has 5 dotted segments (`17.0.1.0.0`), not 3 |
| H | `depends` lists every module whose models the hooks touch |
| M | `license` declared (LGPL-3 / OEEL-1 — affects Enterprise compat) |
| M | `data` files load BEFORE `post_init_hook` — don't seed in XML what the hook re-seeds |
| L | `installable: True` (or absent) |

### `__init__.py` (addon root)

| Sev | Check |
|---|---|
| H | Hook callables match manifest strings character-for-character |
| H | Hook signature matches detected major (v14: `(cr, registry)`, v15+: `(env,)`) |
| H | No `from odoo.http import request` in hook module |
| M | `_logger = logging.getLogger(__name__)` at module top |
| L | No top-level side effects on `import` |

### `migrations/**/*.py`

| Sev | Check |
|---|---|
| H | `def migrate(env, version):` (v15+) or `def migrate(cr, version):` (v14) — name + arity exact |
| H | Every DDL uses `IF [NOT] EXISTS` |
| H | Every data mutation sentinel-guarded (`ir.config_parameter` or column-existence) |
| H | Version dir name matches manifest `version` exactly |
| M | Long-running `UPDATE` paginated on tables >100k rows |
| M | `_logger.info()` at start + end of `migrate()` |
| L | `version` parameter inspected to skip when irrelevant |

## 7. References & cross-references

References (this skill):
- `references/odoo-pre-post-init-hooks.md` — hook signatures per major, manifest wiring, per-phase pitfalls
- `references/odoo-migrations-convention.md` — OCA / openupgrade folder layout, idempotency patterns, end- vs post-migration
- `references/odoo-community-vs-enterprise.md` — module list deltas, addons_path ordering, runtime detection, LGPL-3 vs OEEL-1

Sibling skills:
- Runtime `with_company()` flavor → `odoo-multi-company` §1
- Install-finding severity anchors → `odoo-code-review` §B + `references/odoo-<N>-rules.md` §F
- Probes verifying install side effects → `odoo-data-verification`
- Manifest + `__init__.py` skeleton → `odoo-module-scaffold`
- EE-only model patterns → `odoo-enterprise-patterns`; Community fallback → `odoo-community-patterns`

Call BEFORE this skill:
- `odoo-codebase-discovery` — locate target module + read `__manifest__.py`
- `odoo-deterministic-answers` — `lookup_canonical_decision` for project-specific install rules

## 8. Hard rules summary

- Never call ORM on the module's OWN models in `pre_init_hook` — tables don't exist yet.
- Never write a migration unsafe to re-run — DDL needs `IF [NOT] EXISTS`, data ops need a sentinel.
- Never use `request.env` (or any `odoo.http` import) in install / migration hooks — no HTTP context.
- Never `print()` in install hooks — use `_logger`.
- Never hardcode `company_id=1` in seed data — iterate `env['res.company'].search([])` and scope via `with_company()`.
- Never assume Community == Enterprise — detect via `web_enterprise` install state and branch.
- Never trust the manifest hook string ran — pair with a probe-able sentinel `ir.config_parameter` so absence is detectable.
