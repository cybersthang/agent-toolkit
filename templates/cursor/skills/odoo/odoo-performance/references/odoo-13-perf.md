# Odoo 13 — performance deltas (standalone)

> odoo-13 reference (drafted v0.29). Deltas vs odoo-12-perf.md web-verified where cited; `<!-- VERIFY -->` items need DEV confirmation.

Standalone reference: 13 does NOT cascade from 17. Load when Step 0
detected major = **13**. Most v12 perf rules carry over verbatim; the
deltas are around the removed `@api.multi`, the multi-record `create()`,
and the company-dependent compute cache key.

## `browse()` vs ORM access — 13 specifics

Unchanged from v12 — see odoo-12-perf.md §"`browse()` vs ORM access".
Singleton `browse(<single_id>)` inside a loop still breaks the prefetch
group; browse the full ID list once and `mapped(...)`.

## Prefetch context — 13 API

Unchanged from v12 — see odoo-12-perf.md §"Prefetch context". `with_prefetch(...)`
is available; `recordset._prefetch` inspectable at runtime.

## Compute fields — NO `@api.multi`

```python
# Odoo 13 — recordset is default; NO @api.multi
@api.depends('line_ids.price_subtotal')
def _compute_total(self):
    for r in self:
        r.total = sum(r.line_ids.mapped('price_subtotal'))
```

DELTA vs v12: drop `@api.multi` (removed in 13). The compute still must
loop `for r in self:` — a compute that writes `r.<field>` outside a loop
is silently wrong (operates on the first record / raises on multi).

## Batch `create()` — use `model_create_multi`

```python
# v13 — one INSERT batch instead of N
records = self.env['my.model'].create([
    {'name': n} for n in names
])
```

DELTA vs v12: 13's `create()` is multi-record (`@api.model_create_multi`,
verified: 13.0 `odoo/models.py` ~line 3724). Passing a list of vals does
ONE batched insert path. A custom `create()` override declared
single-record (`@api.model create(vals)`) silently degrades batch
inserts to per-record overrides — a real N× regression on imports /
`(0,0,{})` command lists. Flag and re-declare as
`@api.model_create_multi`.

## Company-dependent compute cache key — `depends_context`

```python
# v13 — compute that varies by company MUST declare the context dep
@api.depends_context('force_company')
def _compute_price(self):
    ...
```

DELTA vs v12: `@api.depends_context(...)` exists in 13 (verified: 13.0
`odoo/api.py` ~line 209). Without it, a company-dependent compute is
cached across companies and returns stale values when the active company
/ `force_company` changes — a correctness bug that masquerades as a
caching win. (v12 had no `depends_context`; v12 code re-read fields
manually.)

## `@api.depends` with `store=True` — recompute fan-out

Unchanged from v12 — see odoo-12-perf.md §"`@api.depends` with
`store=True`". Long stored-compute chains cost real time on every write;
measure with `env.cr.sql_log = True`.

<!-- VERIFY(odoo-13): a community report (odoo/odoo#38178) claims `env.norecompute()` "has no effect in v13"; the context manager still exists in 13.0 models.py. If a perf finding hinges on manual recompute batching via `norecompute()`, DEV must confirm whether it actually defers recomputation in 13. -->

## `read_group(lazy=False)` behavior in 13

Unchanged from v12 — see odoo-12-perf.md §"`read_group(lazy=False)`".
Pass `lazy=False` for Python aggregators.

## Index API — `index=True` only

Unchanged from v12 — see odoo-12-perf.md §"Index API". Functional /
JSONB / expression indexes go in a migration script (under
`<module>/migrations/13.0.x.y/`), not the model declaration.

## QWeb `t-cache` — still present in 13

Unchanged from v12 — see odoo-12-perf.md §"QWeb `t-cache`". The
server-side QWeb render is still the default in 13 (no OWL backend), so
`t-cache="<stable-key>"` applies. Cache-key fragments must be stable
strings.

## Hard rules (Odoo 13 perf)

- NO `@api.multi` — removed; computes still loop `for r in self:`.
- Batch `create()` with `@api.model_create_multi` + a vals list — never
  a single-record override on a model hit by batch inserts.
- Company-dependent computes MUST use
  `@api.depends_context('force_company')` or they cache stale across
  companies.
- Never `browse(<single_id>)` inside a loop — pass the full ID list.
- `read_group(..., lazy=False)` for Python aggregators.
- Functional / JSONB indexes go in a migration script (`13.0.x.y/`).
- No OWL backend → frontend perf is jQuery + QWeb `t-cache`; read the
  exact jQuery version under `addons/web/static/lib/jquery/` on the 13.0
  branch if a finding hinges on it.
