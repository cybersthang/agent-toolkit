# Odoo 16 — TDD pitfalls (neighbour = v17)

> odoo-16 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load when Step 0 detected major = **16**. Structural model is
`odoo-17-tdd-pitfalls.md`; only divergences from v17 are recorded.

| Pitfall | Detection | Fix |
|---|---|---|
| Test of `create()` override only fires once for a batch | Override still uses `@api.model` (single-record) | Switch to `@api.model_create_multi(vals_list)`; assert on a list of ≥2 dicts (same as v17) |
| View fixture uses inline `invisible="<expr>"` and the condition never applies | Inline-expr is **17+**; on 16 it is silently ineffective | Use `attrs="{'invisible': [...]}"` in 16 fixtures (DELTA vs v17, which forbids `attrs`) |
| View fixture uses `<list>` → parse error on 16 | `<list>` is the v17 rename | Use `<tree>` in 16 fixtures |
| Display-name assertion fails | Test asserts `_compute_display_name` ran, but 16.0 model overrides `name_get` | On 16.0 assert on `record.name_get()` / `record.display_name`; override point is `name_get` (deprecated saas-16.4 → `_compute_display_name`, removed 17.0 — PR #122085) |
| Test calls `record.flush()` and gets a DeprecationWarning / future breakage | `flush()`/`recompute()` deprecated in 16 | Use `record.flush_recordset()` / `env['m'].flush_model()` / `self.env.flush_all()` in test setup before raw SQL assertions |
| Test calls `invalidate_cache()` to force re-read | Deprecated in 16 | Use `invalidate_recordset()` / `invalidate_model()` / `self.env.invalidate_all()` |
| Compute test reads stale value | Cache not flushed before raw read | `record.flush_recordset(fnames=[...])` then re-read (replaces blanket `flush()`) |
| OWL component test missing assets | JS in `static/src/` not referenced in `'assets'` dict | Add path to `'assets': {'web.assets_backend': [...]}` (same as v17) |

## Test framework classes (Odoo 16)

- `TransactionCase` — sub-transaction per test (same as v17).
- `SavepointCase` — **still present in 16** as a distinct class; the full
  merge of savepoint behaviour into `TransactionCase` is a later-version
  cleanup. (Verified-tentative — see flag below.) For new 16 tests,
  `TransactionCase` is the safe default; if a 16 codebase uses
  `SavepointCase`, do not flag it as removed.
  <!-- VERIFY(odoo-16): exact status of SavepointCase in 16.0 — distinct class vs alias of TransactionCase. Confirm against odoo/odoo 16.0 odoo/tests/common.py before asserting either in a customer-facing report. -->
- `HttpCase` — controller/browser tests; `self.url_open` works (same as v17).
- `tagged()` decorator for filtering test runs (same as v17).

## Hard rules (Odoo 16 TDD)

- `create()` override MUST be `@api.model_create_multi(vals_list)`; test
  with ≥2 vals (same as v17).
- View fixtures use `attrs="{...}"` and `<tree>` in 16 — NOT inline
  `invisible="<expr>"` / `<list>` (those are v17+ and break or no-op on 16).
- For display-label tests, assert via `name_get()` / `display_name`; the
  override target is `name_get` on 16.0 (deprecated saas-16.4 →
  `_compute_display_name`, removed 17.0).
- In setup/teardown use the granular `flush_recordset` /
  `invalidate_recordset` family; the old `flush()` / `invalidate_cache()`
  are deprecated in 16.
