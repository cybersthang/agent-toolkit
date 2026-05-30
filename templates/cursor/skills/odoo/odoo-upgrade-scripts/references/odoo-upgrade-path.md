# The Odoo upgrade path — sequential, version-by-version

Odoo upgrades are a **chain, not a hop**. Standard-addon migrations (and
OCA OpenUpgrade scripts) are version-keyed: `migrations/15.0.x/` runs
only when the prior `ir.module.module.latest_version` was `14.x`. Skipping
a major means the intermediate migrations NEVER execute — half-applied
schema, corrupted `account.move` (SKILL.md §3 Anti-Pattern A).

## The golden rule: one major per `-u` run

```bash
# WRONG — restore a v14 dump onto a v17 server, upgrade once. 15.0 + 16.0
# migrations are skipped. Random tracebacks, silent data corruption.
pg_restore -d prod_v17 prod_v14.dump
/opt/odoo17/odoo-bin -d prod_v17 -u all --stop-after-init   # NO

# RIGHT — walk the chain, one major at a time, snapshotting between hops.
for v in 15 16 17; do
    /opt/odoo${v}/odoo-bin -c odoo${v}.conf -d prod -u all --stop-after-init
    pg_dump prod > backup_after_v${v}.dump        # rollback point per hop
done
```

`12 → 17` means running the upgrade FIVE times (12→13, 13→14, 14→15,
15→16, 16→17), each on the matching Odoo binary + addons checkout.

## Three upgrade paths (recap — full table in SKILL.md §1)

| Path | Edition | Covers | You still own |
|---|---|---|---|
| **A. Custom migrations** | any | your `migrations/<v>/{pre,post}-migration.py` | — (always required) |
| **B. OpenUpgrade** | Community | standard Odoo addons | your custom addons (Path A) |
| **C. upgrade.odoo.com** | Enterprise | standard + Enterprise addons | your custom addons (Path A) |

- **Community** → Path B (`openupgrade_scripts`) for std addons + Path A.
- **Enterprise** → Path C (`upgrade.odoo.com`) for std/ent addons + Path A.
- Path A is non-negotiable: neither B nor C touches third-party modules.

## CE vs EE — concretely different pipelines

**Community (Path B):** put the matching `OCA/OpenUpgrade` branch on the
addons path and run the upgrade. OpenUpgrade pins the server version
(its `openupgrade_scripts` ships per-version scripts under
`scripts/<addon>/<version>/`). One OCA branch per major — pin to the
exact target (`17.0` branch for a v17 target).

```bash
# Community, v16 → v17, OpenUpgrade on the addons path
/opt/odoo17/odoo-bin -c odoo17.conf -d prod \
    --addons-path=/opt/odoo17/addons,/opt/OpenUpgrade-17.0,/opt/custom \
    -u all --stop-after-init
```

**Enterprise (Path C):** black-box service — POST a dump, GET a
transformed dump. Custom modules are NOT migrated.

```bash
pg_dump --no-owner --no-privileges prod > prod_v16.dump
# "test" request first — free + repeatable; "production" is billed by DB size.
python <(curl -s https://upgrade.odoo.com/upgrade) test \
    -d prod_v16.dump -t 17.0 --contract <enterprise-contract-code>
createdb prod_v17 && pg_restore -d prod_v17 prod_v17_upgraded.dump
/opt/odoo17/odoo-bin -c odoo17.conf -d prod_v17 -u my_module --stop-after-init  # Path A
```

`upgrade.odoo.com` also walks the chain internally — you submit the
source dump and a single target; Odoo S.A. runs the intermediate steps.
For your OWN addons you still walk each major with Path A.

## `migrations/<version>/` script layout (Path A)

```
my_module/
├── __manifest__.py                 # version = "17.0.1.0.0"
└── migrations/
    └── 17.0.1.0.0/                 # MUST equal __manifest__.version EXACTLY
        ├── pre-migration.py        # before models load — SQL, renames
        ├── post-migration.py       # after models load + data — backfill
        └── end-migration.py        # after ALL modules migrated (rare)
```

| Hook | Runs | `migrate()` arg | Use for |
|---|---|---|---|
| `pre-migration.py` | before ORM schema sync | `cr` | `ALTER TABLE`, drop constraints, `openupgrade.rename_*` |
| `post-migration.py` | after ORM + data update | `cr` (build env) | data backfill, recompute stored fields, fix `ir.model.data` |
| `end-migration.py` | after every module migrated | `cr` | cross-module consistency (rare) |

Directory name must equal `version` **string-for-string**: `17.0.1.0`
vs `17.0.1.0.0` silently skips (SKILL.md §8). Signature + idempotency
rules: SKILL.md §2. Helper catalog: `odoo-openupgrade-helpers.md`.

## Testing an upgrade (the only real gate)

Functional clicking is NOT a gate. Aggregate parity is (SKILL.md §3-C, §7).

```bash
# 1. Restore a PRODUCTION-representative dump (real edge-case distribution:
#    multi-currency, partially-paid, refunded — staging rarely has these).
createdb prod_test && pg_restore -d prod_test prod.dump

# 2. Neutralize (see below) so the test DB can't email/charge/cron.

# 3. Walk the chain ONE major at a time, capturing logs.
/opt/odoo17/odoo-bin -c test.conf -d prod_test -u all --stop-after-init \
    --logfile=upgrade_v17.log
grep -E "DeprecationWarning|ERROR|CRITICAL" upgrade_v17.log   # gate on these
```

```sql
-- 4. Before/after aggregate parity (run the SAME probe on source + target).
SELECT date_trunc('month', date), state, currency_id,
       COUNT(*), SUM(amount_total), SUM(amount_residual)
FROM account_move WHERE date >= '2024-01-01' GROUP BY 1,2,3 ORDER BY 1,2,3;
-- Repeat for sale_order, purchase_order, stock_move, mrp_production.
-- Totals must match modulo DOCUMENTED semantic shifts (cite release notes).
```

```python
# 5. Confirm migrations actually ran (no stale latest_version).
stale = env['ir.module.module'].search([
    ('state', '=', 'installed'), ('latest_version', 'not like', '17.0%')])
assert not stale, stale.mapped('name')   # non-empty → skipped migrations
```

## Neutralization (MANDATORY on any non-prod copy)

A restored prod dump retains live mail servers, payment credentials,
crons, and outgoing connections. Neutralize BEFORE touching it — a test
upgrade must not email customers or charge cards.

```bash
# Odoo 16+ ships a built-in neutralize routine:
/opt/odoo17/odoo-bin -c test.conf -d prod_test --stop-after-init \
    --no-http neutralize          # or click Settings ▸ "Neutralize database"
```

Neutralization disables outgoing mail servers, deactivates `ir.cron`
jobs, switches payment providers to test mode, blanks API keys, and tags
the DB. On pre-16 servers, run the equivalent SQL manually (disable
`ir.mail_server`, `fetchmail.server`, set `ir.cron.active = false`,
`payment.provider`/`payment.acquirer` state to `test`). Re-neutralize
after EACH restore — it is not sticky across `pg_restore`.

## Rollback discipline

- `pg_dump` between every major hop (the loop above) — each is a
  restore point if the next hop fails.
- Never edit an already-applied migration to "fix forward" on prod —
  bump `version`, add a new `migrations/<new-version>/` dir (SKILL.md
  §3-B). Editing diverges staging/DR from prod.

## Hard rules

- One major per `-u` run. Never restore-and-skip.
- Match the Odoo BINARY + addons checkout to each hop's major.
- Community = B + A; Enterprise = C + A. Path A always.
- Pin the `OCA/OpenUpgrade` branch to the exact target major.
- Neutralize every restored copy before upgrading.
- Gate on before/after aggregate parity + a clean deprecation log, not
  on clicking around.

> Sources: [Odoo upgrade docs](https://www.odoo.com/documentation/17.0/administration/upgrade.html),
> [database neutralization](https://www.odoo.com/documentation/17.0/administration/upgrade.html),
> [`OCA/OpenUpgrade`](https://github.com/OCA/OpenUpgrade). Re-confirm the
> neutralize CLI flag for your exact server version.
