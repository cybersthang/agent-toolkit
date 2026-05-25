# Odoo 18 — performance deltas (placeholder, cascade from 17)

Load **on top of** `odoo-17-perf.md`. Only override what differs in 18.
This file is a **placeholder** — the deltas below are the high-level
items confirmed against Odoo 18 release notes; deep numeric measurements
are <see Odoo 18 release notes> and DEV-verify before publishing.

## Confirmed 18 deltas (perf-relevant)

- ORM keyword: `search(args=...)` → `search(domain=...)`. Positional form
  still works; no perf change, only signature.
- Field-level: `group_operator='sum'` → `aggregator='sum'`. Behavior
  identical; no perf delta documented.
- Access checks: `check_access_rights()` + `check_access_rule()` →
  unified `check_access(operation)`. Minor reduction in call count per
  access path; quantify via measurement before claiming a win.
- `odoo.tools.SQL` parameterized-SQL wrapper — use in perf fix-sketches
  instead of raw `cr.execute` string concat.
- `<list>` is the preferred view tag over `<tree>` — purely syntactic,
  no render-perf delta.
- `_sequence` field attribute removed → model-level `_order` (often
  requires `index=True` on the order column for tables > 10k rows).

## Hard rules (Odoo 18 deltas)

- New code uses `search(domain=...)` + `aggregator='sum'`.
- Hand-tuned SQL goes through `odoo.tools.SQL`, not raw `cr.execute`.
- `_order = 'sequence, id'` on a large table → add `index=True` on `sequence`.

## Unconfirmed / DEV-verify before publish

- Quantitative perf claims about `check_access` collapse — <see Odoo 18
  release notes> for measured numbers.
- OWL renderer micro-perf changes between 17 and 18 — <see Odoo 18 web
  framework changelog>.
