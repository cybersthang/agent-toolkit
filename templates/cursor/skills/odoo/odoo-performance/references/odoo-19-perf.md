# Odoo 19 — performance deltas (neighbour = v18 → v17)

> odoo-19 reference (drafted v0.29). Deltas vs v18/v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load **on top of** `odoo-18-perf.md` (which itself cascades from
`odoo-17-perf.md`). Only the items below override v18. Odoo 19 was
released Sept 2025 (Odoo Experience 2025) and is stable through the 19.x
patch line. As always: every numeric perf claim must be re-derived from
the project's own benchmarks against a real Odoo 19 instance via
`realdata_test` / `postgres` MCP before being cited.

## What is UNCHANGED from v18 (→ v17)

See `odoo-18-perf.md` and `odoo-17-perf.md`:

- **`@api.multi` gone; `@api.model_create_multi` for batch `create`** —
  unchanged. Single-record `@api.model create` override still serialises
  batch inserts (perf claim category for bulk import).
- **OWL component perf** (`useState` re-render, `onWillStart` for async,
  `<t t-foreach>` cost, service reuse) — base model unchanged; see the
  OWL micro-perf VERIFY note below for 19-specific renderer churn.
- **ORM prefetch hints** (`with_prefetch`, `_prefetch_fields=False` on
  heavy Binary fields) — unchanged.
- **`compute_sudo` semantics** — unchanged.
- **`search(domain=...)` keyword + `aggregator='sum'`** — these landed in
  18 (17.2 for the rename); unchanged in 19. See `odoo-18-perf.md`.
- **`odoo.tools.SQL` parameterized wrapper** — introduced 17.0
  (#134677); use it in fix-sketches instead of raw `cr.execute`.
- **Index API** (`index=True` / `'btree'` / `'btree_not_null'` /
  `'trigram'` in the field declaration) — unchanged.

## Confirmed 19 deltas (perf-relevant)

Verified against the Odoo 19.0 ORM changelog
(/documentation/19.0/developer/reference/backend/orm/changelog.html) and
PR #110737.

### `read_group()` deprecated → `_read_group()` / `formatted_read_group()`

The biggest 19 aggregation-perf change. `read_group()` is deprecated in
favour of `_read_group()` (backend) and `formatted_read_group()` (the
formatted public API). `_read_group()` gained a new signature in #110737
and returns value-tuples rather than the legacy list-of-dicts
(`__domain`/`__count` keys). The old `read_group()` is documented as
"inefficient and mostly overkill" for in-Python use.

```python
# v19 — backend aggregation, fewer round-trips than legacy read_group
groups = self.env['sale.order.line']._read_group(
    domain=[('order_id', 'in', self.ids)],
    groupby=['order_id'],
    aggregates=['price_subtotal:sum'],
)
totals = {order.id: subtotal for order, subtotal in groups}
```

**Perf relevance**: a hot dashboard / report that calls `read_group()`
per group, or post-processes the legacy dict result in Python, can drop
round-trips and Python overhead by moving to `_read_group()`. **Measure**
query count + wall time before/after via the query log — do NOT cite a
fixed % without project numbers.

**Detect**: `grep -nE "\.read_group\(" <model>.py` — flag for migration
to `_read_group` / `formatted_read_group`.

### `search_fetch()` / `fetch()` — combined search+read

Introduced in 17.4 and the recommended form in 19: `search_fetch()` runs
the search and prefetches the listed fields in the SAME SQL query (the
17.4 refactor lets `search()` / `search_read()` fetch fields in one
round-trip). For an explicit "search then read these columns" path,
`search_fetch(domain, field_names)` saves the separate prefetch query.

```python
# v19 — one query: search + fetch the columns you need
recs = self.env['my.model'].search_fetch(
    [('state', '=', 'open')], ['name', 'amount', 'partner_id'],
)
```

**Perf relevance**: replaces the `search()` + first-field-touch
prefetch-trigger pattern with a single query. **Measure** with the query
log; claim the saved query only with numbers.

### Per-field PostgreSQL index type — same selector, restated in 19

The `index=` property selects the PG index type (`True`/`'btree'`,
`'btree_not_null'`, `'trigram'`). This existed from 16/17; the 19
changelog restates that developers define the index type via the
`index` property of `odoo.fields.Field`. No new index type confirmed in
19 over the v16/v17 set — treat any "new 19 index type" claim as
unverified until read off the 19.0 `fields.py`.

## Version-specific notes (re-verify per audit)

Signal-level only — hypotheses until measured on the project's own Odoo
19 instance.

- **ORM "query planner / batch prefetch" performance claims.** Secondary
  sources describe a 19 ORM with reduced round-trips and tiered compute
  caching, but no specific magnitude is in the official changelog. Do NOT
  cite a "% fewer queries" number without `realdata_test` / `postgres`
  MCP probes on the actual deployment. The verifiable mechanisms are the
  `_read_group` / `search_fetch` / `fetch` round-trip reductions above.
- **OWL renderer micro-perf between 18 and 19** — check the OWL changelog
  (`addons/web/static/src/core/`) on the matching branch when frontend
  render time is the load-bearing claim.

## Hard rules (Odoo 19 deltas)

- Aggregation/reports: `_read_group()` (backend) / `formatted_read_group()`
  (public) over the deprecated `read_group()`; expect the new
  tuple-based return shape (#110737).
- Explicit search+read paths: prefer `search_fetch(domain, fields)` /
  `fetch(fields)` to collapse the read into the search query.
- Everything else (batch `create`, OWL, prefetch, `index=` types,
  `odoo.tools.SQL`, `search(domain=...)`, `aggregator=`) is unchanged
  from v18 — see `odoo-18-perf.md`.
- No quantitative "19 ORM is X% faster" claim without project-measured
  numbers.
