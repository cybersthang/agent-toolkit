# Odoo — `pre_init_hook` / `post_init_hook` / `uninstall_hook`

Manifest-declared lifecycle callbacks. The **signature changed at Odoo 17**:
v16 and earlier pass raw `cr` (+ `registry`); v17+ pass a ready-built `env`.
Verified against `odoo/modules/loading.py` on tags 15.0 / 16.0 / 17.0.

## Manifest wiring (all versions)

```python
# __manifest__.py — value is the function NAME (string), resolved via getattr
{
    'name': "My Module", 'version': '17.0.1.0.0',
    'depends': ['base', 'mail'],
    'pre_init_hook':  'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
}
```

The string MUST match a top-level callable in the addon-root `__init__.py`.
Odoo does `getattr(py_module, <name>)(...)` — a typo raises `AttributeError`
that is NOT swallowed in modern versions, so install fails loudly; older
code paths could mask it. Always pair with a probe-able side effect.

## Signature by version (VERIFIED)

```python
# ── Odoo 15.0 / 16.0 — loading.py ───────────────────────────
from odoo import api, SUPERUSER_ID

def pre_init_hook(cr):                 # raw cursor only; tables NOT yet created
    cr.execute("ALTER TABLE res_partner DROP CONSTRAINT IF EXISTS legacy_uniq")

def post_init_hook(cr, registry):      # cursor + registry; build env yourself
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['my.model'].search([])._compute_total()

def uninstall_hook(cr, registry):      # cursor + registry
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.config_parameter'].set_param('my_module.installed', False)
```

```python
# ── Odoo 17.0+ — loading.py — env is pre-built ──────────────
def pre_init_hook(env):                # env.cr for raw SQL
    env.cr.execute("ALTER TABLE res_partner DROP CONSTRAINT IF EXISTS legacy_uniq")

def post_init_hook(env):
    env['my.model'].search([])._compute_total()

def uninstall_hook(env):
    env['ir.config_parameter'].set_param('my_module.installed', False)
```

Exact call sites confirmed in source:

| Version | `pre_init_hook` | `post_init_hook` | `uninstall_hook` |
|---|---|---|---|
| 15.0 | `getattr(m, pre_init)(cr)` | `getattr(m, post_init)(cr, registry)` | `getattr(m, uninstall_hook)(cr, registry)` |
| 16.0 | `getattr(m, pre_init)(cr)` | `getattr(m, post_init)(cr, registry)` | `getattr(m, uninstall_hook)(cr, registry)` |
| 17.0 | `getattr(m, pre_init)(env)` | `getattr(m, post_init)(env)` | `getattr(m, uninstall_hook)(env)` |

The official 17.0 manifest reference confirms it in prose: each hook
"receives an environment object as their sole parameter."

> 18.0 / 19.0 / 20.0 follow the 17.0 `(env)` form (stable since the v17
> refactor) — treat as v17 and flag LOW if you cannot read the installed
> source. For v12/v13/v14 the shape matches v15/v16 (`cr` / `cr, registry`):
> describe the stable pre-v17 pattern rather than asserting a specific tag.

## Cross-version addons (one codebase, v16 + v17)

Branch on arity, NOT on `odoo.release.version` (brittle across `saas-N`):

```python
import inspect
from odoo import api, SUPERUSER_ID

def post_init_hook(*args):
    # v17+: args == (env,)        v16-: args == (cr, registry)
    if len(args) == 1:
        env = args[0]
    else:
        env = api.Environment(args[0], SUPERUSER_ID, {})
    _seed(env)
```

## Each hook — when it fires, what's safe

| Hook | Fires | DB state at entry | Use for | NOT for |
|---|---|---|---|---|
| `pre_init_hook` | BEFORE the module's tables/columns are created | Old schema only — your model's table does NOT exist yet | DDL on PRE-EXISTING tables: drop legacy constraints, rename columns, scrub stale `ir_attachment` | ORM on the module's OWN models (table missing → `ProgrammingError`) |
| `post_init_hook` | AFTER all XML/CSV data files load | Full schema + data | Seed records inexpressible in XML, force `_compute` recompute, register runtime cron, conditional Enterprise seeding | Schema DDL (do it in `pre_init_hook`) |
| `uninstall_hook` | On module removal, BEFORE its tables are dropped | Schema + data still present | Clean `ir.config_parameter` keys, archive/detach user data, drop external resources | Re-creating data; assuming a web/HTTP context |

In v15/v16 `pre_init_hook`, the loader calls `registry.setup_models(cr)`
before your hook so the cursor is usable; in v17+ that setup is folded into
the `env` you receive.

## Falsification — did the hook run?

Install can SUCCEED even when a hook string is mis-wired, so prove the
side effect rather than the module state:

```python
# eval_orm_expression
assert env['ir.module.module'].search([('name','=','my_module')]).state == 'installed'
assert env['ir.config_parameter'].get_param('my_module.post_init_ran'), \
    "post_init_hook never ran — manifest hook key likely a typo"
```

## Hard rules

- v16 and earlier: `pre_init_hook(cr)`, `post_init_hook(cr, registry)`,
  `uninstall_hook(cr, registry)`. v17+: every hook takes `(env)`.
- Never call ORM on the module's own models in `pre_init_hook` — the table
  does not exist yet; only DDL / raw SQL on pre-existing tables is safe.
- Never `from odoo.http import request` in a hook — install runs in CLI /
  cron, so `request` is `None`. Use the `env` you are given (or
  `api.Environment(cr, SUPERUSER_ID, {})` on v16-).
- The manifest value is a function-name string, not a callable.
- Pair every hook with a probe-able sentinel (`ir.config_parameter`,
  sentinel record) so a silent no-run is detectable.

## Sources

- `odoo/modules/loading.py` @ 15.0, 16.0, 17.0 (hook call sites) —
  https://github.com/odoo/odoo
- Module Manifests reference, Odoo 17.0 (`pre_init_hook` / `post_init_hook`
  / `uninstall_hook`, "receives an environment object as their sole
  parameter") —
  https://www.odoo.com/documentation/17.0/developer/reference/backend/module.html
