# Odoo 17 — performance deltas (head of 17→18→19→20 cascade)

Load when Step 0 detected major = **17** (or 16 transitional with LOW
flag). Cascading references (18/19/20) override only the deltas below.

## `@api.multi` is GONE — recordset is default

```python
# 17+ — no @api.multi, recordset is the default
@api.depends('line_ids.price_subtotal')
def _compute_total(self):
    for r in self:
        r.total = sum(r.line_ids.mapped('price_subtotal'))
```

A method without `@api.multi` in 17 still iterates `self` correctly —
the decorator no longer exists. If you see `@api.multi` in 17 code,
that's a migration bug, not a perf bug, but flag it.

## `create()` — `@api.model_create_multi` is required for batch

```python
@api.model_create_multi
def create(self, vals_list):
    records = super().create(vals_list)
    records._post_create_hook()  # runs once on the WHOLE batch
    return records
```

A 17 module with the old `@api.model` `create(vals)` form silently
inserts records ONE-AT-A-TIME under the hood — perf claim category for
any bulk import.

**Measurement**: time `env['<model>'].create([{...}] * 100)` vs the same
with the `@api.model_create_multi` form patched in. Single-record
override → linear with N; multi → ~constant overhead.

## OWL component perf (frontend, 17+)

OWL replaces `web.Widget`/jQuery. Hot perf surfaces:

- **`useState`** triggers a re-render on every assignment. Static data
  belongs on `this.data` (plain prop), not `useState`.
- **`onWillStart`** is the right place for async data fetch — never
  `await` directly in `setup()` (blocks render).
- **`<t t-foreach>`** over 1000+ rows in a synchronous render freezes
  the browser. Paginate or use a lazy/virtual list pattern.
- **OWL services** (`useService('orm')`) are reused per component
  lifetime — instantiate once in `setup()`, not per render.

```javascript
// BAD — await in setup blocks render until data arrives
setup() {
    this.records = await this.orm.searchRead("my.model", [], ["id"]);
}

// GOOD — onWillStart awaits BEFORE first render
setup() {
    this.state = useState({ records: [] });
    onWillStart(async () => {
        this.state.records = await this.orm.searchRead("my.model", [], ["id"]);
    });
}
```

## ORM hints — `prefetch_fields` + `with_prefetch`

- `recordset.with_prefetch(prefetch_ids)` works the same as 12 but the
  prefetch dict is now keyed differently (model + field cache merged).
  Inspect via `recordset.env.cache` if a perf claim hinges on it.
- `_prefetch_fields` field-level attribute can be set to `False` on
  heavy fields (e.g., a large `Binary`) — disables automatic prefetch
  inclusion so a wide `read()` doesn't drag MB of unused payload.

## `compute_sudo` — 17 semantic

`compute_sudo=True` on a `fields.X(compute=...)` runs the compute as
SUPERUSER but stores the result visible to the regular user. Useful
when the compute needs to see records the user can't, but be explicit:
adds an audit-trail concern, not a perf win on its own.

## Index API — `index=True` + `_sql_constraints`

`index=True` still works; in addition 17 supports
`fields.X(index='btree_not_null')` and `index='trigram'` (PG ≥ 11) as
alternate index types. Default `index=True` maps to `btree`.

```python
name = fields.Char(index='trigram')  # speeds up ILIKE searches
state = fields.Selection([...], index='btree_not_null')
```

**Measurement**: same `EXPLAIN ANALYZE` recipe as the SKILL.md core; the
plan node will say `Index Scan using <name>_<col>_idx` when hit.

## Removed in 17 (don't measure against, flag if present)

- `attrs="{...}"` on views — view-render perf claim on `attrs` is moot
  because the view won't load.
- `@api.one` — never existed in 17.

## Hard rules (Odoo 17 perf)

- No `@api.multi` (gone). If you see it → migration bug, not perf bug.
- `@api.model_create_multi(vals_list)` is the only batch-safe `create`
  override.
- OWL `setup()` MUST NOT `await` directly — use `onWillStart`.
- Trigram / btree_not_null indexes go in the field declaration, not a
  migration script (12-style migration is no longer needed for these).
- `_prefetch_fields=False` on heavy Binary fields when read paths
  routinely don't need them — verify via query log first.
