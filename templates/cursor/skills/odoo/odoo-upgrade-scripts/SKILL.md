---
name: odoo-upgrade-scripts
description: Cross-version Odoo upgrade pipeline — choosing between custom per-module `migrations/<version>/{pre,post}-migration.py`, OCA `openupgrade_scripts` (community), and Odoo's official `upgrade.odoo.com` service (Enterprise). Embedded breaking-change inventory v12→v20 (`@api.one`/`@api.multi` removal, `account.invoice`→`account.move`, `payment.acquirer`→`payment.provider`, `name_get()`→`_compute_display_name`, `attrs=`/`states=` removal, OWL refactor, mail framework v2). Top 5 upgrade anti-patterns (skip-version, edit-applied-script, no source/target parity test, ignored deprecations, SQL renames). Falsification via `ir.module.module.latest_version` + before/after aggregates on `account.move` / `sale.order`. Trigger phrases: "upgrade", "migration", "nâng cấp", "v12 to v17", "openupgrade", "upgrade.odoo.com", "version migration", "breaking change".
license: MIT
---

# Odoo — Cross-Version Upgrade Scripts (v12 → v20)

Major-version upgrades are the *highest-blast-radius* operation in an
Odoo consultancy's lifecycle: data, schema, ORM API, JS framework, and
view DSL all shift simultaneously, and the failure modes are
silent-corruption (off-by-one totals on `account.move`) before they are
loud-error (server fails to boot).

This skill enumerates the **three upgrade paths**, the **version-by-version
breaking-change inventory**, the **top 5 anti-patterns**, and the
**falsification recipes**.

> Module-agnostic: never assumes project module names. Discover the addon
> set via `codebase.list_manifests` first, then read each
> `__manifest__.py` `version` field to learn the source major.

Pair with `odoo-code-review` (severity anchors), `odoo-module-install-scripts`
(the hook pattern that backs migrations), and `odoo-data-verification`
(live ORM probes against the upgraded DB).

## 0. Version detection (MANDATORY first step)

1. **`__manifest__.py` `version` field** — `codebase.read_manifest({module_path})`.
   Pattern `^(\d+)\.0\.`. This is the **source** major.
2. **Target** major: ask DEV directly ("v17", "v18"); never infer.
3. **Fallback signals** (only if manifest's `version` is missing):
   - `@api.one` → ≤12. `@api.multi` → ≤12 (removed in v13).
   - `account.invoice` model references → ≤12 source.
   - `payment.acquirer` references → ≤14 source.
   - `name_get(self)` without `_compute_display_name` → ≤16.
4. **Ask DEV** when signals are inconclusive — never guess across two majors.

Load delta references **for every major between source and target inclusive**
— the upgrade is a chain, not a hop (see §3 Anti-Pattern A).

| Source → Target | Versions to load |
|---|---|
| 12 → 13 | v12→v13 delta |
| 12 → 17 | v12→v13, v13→v14, v14→v15, v15→v16, v16→v17 |
| 16 → 18 | v16→v17, v17→v18 |
| 18 → 19 | v18→v19 (BIG — mail framework v2) |
| 19 → 20 | v19→v20 (limited verified delta — apply stub-extends-v19) |

## 1. The three upgrade paths

| Path | Audience | What it gives | What you still own |
|---|---|---|---|
| **A. Custom code-only** | Any addon, any edition | Per-module `migrations/<new-version>/{pre,post}-migration.py` hooks Odoo's loader runs during `-u`. | All schema + data transformations for *your* addons. Standard Odoo addons NOT covered. |
| **B. OpenUpgrade (community)** | Community / OCA stack | OCA's `openupgrade_scripts` addon supplies migration scripts for **standard Odoo addons** version-by-version. | Your custom addons still need Path A; you can use `openupgrade.rename_models()` etc. |
| **C. upgrade.odoo.com (Enterprise)** | Enterprise contracts | Upload DB dump; Odoo S.A.'s proprietary pipeline returns a transformed dump. Covers standard + Enterprise addons. | Your custom addons still need Path A — Odoo's service does NOT migrate third-party modules. |

**Decision tree:**

```
Edition?
  ├── Enterprise → C (upgrade.odoo.com) for std + ent addons
  │                 + A (custom migrations) for your modules
  └── Community  → B (OpenUpgrade) for std addons
                   + A (custom migrations) for your modules
```

**Path A is non-negotiable for any consultancy delivery** — paths B and C
cover Odoo's own modules, never your project's.

## 2. Migration script anatomy (Path A)

```
my_module/
├── __manifest__.py                # version = "17.0.1.0.0"
└── migrations/
    └── 17.0.1.0.0/                # MUST match __manifest__.version exactly
        ├── pre-migration.py       # before models load
        ├── post-migration.py      # after models load + data update
        └── end-migration.py       # after ALL modules migrated (rare)
```

| Hook | Runs when | Use for |
|---|---|---|
| `pre-migration.py` | Before models load — new ORM schema not yet in PG | SQL `ALTER TABLE`, drop deprecated constraints, `openupgrade.rename_models()` |
| `post-migration.py` | After models load + data updated — full ORM access | Data backfill, recomputing stored compute fields, re-creating `ir.model.data` |
| `end-migration.py` | After ALL modules migrated | Cross-module consistency (rare) |

### Required signature

```python
# my_module/migrations/17.0.1.0.0/pre-migration.py
import logging
_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """cr = raw psycopg2 cursor (env NOT available pre-).
       version = previous ir.module.module.latest_version,
                 or None on a fresh install (NOT an upgrade)."""
    if not version:
        return  # fresh install — nothing to migrate
    _logger.info("my_module pre: from %s to 17.0.1.0.0", version)
    cr.execute("ALTER TABLE my_table RENAME COLUMN old_name TO new_name")
```

```python
# post-migration.py
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for rec in env['my.model'].search([('new_field', '=', False)]):
        rec.new_field = rec._compute_new_field_value()
```

### Idempotency (hard rule)

Migration scripts MUST be re-runnable safely — Odoo's `-u` may trigger
re-application during recovery.

```python
# BAD — double-applies on second run
cr.execute("ALTER TABLE my_table ADD COLUMN new_col INTEGER")
# GOOD
cr.execute("ALTER TABLE my_table ADD COLUMN IF NOT EXISTS new_col INTEGER")
```

`_logger.info()` lines in every migration script — Odoo's upgrade log is
the only forensic trail when an upgrade fails halfway.

---

## 3. Top 5 upgrade anti-patterns

### Anti-Pattern A — Skip-version upgrade (v14 → v17 directly)

**Confidence: H**

Odoo's standard module migrations (and OCA OpenUpgrade scripts) are
**version-keyed**: `migrations/15.0.x/` runs only when prior
`ir.module.module.latest_version` was 14.x. Jumping v14 → v17 in one
shot means the 15.0 and 16.0 migrations *never execute*.

```bash
# BAD — restore v14 dump on v17 server
pg_restore -d prod_v17 prod_v14.dump
odoo-bin -d prod_v17 -u all --stop-after-init
# Random tracebacks, half-applied schema, corrupted account.move.

# GOOD — one major at a time
for target in 15 16 17; do
    /opt/odoo${target}/odoo-bin -c odoo${target}.conf -d prod -u all --stop-after-init
    pg_dump prod > backup_after_v${target}.dump  # rollback point
done
```

**Falsification:**
```python
env['ir.module.module'].search([
    ('state', '=', 'installed'),
    ('latest_version', 'not like', '17.0%'),
])
# Expected: empty. Non-empty → those modules never ran their 15.0/16.0/17.0 migrations.
```

### Anti-Pattern B — Editing already-applied migration scripts

**Confidence: H**

Once a migration runs, Odoo records the new version in
`ir.module.module.latest_version`. Editing
`migrations/17.0.1.0.0/post-migration.py` after production already ran
it does **nothing** on the next `-u` (Odoo skips — version unchanged),
but the edited code WILL execute on environments that haven't upgraded
yet (staging, DR) — producing **divergent state**.

**Fix:** bump the addon version and add a *new* migration directory.

```python
# __manifest__.py
'version': '17.0.1.0.1',  # bumped

# migrations/17.0.1.0.1/post-migration.py
def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE my_table SET status='archived' WHERE status='done' AND ...")
```

**Falsification:** `git log` on `migrations/<version>/*.py` — any commit
*after* the first production deploy is the smoking gun.

### Anti-Pattern C — Not testing source + target parity on the same dataset

**Confidence: H**

DEV upgrades staging, clicks around, declares success. Production
upgrade goes live → `account.move` totals drift by 0.01 per invoice on
50% of records. Staging dataset lacks the edge-case distribution
(multi-currency, partially-paid, refunded) production has.

```sql
-- BEFORE upgrade snapshot
SELECT date_trunc('month', date), state, currency_id,
       COUNT(*), SUM(amount_total), SUM(amount_residual)
FROM account_move
WHERE date >= '2024-01-01'
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
-- AFTER upgrade: same probe, same dataset → must match (modulo
-- documented v15→v17 semantic shifts).
```

Apply same pattern to `sale.order`, `purchase.order`, `stock.move`,
`mrp.production`. **Aggregate parity is the only deterministic upgrade
gate**; functional clicking is not.

### Anti-Pattern D — Ignoring deprecation warnings during prior major's install

**Confidence: H**

Odoo prints `DeprecationWarning: <pattern> will be removed in <next major>`.
Most teams grep for `ERROR` and ignore `WARNING` — next major lands,
warning becomes hard `AttributeError`, upgrade hangs at module load.

| Source | Warning | Becomes error in |
|---|---|---|
| v12 | `@api.multi is deprecated` | v13 (removed) |
| v12 | `account.invoice is deprecated` | v13 (model removed) |
| v15 | `payment.acquirer is deprecated` | v16 (model renamed) |
| v16 | `name_get() override deprecated` | v17 (`_compute_display_name`) |
| v16 | `attrs="..." in views deprecated` | v17 (removed) |
| v18 | `mail.message legacy API` | v19 (mail v2 refactor) |

```bash
# CI gate — fail on any DeprecationWarning from your addon namespace
odoo-bin -d test_db -i my_module --stop-after-init 2>&1 \
  | grep -E "DeprecationWarning.*my_module" && exit 1 || exit 0
```

### Anti-Pattern E — Renaming fields / models via raw SQL

**Confidence: H**

`ALTER TABLE … RENAME COLUMN` renames the PG column but does NOT update
`ir.model.fields`, `ir.model.data`, view definitions (`ir.ui.view`),
translations (`ir.translation`), or stored compute deps. Server boots,
`read_group` crashes, ACLs lose grip, inherited views silently disappear.

```python
# BAD
cr.execute("ALTER TABLE my_table RENAME COLUMN old_field TO new_field")

# GOOD — OpenUpgrade helpers
from openupgradelib import openupgrade
def migrate(cr, version):
    if not version:
        return
    openupgrade.rename_fields(cr, [('my.model', 'my_table', 'old_field', 'new_field')])
```

`openupgrade.rename_fields()` updates PG column **and**
`ir.model.fields`, `ir.model.data`, view references, translations
atomically. Same for `rename_models()`, `rename_modules()`,
`rename_xmlids()`. If `openupgradelib` is unavailable, replicate the
helper's bookkeeping explicitly — never just `ALTER TABLE`. See
`references/odoo-openupgrade-helpers.md`.

---

## 4. Breaking-change inventory (v12 → v20)

Condensed; full details + code snippets in
`references/odoo-version-deltas-v12-to-v20.md`.

| Transition | Class | Breaking change | Migration action |
|---|---|---|---|
| v12 → v13 | ORM | `@api.one` / `@api.returns` removed | Replace `@api.one` with `for rec in self:` loop returning `self`. |
| v12 → v13 | ORM | New computed-field evaluator (lazy + cached differently) | Re-test all `@api.depends` for re-trigger semantics. |
| v12 → v13 | Accounting | `account.invoice` removed (deprecated in v12) | Complete migration to `account.move` — the model no longer exists in v13. |
| v12 → v13 | ORM | `@api.multi` removed (silent default) | Strip all `@api.multi` — methods default multi-record. |
| v12 → v13 | Accounting | `account.invoice` → `account.move` **REAL move** | Rewrite all invoice references: model name, field names, state machine. |
| v13 → v14 | ORM | `@api.model_create_multi` introduced | Override `create(self, vals_list)`. |
| v15 → v16 | Payment | `payment.acquirer` → `payment.provider` (rename landed in 16) | Rename all references; views, security, code. |
| v14 → v15 | JS | Legacy kanban JS dropped (pre-OWL) | Rewrite custom kanban widgets in OWL. |
| v15 → v16 | ORM | `_check_company_auto = True` mainstream | Audit multi-company models — see `odoo-multi-company`. |
| v15 → v16 | ORM | `flush()` formalized → `flush_recordset()` / `flush_model()` | Replace `flush(['fname'])` with `flush_model(['fname'])`. |
| v16 → v17 | ORM | `name_get()` removed → `_compute_display_name` | Convert every override to a `display_name` compute. |
| v16 → v17 | Views | `attrs="..."` removed | Replace with `invisible=`, `readonly=`, `required=` (Python expr directly). |
| v16 → v17 | Views | `states="..."` removed | Replace with `invisible="state not in ['draft','open']"`. |
| v16 → v17 | JS | OWL refactored (lifecycle, hooks) | Audit OWL components for `onMounted` / `onWillStart` migration. |
| v17 → v18 | ORM | Minor refinements (no big breaks) | Re-run deprecation gate (§3 Anti-Pattern D). |
| v17 → v18 | JS | OWL continued evolution | Patch custom OWL components. |
| v18 → v19 | **Mail** | **Mail framework v2 refactored (BIG)** | `mail.thread` internals rewritten; `message_post` signature stable but underlying engine changed. See `odoo-mail-v2-migration`. |
| v19 → v20 | All | Limited verified delta — **stub-extends-v19** | Treat as v19 + monitor release notes; do NOT assume new breakage absent verified notes. |

> **Authoritative source for each row:** Odoo official release notes +
> the corresponding OCA `openupgrade` branch's
> `openupgrade_scripts/scripts/base/<version>/`. When auditing a real
> upgrade, **cite the release-notes URL or OpenUpgrade commit hash** —
> never rely on this table alone for sign-off.

---

## 5. OpenUpgrade integration (Path B)

OpenUpgrade is OCA's community-driven upgrade pipeline. Install
`openupgrade_scripts` at the database level (server `--upgrade` flag +
OCA repo on the addons path); custom addons import `openupgradelib`
inside their `migrations/<version>/*.py`:

```python
# my_module/migrations/17.0.1.0.0/pre-migration.py
from openupgradelib import openupgrade

@openupgrade.migrate()  # OCA preferred form — env-based signature, auto-logs entry/exit
def migrate(env, version):
    openupgrade.logged_query(env.cr, """
        UPDATE my_table SET new_field = old_field WHERE new_field IS NULL
    """)
    openupgrade.load_data(env.cr, 'my_module', 'migrations/17.0.1.0.0/noupdate.xml')
```

The `@openupgrade.migrate()` decorator handles the version gate, sets up
`env`, and logs entry/exit — strictly preferred over hand-rolled
`api.Environment(cr, SUPERUSER_ID, {})`. Helper catalog:
`references/odoo-openupgrade-helpers.md`.

## 6. Path C — Odoo Official upgrade service (Enterprise)

Black-box service: POST a dump, GET back a transformed dump. **Custom
modules' migrations are NOT touched** — Path A still required.

```bash
pg_dump --no-owner --no-privileges prod > prod_v14.dump
python <(curl -s https://upgrade.odoo.com/upgrade) test \
    -d prod_v14.dump -t 17.0 --contract <enterprise-contract-code>
# Receive prod_v17_upgraded.dump
createdb prod_v17 && pg_restore -d prod_v17 prod_v17_upgraded.dump
odoo-bin -c odoo17.conf -d prod_v17 -u my_module --stop-after-init  # Path A
```

**Hard rule:** test on a "test" submission first (free + repeatable);
production submissions are billed per DB size.

---

## 7. Falsification recipes

```python
# Recipe 1 — Migrations actually ran
stale = env['ir.module.module'].search([
    ('state','=','installed'), ('latest_version','not like','17.0%'),
])
assert not stale, f"Stale latest_version: {stale.mapped('name')}"
```

```sql
-- Recipe 2 — Aggregate parity on accounting (run before AND after)
SELECT COUNT(*), SUM(amount_total), COUNT(*) FILTER (WHERE state='posted')
FROM account_move WHERE date BETWEEN '2024-01-01' AND '2024-12-31';

-- Recipe 3 — Aggregate parity on sales
SELECT COUNT(*), SUM(amount_total), SUM(amount_untaxed)
FROM sale_order
WHERE state IN ('sale','done') AND date_order BETWEEN '2024-01-01' AND '2024-12-31';
```

```python
# Recipe 4 — ir.model.data integrity
broken = env['ir.model.data'].search([]).filtered(
    lambda d: not env[d.model].browse(d.res_id).exists())
assert not broken, f"{len(broken)} orphans — likely SQL rename without ir.model.data update"

# Recipe 5 — View inheritance integrity
broken_views = env['ir.ui.view'].search([
    ('inherit_id','!=',False), ('mode','=','extension'),
]).filtered(lambda v: not v.inherit_id.exists())
assert not broken_views, "Extensions point to deleted parents — migration gap"
```

---

## 8. Code-review checklist for `migrations/**`

| Path / pattern | Severity | What to check |
|---|---|---|
| `pre-migration.py` raw `ALTER TABLE RENAME` | **H (blocker)** | Use `openupgrade.rename_fields/models/xmlids` or replicate bookkeeping. See §3 Pattern E. |
| `migrations/*.py` missing `if not version: return` guard | **H** | Fresh installs spuriously execute migration logic. |
| `migrations/*.py` non-idempotent ops (no `IF EXISTS` / dup check) | **H** | Re-run during recovery will corrupt. §2 Idempotency. |
| `migrations/*.py` silent (no `_logger.info`) | **M** | Loses forensic trail on failed upgrade. |
| `__manifest__.version` bump without matching `migrations/<new-version>/` dir | **M** | Either intentional (no data change) — confirm — or missed. |
| Migration directory name ≠ `__manifest__.version` exactly | **H** | Loader matches on string equality; `17.0.1.0` vs `17.0.1.0.0` silently skips. |
| `migrations/**` edited in commit AFTER first prod deploy of that version | **H** | §3 Pattern B (divergent environment state). |
| Cross-major-skip in CI matrix (no v15 / v16 in v14→v17 chain) | **H** | §3 Pattern A. |
| New addon with `_inherit = 'res.company'` without re-check of company-scoped migrations | **M** | Cross-link `odoo-multi-company` — verify `_check_company_auto` (mainstream v16+). |
| Deprecation warnings from your namespace in install log | **M→H** | §3 Pattern D — promote to H if API removed in next major. |

---

## 9. Cross-references

| Concern | Skill / file |
|---|---|
| Mail framework v2 (v18→v19) | `odoo-mail-v2-migration` |
| Module-level install/uninstall hooks (sibling) | `odoo-module-install-scripts` |
| Severity anchors for migration findings | `odoo-code-review` §D |
| Multi-company gotchas during upgrade (`_check_company_auto` flip v15→v16) | `odoo-multi-company` |
| Live ORM probes against upgraded DB | `odoo-data-verification` |
| TDD harness for migration scripts | `odoo-tdd` |
| Per-version delta details + snippets | `references/odoo-version-deltas-v12-to-v20.md` |
| OpenUpgrade helper catalog | `references/odoo-openupgrade-helpers.md` |
| Upgrade path decision tree + tooling | `references/odoo-upgrade-path.md` |

## 10. Sibling skills to call BEFORE this one

- `odoo-codebase-discovery` — enumerate the addon set + read every
  `__manifest__.py` `version`. Upgrade plan is N×M where N = custom
  addons, M = major hops; cannot plan without this enumeration.
- `odoo-deterministic-answers` — call `lookup_canonical_decision` for
  project upgrade rules (e.g. "client always Path B + A, never C";
  "always pin OCA 17.0 branch YYYY-MM-DD") before re-deriving.

## 11. Hard rules summary

- Never skip a major — one major hop per `-u` run, always.
- Never edit a migration script after first production deploy — bump
  addon `version` and create a *new* migration directory.
- Never `ALTER TABLE RENAME` without OpenUpgrade helpers (or equivalent
  bookkeeping for `ir.model.fields` / `ir.model.data` / views / translations).
- Never sign off without before/after aggregate parity on `account.move`,
  `sale.order`, and any project-critical model.
- Never ignore `DeprecationWarning` from your namespace — they are hard
  errors in the next major.
- Always `_logger.info()` every migration step.
- Always guard `if not version: return` in every `migrate()`.
- Always re-validate against Odoo's release notes + matching OCA
  `openupgrade_scripts` branch — §4 is a *map*, not the *territory*.
