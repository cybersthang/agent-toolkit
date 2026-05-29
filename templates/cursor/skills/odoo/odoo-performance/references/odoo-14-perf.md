> odoo-14 reference (drafted v0.29). Deltas vs odoo-12-perf.md web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

# Odoo 14 — performance deltas (standalone)

Standalone reference: 14 does NOT cascade from 17. Load when Step 0
detected major = **14**.

**Orientation**: On ORM internals 14 is between 12 and 17. `@api.multi` is
gone (recordset default, like 17), `@api.model_create_multi` exists (batch
create like 17), but the index API and frontend are still 12-like
(`index=True` only; legacy widgets default).

## `browse()` vs ORM access — prefetch

Unchanged from v12 — see odoo-12-perf.md "browse() vs ORM access" and
"Prefetch context". Singleton `browse(<single_id>)` inside a loop still
defeats the prefetch group; browse the full ID list once.

```python
# GOOD — browse the full list once
lines = self.env['sale.order.line'].browse(line_ids)
total = sum(lines.mapped('price_subtotal'))
```

## Compute fields — NO `@api.multi` (delta vs v12)

```python
# Odoo 14 — no @api.multi, recordset is default
@api.depends('line_ids.price_subtotal')
def _compute_total(self):
    for r in self:
        r.total = sum(r.line_ids.mapped('price_subtotal'))
```

Verified `odoo/api.py` 14.0 has no `multi`. The v12 rule "missing
`@api.multi` raises" does NOT apply — methods iterate `self` by default.
Adding `@api.multi` in 14 is an import-time error, not a perf concern.

## `create()` — `@api.model_create_multi` for batch (delta vs v12)

```python
@api.model_create_multi
def create(self, vals_list):
    records = super().create(vals_list)
    records._post_create_hook()   # runs once on the whole batch
    return records
```

Verified `@api.model_create_multi` present in 14. A single-record
`@api.model create(vals)` override processes per-record and loses batch
amortization — perf-claim category for any bulk import.

**Measurement**: time `env['<model>'].create([{...}] * 100)` with the
multi override vs a single-record override patched in.

## `@api.depends` with `store=True` — recompute fan-out

Unchanged from v12 — see odoo-12-perf.md "@api.depends with store=True".
Dependency graph regenerated at module load; long relational chains cost
real time per write. Measure via `env.cr.sql_log = True` around a write.

## `read_group(lazy=False)` behavior in 14

Unchanged from v12 — see odoo-12-perf.md "read_group(lazy=False)". Pass
`lazy=False` for Python aggregators that read all grouping levels.

## Index API — `index=True` only (same as 12, NOT 17)

Verified `odoo/fields.py` 14.0: `index = False` is a plain boolean. The
string index types (`index='trigram'`, `index='btree_not_null'`) are **15.2+**
and do NOT exist in 14. So, like v12:

- `index=True` is the only declarative option.
- Functional / JSONB / expression indexes go in a migration script:

```sql
-- in <module>/migrations/14.0.1.x.y/post-create-index.py via env.cr.execute
CREATE INDEX IF NOT EXISTS <table>_<col>_idx ON <table> ((data->>'key'));
```

## `prefetch` / `compute_sudo` field attributes

- `prefetch=False` on a heavy field (e.g. large `Binary`) disables
  automatic prefetch inclusion — verified `odoo/fields.py` 14.0
  (`prefetch = True` default). Useful so a wide `read()` doesn't drag MB of
  unused payload. (17 colloquially calls this `_prefetch_fields=False`; the
  field attribute name is `prefetch` in 14.)
- `compute_sudo=True` runs a compute as superuser — present in 14
  (verified fields.py 14.0). Audit-trail concern, not a perf win on its own.
- No native `Json` field type in 14 (that is 16+) — JSON lives in
  `Text`/`Char` with manual `json.loads`/`dumps`; large JSON columns are a
  read-amplification surface, mitigate with `prefetch=False`.

## QWeb `t-cache` — NOT honored in 14 (do not rely on it)

`t-cache` is **not a directive in the Odoo 14 server-side QWeb engine**
(verified `odoo/addons/base/models/qweb.py` 14.0: `_directives_eval_order()`
is `debug, groups, foreach, if, elif, else, field, esc, raw, tag, call, set`
— there is no `cache` entry and no `_compile_directive_cache` method; a grep
for `cache` in 14.0 `qweb.py` returns nothing). It is also absent from 12.0
`qweb.py`, so the old "same as 12" claim was wrong on both ends. A
`t-cache="..."` attribute in a 14 template is silently treated as an unknown
attribute (no caching, no error) — **do NOT base a 14 perf finding on it.**
For server-side render caching in 14, rely on the ORM/record caches and
`ir.qweb` compiled-template caching rather than a `t-cache` directive.

## Frontend perf — legacy widgets default; OWL is new

OWL exists in 14 but the backend client is mostly the legacy
`web.Widget`/jQuery framework. For a 14 frontend perf claim hinging on
bundle size or a specific jQuery API, read the exact jQuery version under
`addons/web/static/lib/jquery/` on the 14.0 branch. OWL-specific perf rules
(`useState` re-render, `onWillStart`) apply only to actual OWL components.

## Hard rules (Odoo 14 perf)

- No `@api.multi` (removed in 13). Adding it is an import error, not a perf bug.
- `@api.model_create_multi(vals_list)` is the batch-safe `create` override.
- Never `browse(<single_id>)` inside a loop — pass the full ID list.
- `read_group(..., lazy=False)` for Python aggregators.
- `index=True` only; functional/JSONB indexes go in a migration script
  (string index types are 15.2+).
- `prefetch=False` on heavy Binary/JSON-in-Text fields when read paths don't
  need them — verify via query log first.
