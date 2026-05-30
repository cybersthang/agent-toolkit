# Odoo — Community (CE) vs Enterprise (EE)

The two editions do NOT ship the same addon set. EE = the public `odoo/odoo`
repo (CE) PLUS the separate, non-public `odoo/enterprise` repo mounted on the
`addons_path`. Most mixed-tier install bugs come from assuming the module list
is identical. It is not.

## What differs

| Concern | Community | Enterprise |
|---|---|---|
| Source | `odoo/odoo` (public, LGPL-3) | CE + `odoo/enterprise` (private repo, mostly OEEL-1) |
| `addons_path` | `odoo/addons` (+ OCA) | additionally the `enterprise/` checkout |
| UI / web client | `web` | `web_enterprise` replaces the web layer |
| Accounting | Invoicing only (`account`) | Full accounting via `account_accountant` (assets, follow-ups, etc.) |
| EE-only apps | — | Studio, Documents, Sign, Helpdesk, Planning, Appointments, VOIP, Marketing Automation, Subscriptions, Quality, MRP/PLM add-ons, … |
| License field | `LGPL-3` (default) | `OEEL-1` for proprietary EE modules (some EE modules are still LGPL-3) |

## Dependency rule (HARD)

A Community / LGPL-3 module **must never `depends` on an Enterprise
(OEEL-1) module.** Doing so:

- makes the module un-installable on every CE database, and
- violates the Enterprise license, which forbids incorporating EE code into
  proprietary-incompatible code.

The reverse is allowed: EE modules (and the EE license) may build on top of
any compatibly-licensed Community/OCA module. So depend "downward" toward
CE/`base`, never "upward" toward EE.

If a feature genuinely needs an EE capability, do NOT hard-depend. Either:
1. Ship two modules — `my_module` (CE) + `my_module_enterprise` (depends on
   the EE module, OEEL-1) — the bridge pattern; or
2. Detect EE at runtime (below) and degrade gracefully in CE.

## Common EE-only modules (technical names)

```
web_enterprise          # the EE web client — present in EVERY EE deployment
account_accountant      # full accounting (CE has invoicing-only `account`)
web_studio              # Studio (the module is web_studio, not "studio")
documents               # Documents DMS
sign                    # e-signature
helpdesk                # Helpdesk
planning                # Planning / shift scheduling
appointment             # Online appointments
voip                    # VOIP / click-to-dial
marketing_automation    # Marketing Automation
sale_subscription       # Subscriptions
quality / quality_control
```

Treat any addon importing from one of these (or living under `enterprise/`)
as EE-only. Do not assume an exact `enterprise/` directory listing — that
repo is private; rely on the module's manifest `license` (`OEEL-1`) and its
`depends`.

## Detect edition at runtime (don't hardcode the tier)

Prefer the install-state check — it works inside hooks, cron, and the ORM,
and does not depend on how the server was launched:

```python
def _is_enterprise(env):
    """web_enterprise is the canonical EE sentinel: pulled in by EVERY
    Enterprise deployment, regardless of which apps are licensed."""
    return bool(env['ir.module.module'].search_count([
        ('name', '=', 'web_enterprise'),
        ('state', '=', 'installed'),
    ]))
```

Why `web_enterprise` and not `account_accountant`? `account_accountant` is
opt-in (a CE-with-invoicing-only EE box won't have it), whereas
`web_enterprise` is installed on every EE database.

Lower-level signal — the server build itself carries an edition marker in
`odoo/release.py`: the EE `version` string is suffixed `+e`
(e.g. `'17.0+e'` / historically `'11.0+e-20180424'`) and the last element
of `version_info` is `'e'` on EE builds vs `''` on CE. This tells you what
binary is running, but NOT whether the EE addons are actually installed in
the current database — for install/seed decisions, use the `web_enterprise`
install-state check above.

> The exact `+e` suffix / `version_info` edition flag is set in the
> Enterprise build's `release.py`, which is not in the public repo. The CE
> `release.py` on `odoo/odoo` ends in `''`. Use the `+e` marker as a
> server-edition signal only; treat the DB-level `web_enterprise` check as
> authoritative for install logic.

## Conditional install hook + falsification

```python
def post_init_hook(env):                  # v17+ signature
    if _is_enterprise(env):
        _seed_enterprise_records(env)     # e.g. documents.document, studio data
        env['ir.config_parameter'].set_param('my_module.tier_seeded', 'enterprise')
    else:
        _seed_community_records(env)       # degrade gracefully
        env['ir.config_parameter'].set_param('my_module.tier_seeded', 'community')
```

```python
# eval_orm_expression
is_ee = bool(env['ir.module.module'].search_count(
    [('name','=','web_enterprise'), ('state','=','installed')]))
seeded = env['ir.config_parameter'].get_param('my_module.tier_seeded')
assert seeded == ('enterprise' if is_ee else 'community')
```

## Hard rules

- A CE / LGPL-3 module must NOT `depends` on an EE / OEEL-1 module — split
  into a CE base + an EE bridge module, or detect EE at runtime.
- Never assume the addon list is identical across editions.
- Detect EE via `web_enterprise` install state, not by hardcoding a flag and
  not via `account_accountant` (which is opt-in).
- The `+e` suffix / `version_info[-1] == 'e'` tells you the server edition,
  not whether EE apps are installed in the DB.
- Set the manifest `license` honestly: `LGPL-3` for Community-distributable
  code, `OEEL-1` only for Enterprise-licensed code (`OPL-1` is the separate
  Odoo Apps Store proprietary license).

## Sources

- Licenses, Odoo 17.0 (CE = LGPL-3; EE = OEEL-1; EE license permits using
  compatibly-licensed modules alongside it, but CE code may not incorporate
  EE code) — https://www.odoo.com/documentation/17.0/legal/licenses.html
- Module Manifests, Odoo 17.0 (`license` allowed values incl. `LGPL-3`,
  `OEEL-1`, `OPL-1`) —
  https://www.odoo.com/documentation/17.0/developer/reference/backend/module.html
- `odoo/release.py` @ 17.0 (CE `version_info` ends in `''`) —
  https://github.com/odoo/odoo ; EE `+e` version-string suffix —
  https://www.odoo.com/forum/help-1/how-to-check-if-odoo-ee-is-installed-157643
