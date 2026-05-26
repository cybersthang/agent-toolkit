# Odoo 12 — performance deltas (standalone)

Standalone reference: 12 does NOT cascade from 17. Load when Step 0
detected major = **12**.

## `browse()` vs ORM access — 12 specifics

- `record.browse(id)` returns a recordset whose fields are NOT yet
  fetched. Reading any field triggers a SELECT for the whole prefetch
  group. The prefetch group is built from the recordset's `_prefetch`
  dict, which Odoo populates when records are obtained via `search()` /
  `browse(ids_list)` (multi).
- `record.browse(<single_id>)` inside a loop **breaks the prefetch
  group** — each `browse` returns a singleton with its own prefetch
  hint, defeating batched SELECTs.

```python
# BAD — singleton browse defeats prefetch
for line_id in self.env.context.get('line_ids', []):
    line = self.env['sale.order.line'].browse(line_id)
    total += line.price_subtotal

# GOOD — browse the full list once
lines = self.env['sale.order.line'].browse(self.env.context.get('line_ids', []))
total = sum(lines.mapped('price_subtotal'))
```

## Prefetch context — 12 API

- `with_prefetch(prefetch_ids)` is available in 12 but rarely needed —
  the default prefetch built into the recordset usually suffices. Use
  ONLY when you have a list of IDs to prime that wasn't obtained via
  `search()`.
- `recordset._prefetch` is a `defaultdict(set)` keyed by model name —
  inspect at runtime if a perf claim hinges on prefetch shape.

## Compute fields — `@api.multi` matters

```python
# Odoo 12 requires @api.multi on the compute
@api.depends('line_ids.price_subtotal')
@api.multi
def _compute_total(self):
    for r in self:
        r.total = sum(r.line_ids.mapped('price_subtotal'))
```

Missing `@api.multi` on a compute that iterates `self` raises in 12;
missing it on a method that only writes `record.<field> = ...` outside
a for-loop is silently wrong (operates on first record only).

## `@api.depends` with `store=True` — recompute fan-out

In 12, the dependency graph computed from `@api.depends` is REGENERATED
at module load. If two stored computes depend on each other via
relational paths, the recompute order is fixed-point — long chains cost
real time on every write.

**Measurement**: write to a single hot field and count recomputes via
`env.cr.sql_log` (set `env.cr.sql_log = True` then issue the write, read
back the log).

## `read_group(lazy=False)` behavior in 12

- `lazy=True` (default) returns only the **outermost** grouping level
  + a `__domain` you must drill down on — fine for UI, terrible for a
  Python aggregator that reads all levels at once. Always pass
  `lazy=False` when aggregating in Python.

## Index API — `index=True` only

Odoo 12 supports `index=True` on field declarations only — no functional
index DSL. For JSONB / expression indexes you must create the index
manually in a migration script:

```sql
-- in <module>/migrations/12.0.1.x.y/post-create-index.py via env.cr.execute
CREATE INDEX IF NOT EXISTS <table>_<col>_idx ON <table> ((data->>'key'));
```

## QWeb `t-cache` — 12-only

- `t-cache="<key-expression>"` caches a sub-template render. Cache key
  fragments must be **stable strings** — including a list-of-records in
  the key fragments bypasses the cache silently.
- 17+ does NOT carry `t-cache` forward (OWL renders client-side, no
  server cache layer).

## Hard rules (Odoo 12 perf)

- `@api.multi` on every method iterating `self`, including computes.
- Never `browse(<single_id>)` inside a loop — pass the full ID list.
- `read_group(..., lazy=False)` for Python aggregators.
- Functional / JSONB indexes go in a migration script, not the model.
- `t-cache` keys must be stable strings — verify per-render.
- No OWL → frontend perf is jQuery + QWeb t-cache. If a finding hinges
  on the frontend bundle size or a specific jQuery API, read the exact
  jQuery version shipped under `addons/web/static/lib/jquery/` on the
  matching `odoo/odoo` 12.0 branch rather than assuming the major.
