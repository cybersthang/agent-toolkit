---
name: odoo-performance
description: Detect + falsify the five canonical Odoo performance anti-patterns (N+1 queries, missing prefetch, slow computed fields, missing indexes, sudo() in loops). Version-aware: Step 0 detects the addon's Odoo version from `__manifest__.py`, then loads `references/odoo-<N>-perf.md` (12 standalone; 17→18→19→20 cascade). Every finding MUST carry a real-data timing / EXPLAIN measurement — no "looks slow" without numbers. Open whenever the user says "tối ưu", "slow", "performance", "chậm", "N+1", "thêm index", "query plan", or when `odoo-code-review` Dimension 2/3/13 surfaced a perf concern.
---

# Odoo — Performance anti-patterns (version-aware, falsification-first)

> "Measure before optimizing." Every finding from this skill MUST cite a
> measured wall time / query count / EXPLAIN row via `realdata_test` or
> `postgres` MCP. A PERF claim without numbers is rejected by
> `evidence_audit`.

Pair with `odoo-code-review` (finding gate), `odoo-data-verification`
(live ORM probes), `odoo-codebase-discovery` (locate target module), and
`_common/code-review/references/performance-checklist.md` (broad
9-dimension list — this skill is the **depth pass** on the 5 anti-patterns
that produce >80% of real Odoo slowdowns).

## 0. Version detection (MANDATORY)

Same protocol as `odoo-code-review`:

1. `__manifest__.py` `version` via `codebase.read_manifest({module_path})`.
2. Fallback signals: `@api.multi` → 12; OWL `/** @odoo-module **/` → 15+; `search(domain=...)` → 18+.
3. Ask the user only if inconclusive.

| Detected major | Reference |
|---|---|
| 12 | `references/odoo-12-perf.md` (standalone) |
| 13 | load `references/odoo-13-perf.md` |
| 14 | load `references/odoo-14-perf.md` |
| 15 | load `references/odoo-15-perf.md` |
| 16 | load `references/odoo-16-perf.md` (+ note: backports some v17 conventions) |
| 17 | `references/odoo-17-perf.md` |
| 18 | `references/odoo-18-perf.md` ← 17 |
| 19/20 | `references/odoo-18-perf.md` ← 17 + flag MEDIUM (placeholder cascade — re-check the target major's release notes; this reference may need overrides) |

Skip Step 0 → wrong prefetch API / wrong cache helper. Restart.

## 1. The five anti-patterns

### 1.1 N+1 queries (loop-bound `search` / `browse`)

Iterating a recordset and re-querying inside the loop → one round-trip
per iteration. 1k records → 1000 extra queries; latency O(1) → O(N).

```python
# BAD
for order in self:
    lines = self.env['sale.order.line'].search([('order_id','=',order.id)])
    order.total = sum(lines.mapped('price_subtotal'))

# GOOD — single search + grouping
all_lines = self.env['sale.order.line'].search([('order_id','in',self.ids)])
by_order = {}
for line in all_lines:
    by_order.setdefault(line.order_id.id, []).append(line.price_subtotal)
for order in self:
    order.total = sum(by_order.get(order.id, []))
```

**Detect**: `grep -nE "for .+ in self" -A 5 <model>.py | grep -E "self\.env\[.+\]\.(search|browse)\("`

**Falsify** (linearity test):

```python
import time
recs = env['<model>'].search([<domain>], limit=200)
t0 = time.time(); _ = recs.mapped('<suspect_field>'); dt_200 = time.time()-t0
recs2 = env['<model>'].search([<domain>], limit=400)
t0 = time.time(); _ = recs2.mapped('<suspect_field>'); dt_400 = time.time()-t0
# Claim: N+1 iff dt_400/dt_200 ≈ 2.0 (±20%)
```

Severity: BLOCKER if linear AND prod batch ≥ 500.

### 1.2 Missing prefetch on chained relational reads

Auto-prefetch warms on a `mapped()` or batched read; Python `if`
branches on a relational field do NOT warm prefetch — every `.partner_id`
fires a SELECT.

```python
# BAD — branching defeats prefetch
for o in orders:
    if o.partner_id.country_id:
        o.country_name = o.partner_id.country_id.name

# GOOD — warm prefetch first
orders.mapped('partner_id.country_id.name')
for o in orders:
    if o.partner_id.country_id:
        o.country_name = o.partner_id.country_id.name
```

**Detect**: `grep -nE "for .+ in" -A 10 <model>.py | grep -E "\.[a-z_]+_id\.[a-z_]+(_id)?"`

**Falsify**: enable `env.cr.sql_log = True` (Odoo 12) or `pg_stat_statements`
snapshot via `postgres` MCP, run the loop, count queries. Claim: missing
prefetch iff queries > `len(orders) + 2`.

Severity: MEDIUM default; BLOCKER if queries > 100 on typical page load.

### 1.3 Slow computed fields (`store=True` + heavy compute)

Stored compute recomputes on every write of any `@api.depends` field —
across the dependent recordset. Storing a non-trivial compute amplifies
write cost; storing a compute only used for display wastes throughput.

```python
# BAD — stored + inner search + hot dependency
total = fields.Monetary(compute='_compute_total', store=True)

@api.depends('line_ids', 'line_ids.price', 'partner_id.is_company')
def _compute_total(self):
    for r in self:
        partners = self.env['res.partner'].search([('parent_id','=',r.partner_id.id)])
        r.total = sum(r.line_ids.mapped('price_subtotal')) * (2 if partners else 1)

# GOOD — narrow depends, no inner search, computed-on-read
total = fields.Monetary(compute='_compute_total')

@api.depends('line_ids.price_subtotal')
def _compute_total(self):
    for r in self:
        r.total = sum(r.line_ids.mapped('price_subtotal'))
```

**Detect**: `grep -nE "compute=.+store=True" <model>.py`; then read each
`_compute_*` body and flag inner `search`/`browse`.

**Falsify**:

```python
import time
r = env['<model>'].browse(<id>)
t0 = time.time(); r.write({'<hot_field>': r.<hot_field>}); dt = time.time()-t0
# Claim: slow compute iff dt > 200ms AND > 5x no-op write baseline
```

Severity: MEDIUM if > 200ms on hot path; BLOCKER if > 1s on user button click.

### 1.4 Missing indexes on hot WHERE / ORDER BY

Postgres seq-scans without an index. Odoo auto-indexes `_rec_name` + FK
columns + `index=True` fields. Custom domains on free `Char`/`Date`/`Bool`
fields, or `read_group` groupby on un-indexed columns, scale linearly
with table size.

```python
# BAD — used in every list view domain, no index
state = fields.Selection([...])

# GOOD
state = fields.Selection([...], index=True)
```

JSONB / functional indexes differ by version — see reference.

**Detect**: grep models for `search([('<field>'...`; cross-check
`pg_indexes` via `postgres` MCP.

**Falsify** (SQL via `postgres` MCP):

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM <table> WHERE <suspect_col> = '<value>' ORDER BY <order_col>;
-- Claim: missing index iff Seq Scan AND rows > 10k AND total > 50ms
```

Severity: MEDIUM if seq-scan > 10k rows AND > 50ms; BLOCKER if hot
endpoint AND > 500ms.

### 1.5 `sudo()` in loops / compute methods

`record.sudo()` allocates a SUPERUSER-env recordset per call AND bypasses
record rules. In a loop the cost stacks; in a compute every recompute
pays it — and `sudo()` inside a compute often hides a record-rule bug
(restricted data leaks into the displayed total).

```python
# BAD — sudo in loop + compute
@api.depends('line_ids')
def _compute_visible_total(self):
    for r in self:
        r.visible_total = sum(r.sudo().line_ids.mapped('amount'))

# GOOD — sudo once outside (or not at all if record rules should apply)
@api.depends('line_ids.amount')
def _compute_visible_total(self):
    for r in self:
        r.visible_total = sum(r.line_ids.mapped('amount'))
```

**Detect**: `grep -nE "\.sudo\(\)" <model>.py` then narrow to lines
inside a `for` or a `@api.depends` block.

**Falsify**:

```python
import time
r = env['<model>'].browse(<id>)
t0 = time.time(); _ = r._compute_visible_total(); dt_sudo = time.time()-t0
# 1. Patch removes sudo; rerun: dt_no_sudo
# Claim: sudo-in-loop iff dt_sudo > 2x dt_no_sudo on N >= 100
# 2. Run compute as user U vs SUPERUSER; values differ → record-rule leak
```

Severity: LOW for perf only; MEDIUM-BLOCKER if record-rule bypass leaks data.

## 2. Output contract (per finding) — ADR-003

```
FINDING <ID> — <one-line claim>
  pattern:    <1.1 | 1.2 | 1.3 | 1.4 | 1.5>
  file:       <abs/path/to/file.py>:<line>
  evidence:   <grep hit / AST excerpt>
  Proof:      <ORM expression or SQL via realdata_test/postgres MCP — INCLUDE measured value, e.g. dt_400/dt_200 = 2.1>
  Doubt-pass: <one rationalization considered + why it doesn't dismiss>
  severity:   <BLOCKER | MEDIUM | LOW>
  fix-sketch: <2–3 line outline; do NOT write the full patch>
```

A finding without **measured numbers** in `Proof:` is rejected.

## 3. Stop checkpoints

Stop and escalate to DEV when:

- The measurement requires DML (UPDATE/INSERT) — never run destructive
  SQL through `postgres` MCP; ask DEV to run on staging.
- `realdata_test` says target table has < threshold rows for the claim
  (e.g. wanted ≥500, table has 12) — flag `[insufficient-data]`,
  downgrade to LOW.
- Adding an index on a write-heavy table — verify with
  `pg_stat_user_indexes` + `pg_stat_user_tables` that the index won't
  tank writes before proposing.
- Flipping `store=True` on an existing field — that's a migration, not
  a patch. Punt to migration playbook.

## 4. Anti-rationalizations (short)

- "Fast on dev DB" → re-run on prod-shaped data via `realdata_test`.
- "`store=True` will fix it" → storing AMPLIFIES write cost; measure read hotness first.
- "Caching solves N+1" → fix query first, cache second (stale-data risk).
- "Index everything" → each index costs ~1ms write + memory; require EXPLAIN.
- "`sudo()` is just a perf hint" → it BYPASSES record rules; audit data leak too.

## 5. Red flags

- PR adds `@api.depends` on a chained relational path without verifying batch-safe compute.
- Bugfix flips `store=True` "to make it persist" — misread of the flag.
- `search()` appears inside a `_compute_*` body — almost always wrong.
- `index=True` added with no prior `EXPLAIN` showing Seq Scan.
- `sudo()` added "to make the compute work" with no ADR for the rule bypass.

## 6. Sibling skills

- `odoo-code-review` — finding gate; Dimension 2/3/13 = perf surfaces.
- `odoo-data-verification` — runs the `Proof:` ORM probes.
- `odoo-codebase-discovery` — locate module + read manifest first.
- `_common/code-review/references/performance-checklist.md` — broader 9-dim list (caching, workers, pagination, memory, concurrency, frontend) — open AFTER the five core anti-patterns are walked.
