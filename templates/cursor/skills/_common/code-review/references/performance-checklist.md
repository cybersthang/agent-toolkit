# Performance Checklist — Code Review Reference

Open this file when walking Dimension 2 (SQL touchpoints), Dimension 3
(Cron / workers), Dimension 13 (Double-counting), Dimension 15
(Concurrency / leaks), or whenever a finding involves loops, queries,
caching, or memory. Use as a *checklist*, not a tutorial. Every unchecked
item is either a finding (with PROOF + a `realdata_test` / `postgres`
expression you would run to live-verify) or an explicit
"none — verified by …".

The list mixes stack-agnostic items with Odoo-specific items. Mark N/A
when the surface doesn't apply (e.g. "Dimension 7 N/A — no controller in
scope").

---

## Core principle

> "Measure before optimizing. Performance work without measurement is
> guessing."

Every PERF finding worth filing has a measurable expression:

- Counts: `env['model'].search_count(domain)`
- Aggregates: `env['model'].read_group(domain, fields, groupby, lazy=False)`
- Wall time: `EXPLAIN ANALYZE` via `postgres.run_select`
- Determinism: `consistency_check_eval` with `runs=3`

Live-verify the suspect path before promoting a LOW perf concern to MEDIUM.

## N+1 / loop-bound queries (Dimension 3 + 13)

- [ ] No `self.env['model'].search(...)` inside `for record in self:` — push into a domain or `read_group`.
- [ ] No `self.env['model'].browse(record.field_id.id)` inside a loop — use `.field_id` directly.
- [ ] No `record.related_id.related_field` chain inside a loop without prefetch — verify `_inherits` / prefetch covers it.
- [ ] `search_count(domain)` instead of `len(search(domain))` (the latter materializes the recordset).
- [ ] Cross-model joins via `mapped('related_id.field')` or a single `search([('related_id.field', '=', ...)])` — never a Python `for` loop that re-queries per record.
- [ ] Aggregations via `read_group(..., lazy=False)`, not Python `sum(records.mapped(...))` on a large recordset.

## Indexes + SQL hot paths (Dimension 2)

- [ ] Hot WHERE / ORDER BY columns have an index (verify with `\d <table>` or `pg_indexes`).
- [ ] No `ILIKE '%pattern%'` on a column that may be gzip-encoded — first decompress / project into a SQL view.
- [ ] No `JOIN` on un-indexed text columns; use `id` joins where possible.
- [ ] `read_group` `groupby` columns are indexed (else the dashboard query scales linearly).
- [ ] JSON-path access (`additional_info::json -> 'key'`) is **functional-indexed** if it's a hot WHERE — otherwise it falls back to seq-scan.

## Compute fields + storage

- [ ] Every `@api.depends(...)` lists ALL inputs the compute reads — missing field → stale values.
- [ ] `store=True` only when the field is **searched, grouped, sorted, or repeatedly displayed at scale**. Otherwise `store=False` (computed on read).
- [ ] `compute_sudo=True` only when the compute needs to bypass record rules — document why.
- [ ] Compute methods batch-friendly: iterate `self` once, no inner search.

## Batching writes / unlinks

- [ ] `records.write({...})` once on the recordset, not `for r in records: r.write({...})`.
- [ ] `records.unlink()` in one call where possible (else cascading triggers re-fire per record).
- [ ] `create()` overrides use `@api.model_create_multi(vals_list)` in Odoo 17 — single-record override silently breaks batch creates.
- [ ] `with_context(...)` to suppress mail / tracking on bulk write, when appropriate (e.g. data migration).

## Caching

- [ ] Frequently-read, rarely-changed lookup data has a tools.ormcache or `_cache_` decorator.
- [ ] Cache invalidation paths verified: `clear_caches()` called when the underlying data mutates.
- [ ] HTTP responses for static-ish endpoints set cache headers (`Cache-Control`, `ETag`).
- [ ] No cache stampede risk on hot endpoints (consider request coalescing if relevant).

## Background workers / cron (Dimension 3)

- [ ] Daemon thread's `while True:` body has an outer try/except so a transient raise doesn't kill the thread.
- [ ] Queue (`Queue` / `deque`) has a max size — unbounded queues are a memory bomb.
- [ ] Cron `nextcall` realistic vs the job's actual runtime (don't schedule a 10-min job every 5 min).
- [ ] `max_cron_threads` configured for the deployment — defaults often too low for parallel jobs.
- [ ] Graceful shutdown: long-running jobs check `request.env.cr.commit()` periodically + `time.sleep(0)` to yield.

## Pagination + unbounded fetches (Dimension 4)

- [ ] List endpoints (`api_*_dashboard`, `api_logs`, etc.) have `limit` / `offset`.
- [ ] `mapped('many2many_field')` on a large recordset doesn't fan out (use `search` with domain).
- [ ] No `search([], limit=None)` on tables that grow without bound.
- [ ] CSV / Excel exports: stream chunks or cap rows + show `truncated=True` to the consumer.

## Memory leaks (Dimension 15)

- [ ] Module-level dicts / lists that grow on register WITHOUT a prune path — flag MEDIUM.
- [ ] Thread-local state always cleaned in a `finally` block; verify the exception path too.
- [ ] Cached results bounded (LRU cache with `maxsize=...`, not unbounded `functools.cache`).
- [ ] File / socket handles closed via context manager (`with open(...) as f:`) — never raw `open()` without `try/finally`.

## Concurrency

- [ ] Shared mutable state (`_entries` dict, registry patches) protected appropriately — Python GIL makes dict/deque ops atomic but compound ops (`if key in d: d[key].append(...)`) are not.
- [ ] No double-lock on the same path (deadlock).
- [ ] DB transactions narrow: no long-running cursor held while waiting on external HTTP.
- [ ] `request.env.cr.savepoint()` used when a sub-step may fail without aborting the whole request.

## QWeb / OWL render perf (frontend)

- [ ] No `t-foreach` over a 1000+ recordset in a synchronous render — paginate or use OWL `Lazy*` components.
- [ ] OWL components: `useState` only for state that triggers re-render; static data goes to `this.data`.
- [ ] OWL: `onWillStart` for async data load; never `await` inside `setup()` directly.
- [ ] QWeb (Odoo 12): `t-cache` keys correct — wrong key fragments cause stale renders.

## Asset bundles (frontend)

- [ ] New JS / SCSS registered in the correct asset bundle (`assets_backend` / `assets_frontend` / `assets_qweb`).
- [ ] No duplicate jQuery loads (Odoo 12) / no jQuery in Odoo 17 (use OWL).
- [ ] Asset bundles split where reasonable — don't ship a 5MB monolith if 2MB of it is admin-only.

## Verification expressions (per finding, plug into `realdata_test`)

```python
# N+1 suspicion: count queries via _logger SQL profiling first, then run
# Aggregate verification:
sum(env['<model>'].search([<domain>]).mapped('<field>'))

# Determinism on an aggregate:
# Run via consistency_check_eval(runs=3); fingerprints must match.

# Read-group baseline:
env['<model>'].read_group([<domain>], ['<measure>', '<groupby>'], ['<groupby>'], lazy=False)

# Index check (raw SQL via postgres MCP):
# EXPLAIN ANALYZE SELECT ... FROM <table> WHERE <col> = ...;

# Memory growth check (in a short loop, via realdata_test):
len(<module>.<dict_or_deque>)
```

## When to escalate severity

- **BLOCKER**: any of {N+1 that's verified to cause >10× slowdown on real data, daemon thread that dies on first failure with no recovery, unbounded fetch that returns >100MB per call, memory leak verified to grow without bound, deadlock that hangs the worker}.
- **MEDIUM**: any of {missing index on a hot path verified by EXPLAIN, unstored compute called in a list view, cache without invalidation hook, pagination missing on a dashboard endpoint, queue without max size}.
- **LOW**: any of {compute that could be stored but isn't hot enough to matter, jQuery loaded twice with no observable effect, asset bundle slightly over budget, missing `truncated` flag on a capped list}.

## Common rationalizations (counter them)

| Rationalization | Counter |
|------|----|
| "It's fast on my dev DB with 100 rows" | Production has 50k rows / 5M records. Run the expression against `realdata_test` before declaring fine. |
| "Adding an index slows down writes" | Verify with EXPLAIN. Most read-heavy tables can absorb one extra index. The write penalty is usually <1ms. |
| "Caching will fix it" | Caching without invalidation creates stale data bugs. Fix the underlying query first; cache after. |
| "The cron only runs once a day" | If the user clicks "Run now", or you upgrade the module, it runs ad-hoc. Plan for that. |
| "store=True for safety" | `store=True` adds a column + invalidation triggers. Verify the field is actually searched/grouped before storing. |
