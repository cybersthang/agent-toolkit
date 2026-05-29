# Odoo 15 — performance deltas (standalone, transitional)

> odoo-15 reference (drafted v0.29). Deltas vs odoo-12 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Standalone reference: load when Step 0 detected major = **15**. Most ORM
perf mechanics are unchanged from v12; the deltas are the removed
`@api.multi`, the new asset bundling, and the OWL/jQuery frontend split.

## `browse()` vs ORM access — Unchanged from v12

Singleton `browse(<single_id>)` in a loop breaks the prefetch group;
batch via `browse(<id_list>)` + `mapped(...)`. Prefetch internals and
`with_prefetch(...)` usage are unchanged from v12 — see odoo-12-perf.md
"browse() vs ORM access" and "Prefetch context".

## Compute fields — NO `@api.multi` (DELTA from v12)

```python
# Odoo 15 — recordset is default, NO @api.multi
@api.depends('line_ids.price_subtotal')
def _compute_total(self):
    for r in self:
        r.total = sum(r.line_ids.mapped('price_subtotal'))
```

DELTA vs v12: `@api.multi` is removed (v13). The v12 perf note "missing
`@api.multi` operates on first record only" does NOT apply — every method
is recordset-bound by default. Still iterate `for r in self` to be
batch-safe. Web-verified.

## `@api.depends` + `store=True` recompute fan-out — Unchanged from v12

Dependency graph regenerated at load; long stored-compute chains cost on
every write. Measure via `env.cr.sql_log`. Unchanged from v12 — see
odoo-12-perf.md "@api.depends with store=True".

## `flush()` / recompute timing

In v15 the recompute/flush machinery is the modern (v13+) form: pending
computes/writes flush before SQL reads. When a perf claim hinges on flush
timing, call `self.env.flush_all()` / `record.flush_recordset()` shapes
rather than assuming the v12 `record.flush()` signature.
<!-- VERIFY(odoo-15): exact flush method names available in 15.0 (flush() vs flush_all/flush_recordset which were renamed across 13–16) — confirm against 15.0 models.py before relying on a specific name -->

## `read_group(lazy=False)` — Unchanged from v12

`lazy=True` (default) returns only the outermost grouping level; pass
`lazy=False` for Python aggregators reading all levels. Unchanged from
v12 — see odoo-12-perf.md "read_group".

## Index API — `index=True` only — Unchanged from v12

No functional-index DSL on field declarations; create JSONB/expression
indexes in a migration script. Unchanged from v12 — see odoo-12-perf.md
"Index API". (Migration dir is `<module>/migrations/15.0.x.y/`.)

## Frontend perf — DELTA: assets dict + OWL/jQuery split

- Asset bundles are declared in the manifest `assets` dict (NEW in v15),
  not via XML records. Bundle composition affects load — e.g. shipping
  OWL XML in `web.assets_qweb` (the v15-only bundle) vs leaking JS into
  `web.assets_common` (loaded everywhere). If a finding hinges on bundle
  size, read the module's manifest `assets` key, not an `assets.xml`.
- OWL renders client-side; the v12 server-side QWeb `t-cache` still
  applies to **server-rendered** QWeb (reports, website templates) in v15
  but NOT to OWL client templates. Unchanged-where-server-rendered — see
  odoo-12-perf.md "QWeb t-cache".

## Hard rules (Odoo 15 perf)

- No `@api.multi` (removed v13); still iterate `for r in self` in computes.
- Never `browse(<single_id>)` in a loop — pass the full ID list
  (unchanged from v12).
- `read_group(..., lazy=False)` for Python aggregators (unchanged).
- Functional/JSONB indexes go in a `migrations/15.0.x.y/` script
  (unchanged).
- Frontend bundle perf is governed by the manifest `assets` dict; OWL is
  client-rendered (no server `t-cache`), server QWeb still caches.
- Verify exact flush/prefetch method names against the 15.0 source when a
  claim hinges on them (renames happened across 13–16).
