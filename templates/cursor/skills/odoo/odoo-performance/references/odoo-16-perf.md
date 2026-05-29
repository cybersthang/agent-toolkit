# Odoo 16 — performance deltas (neighbour = v17)

> odoo-16 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load when Step 0 detected major = **16**. Structural model is
`odoo-17-perf.md`. Only divergences from v17 are recorded here.

## `@api.multi` is GONE; `@api.model_create_multi` for batch

Unchanged from v17 — see `odoo-17-perf.md` §`@api.multi` and
§`create()`. Recordset is default; single-record `@api.model create`
override silently serialises batch inserts (perf claim category for any
bulk import).

## OWL component perf (frontend, OWL 2.x in 16)

Unchanged from v17 — see `odoo-17-perf.md` §OWL component perf. The OWL
2.x reactivity model (`useState` re-render, `onWillStart` for async,
`<t t-foreach>` cost, service reuse) is identical because 16 already
ships OWL 2.x (verified: OWL 2.0 ~Oct 2022 with Odoo 16; odoo/odoo
#106898 bumps the 2.0.x line on saas-16.1).

Caveat: the 16 *webclient* is only partially OWL (full view/field OWL
rewrite is v17). Some hot backend surfaces in 16 still run legacy
`web.Widget`/jQuery — profile the actual render path before attributing
a 16 frontend slowdown to OWL.

## New flush / invalidate API — granular cache control (DELTA vs how 17 code reads)

16 introduces the explicit-granularity flush/invalidate methods
(verified: ORM API + OCA v16 migration):

```python
# 16+ — granular flush
self.flush_recordset(fnames=['amount'])   # this recordset, named fields
self.env['my.model'].flush_model(['state'])  # whole model
self.env.flush_all()                         # everything pending

# 16+ — granular invalidate
self.invalidate_recordset(fnames=['amount'])
self.env['my.model'].invalidate_model(['state'])
self.env.invalidate_all()
```

- `flush()` / `recompute()` are **deprecated** → use
  `flush_model` / `flush_recordset` / `env.flush_all`.
- `invalidate_cache()` / `refresh()` are **deprecated** → use
  `invalidate_model` / `invalidate_recordset` / `env.invalidate_all`.
- **Perf relevance**: in tight write loops a blanket old-style `flush()`
  forced ALL pending writes + recomputes; targeting `flush_recordset(
  fnames=[...])` flushes only what a subsequent raw-SQL read needs,
  cutting redundant recompute churn. Measure with the query log before
  and after narrowing the flush scope.

## `search_count()` honours `limit` (DELTA vs 15; same as 17)

`search_count(domain, limit=N)` stops counting at N (verified: odoo/odoo
#95589, 16.0). Replace `len(records.search(domain, limit=N))` /
unbounded `search_count` where an "at least N?" answer suffices.

## ORM hints — prefetch

Unchanged from v17 — see `odoo-17-perf.md` §ORM hints
(`with_prefetch`, `_prefetch_fields=False` on heavy Binary fields).

## Index API — `index=` types

Same set as v17 (verified: Odoo 16 ORM fields reference): `index=True`
or `index='btree'` (default btree), `index='btree_not_null'` (mostly-NULL
columns), `index='trigram'` (GIN trigram, good for ILIKE / full-text).

```python
name = fields.Char(index='trigram')          # speeds ILIKE
state = fields.Selection([...], index='btree_not_null')
```

These go in the field declaration (no migration script needed) — same
as v17. The PG-index-type selector landed in the saas line consolidated
into 16.0 (verified: ORM changelog #83274/#83015), so it is a 16 delta
**vs Odoo 15.0** but identical to v17.

## `unaccent=False` field option (DELTA vs 15)

16 adds `unaccent=False` on a field to skip accent-insensitive
normalisation where accent distinctions don't matter — avoids the
`unaccent()` wrapper cost on indexed text searches (verified: OCA v16
migration). Not present pre-16.

## Translated fields → JSONB (DELTA vs 15)

Field translations are stored as JSONB columns in 16 instead of
`ir.translation` rows (verified: odoo/odoo #97692/#101115). Perf note:
reading a translated field no longer joins/looks up `ir.translation`;
flag legacy code that still queries `ir.translation` for field values as
both a correctness AND a perf issue.

## `compute_sudo` — unchanged from v17

See `odoo-17-perf.md`.

## Removed / not-applicable in 16 (don't measure against)

- `@api.one` — gone (same as v17).
- `@api.multi` — gone (same as v17).
- Note: `attrs="{...}"` IS valid in 16 (removed only in 17), so unlike
  v17 a view-render perf claim on `attrs` IS in scope for 16. Heavy
  `attrs` domains across many interdependent fields were a known 16
  view-eval cost (one stated reason for the 17 removal) — flag deeply
  nested `attrs` on large forms as a 16 view-eval perf surface.

## Hard rules (Odoo 16 perf)

- No `@api.multi` (gone). `@api.model_create_multi(vals_list)` for batch.
- Prefer granular `flush_recordset(fnames=[...])` /
  `invalidate_recordset(...)` over blanket `flush()`/`invalidate_cache()`
  (deprecated) in hot paths.
- `search_count(domain, limit=N)` over `len(search(..., limit=N))`.
- Trigram / btree_not_null indexes in the field declaration.
- `unaccent=False` on text fields where accent-folding is wasted.
- Watch heavy nested `attrs` on large 16 forms — a view-eval cost that
  does NOT exist in 17 (where attrs is gone).
