# Odoo breaking-change map — v12 → v20

Headline cross-version map. Load the rows for **every major between
source and target inclusive** (SKILL.md §0) — the upgrade is a chain.
Each anchor is verified against odoo/odoo + odoo.com/documentation +
OCA/OpenUpgrade; sources at the bottom.

> Version-number discipline: a fact's version is the major where the
> change LANDS. Odoo's online (SaaS) interim majors (e.g. 16.4) are noted
> where the ORM changelog records them, but for an on-premise upgrade the
> change ships in the next stable major.

## Quick map (one line per major)

| → | Headline breaking change |
|---|---|
| **v13** | `account.invoice`→`account.move` merge · `@api.one`/`@api.multi`/`@api.returns` **removed** |
| **v14** | **OWL framework introduced** · TransientModels need explicit ACLs · `<act_window>`/`<report>` shortcuts deprecated |
| **v15** | New flush / cache-invalidation API · email templates Jinja→QWeb · search `args`→`domain` |
| **v16** | `payment.acquirer`→`payment.provider` · **OWL 2 web-client rewrite** · field translations → JSONB |
| **v17** | `name_get()`→`_compute_display_name` / `display_name` · view `attrs=`/`states=` **removed** |
| **v18** | `<tree>`→`<list>` view tag · Field `column_format`/`deprecated` & Model `_sequence` removed |
| **v19** | Controller `type='json'`→`'jsonrpc'` · XML-RPC/JSON-RPC deprecated (JSON-2) · `group_operator`→`aggregator` |
| **v20** | NOT YET RELEASED (≈ Sept/Oct 2026) — only confirmed delta: legacy RPC endpoints removed on-prem |

---

## v12 → v13

```python
# REMOVED: @api.one, @api.multi, @api.returns, @api.cr, @api.model_cr.
# Methods are multi-record by DEFAULT. Using @api.multi now raises:
#   AttributeError: module 'odoo.api' has no attribute 'multi'
# BEFORE (v12)                          # AFTER (v13+)
@api.multi                              def _compute_total(self):
def _compute_total(self):                   for rec in self:
    for rec in self: ...                        ...
```

- **`account.invoice` merged into `account.move`** (PR #33797, landed on
  the saas-12.4 branch that became 13.0). `account.invoice.line`→
  `account.move.line`; `account.invoice.refund` wizard → `account.move.reversal`;
  `account.voucher` folded in. This is THE big v13 data migration.
- `@api.model_create_multi` is the preferred `create()` override — but it
  already existed in v12; v13 just removes the legacy decorators around it.

## v13 → v14

```xml
<!-- DEPRECATED in 14: <act_window>/<report> shortcut tags. Use <record>. -->
<record id="my_action" model="ir.actions.act_window">
  <field name="name">My Action</field>
  <field name="res_model">my.model</field>
</record>
```

- **OWL framework introduced** — "Our new OWL framework is available"
  (official v14 release notes). Component-based JS + QWeb templates; legacy
  `web.Widget`/jQuery still present. First step of the multi-version OWL
  migration (NOT complete here).
- **TransientModels (wizards) now require explicit `ir.model.access.csv`**
  (PR #43306). Previously `_transient` models were skipped in access
  checks. Missing ACL → access errors on the wizard.

## v14 → v15

- **New flushing / cache-invalidation API** (ORM changelog 15.4):
  `flush()` → `flush_recordset()` / `flush_model()`; `invalidate_cache()`
  → `invalidate_recordset()` / `invalidate_model()`.
- Search method `args` parameter **renamed to `domain`** (changelog 15.3);
  `filtered_domain()` now preserves recordset order.
- Email/mail templates ported from **Jinja to QWeb** (v15 release notes) —
  custom `${...}` template expressions must become QWeb.

## v15 → v16

```python
# RENAMED model — update code, views, security, data.
# payment.acquirer  →  payment.provider   (PR #90899, lands in 16.0)
self.env['payment.provider'].search([])      # was payment.acquirer
```

- **`payment.acquirer` → `payment.provider`** (PR #90899; merged on master
  labeled 16.0). Rename every reference: model, fields
  (`acquirer_id`→`provider_id`), views, security, XML data.
- **OWL 2 web-client rewrite** — "almost all JS components now use OWL 2,
  backend views load up to 20× faster" (v16 release notes). The bulk of
  the legacy-widget → OWL migration completes here.
- Translations for translatable fields stored as **JSONB** in-column
  (changelog 16.0), not separate `ir.translation` rows.

## v16 → v17

```python
# REMOVED: name_get() override. Compute display_name instead.
# (Method name_get() deprecated #122085 — recorded at 16.4 in the ORM
#  changelog; on-prem this lands in the 17.0 stable major.)
# BEFORE                                  # AFTER (17+)
def name_get(self):                       @api.depends('code', 'name')
    return [(r.id, f"[{r.code}] {r.name}")  def _compute_display_name(self):
            for r in self]                     for r in self:
                                                   r.display_name = f"[{r.code}] {r.name}"
```

```xml
<!-- REMOVED in 17: attrs="..." and states="...". Use Python expressions. -->
<!-- BEFORE -->  <field name="x" attrs="{'invisible': [('state','=','done')]}"/>
<!-- AFTER  -->  <field name="x" invisible="state == 'done'"/>
<!-- states="draft,open" → invisible="state not in ('draft','open')" -->
```

## v17 → v18

```xml
<!-- RENAMED view tag: <tree> → <list>. Update views AND xpath targets. -->
<!-- BEFORE -->  <tree editable="bottom"> ... </tree>
<!-- AFTER  -->  <list editable="bottom"> ... </list>
```

- ORM (changelog 18.0): `Model._sequence` removed (PG default sequence
  used); Field `column_format` and `deprecated` attributes removed;
  `_search_display_name` (#174967); combined access methods
  `check_access` / `has_access` / `_filtered_access` (#179148).
- `name_get()` is now effectively dead — read/compute `display_name`.

## v18 → v19

```python
# RENAMED controller type: type='json' → type='jsonrpc' (same behavior).
@http.route('/my/endpoint', type='jsonrpc', auth='user')   # was type='json'
def my_endpoint(self, **kw): ...
```

- **Legacy RPC deprecated**: `/xmlrpc`, `/xmlrpc/2`, `/jsonrpc` endpoints
  deprecated in 19, replaced by the new **JSON-2** API. Removal on Odoo
  Online in 19.1, on Odoo.sh / on-prem in **v20**.
- ORM (changelog 19.0): Field `group_operator` **renamed to `aggregator`**
  (#127353); `_flush_search()` deprecated (#144747); `_name` optional /
  `_inherit` as a list for cleaner multi-inheritance.
- **Mail framework**: substantial mail/`mail.thread` evolution in this
  cycle — `message_post` API stable, internals changed. Validate custom
  chatter/mail code against `odoo-mail-v2-migration`.

## v19 → v20

**Odoo 20 is NOT yet released** (expected ≈ Sept/Oct 2026; unveiled at
Odoo Experience Brussels, Sep 24–26 2026). Only a roadmap exists ("a list
of things we will maybe do"). Treat as **stub-extends-v19** (SKILL.md §0).

- **Only confirmed delta** (from the v19 deprecation timeline): the
  deprecated `/xmlrpc`, `/xmlrpc/2`, `/jsonrpc` endpoints are **removed**
  on Odoo.sh / on-prem in v20. Use the JSON-2 API. (XML-RPC kept in legacy
  mode; full removal targeted for a later major.)
- Do NOT assume any other v20 breakage until the official release notes
  ship — roadmap items (AI agents, Field Service → Planning) are
  unconfirmed and may change. OMIT rather than guess.

---

## Notes on accuracy

- `account.invoice`→`account.move` and `@api.multi` removal are **v13**
  (not v14). The merge PR targeted saas-12.4 → 13.0; `@api.multi` raises
  `AttributeError` from 13. SKILL.md §0 fallback signals agree.
- `payment.acquirer`→`payment.provider` is **v16** (PR #90899).
- `name_get`→`display_name` deprecation is recorded at **16.4** in the ORM
  changelog; for an on-prem upgrade it surfaces in the **17.0** stable
  major. Both numbers are correct for their context.
- For sign-off, cite the release-notes URL or OpenUpgrade commit per row
  (SKILL.md §4) — this map is a map, not the territory.

> Sources — odoo/odoo:
> [PR #33797 (account.move merge → saas-12.4/13.0)](https://github.com/odoo/odoo/pull/33797),
> [PR #43306 (TransientModel ACLs, 14.0)](https://github.com/odoo/odoo/pull/43306),
> [PR #90899 (payment.provider, 16.0)](https://github.com/odoo/odoo/pull/90899),
> [issue #192829 (tree→list, 18.0)](https://github.com/odoo/odoo/issues/192829).
> Release notes:
> [v13](https://www.odoo.com/odoo-13-release-notes),
> [v14](https://www.odoo.com/odoo-14-release-notes),
> [v15](https://www.odoo.com/odoo-15-release-notes),
> [v16](https://www.odoo.com/odoo-16-release-notes),
> [v17](https://www.odoo.com/odoo-17-release-notes),
> [v18](https://www.odoo.com/odoo-18-release-notes),
> [v19](https://www.odoo.com/odoo-19-release-notes).
> ORM changelogs:
> [17.0](https://www.odoo.com/documentation/17.0/developer/reference/backend/orm/changelog.html),
> [18.0](https://www.odoo.com/documentation/18.0/developer/reference/backend/orm/changelog.html),
> [19.0](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm/changelog.html).
