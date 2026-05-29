# Odoo 20 — performance deltas (PRE-GA stub; neighbour = v19 → v18 → v17)

> odoo-20 reference (drafted v0.29). **Odoo 20 is PRE-GA at drafting
> time.** Planned GA Sept 2026 (Odoo Experience 2026, Brussels, 24–26
> Sept 2026); until then 20 lives on the non-frozen `master` branch and
> NOTHING below is a stable perf delta. Cascade from v19/v18/v17; every
> 20-specific claim is <!-- VERIFY(odoo-20) --> until the branch is cut.

Load **on top of** `odoo-19-perf.md` (which cascades from `odoo-18-perf.md`
→ `odoo-17-perf.md`). Because 20 has not reached GA, this file is a
**cascade stub**: assume the perf model is unchanged from v19, and flag
any 20-specific finding version-tentative, re-checked against the live
`master` / 20.0 branch of `odoo/odoo` and the master ORM changelog
(/documentation/master/developer/reference/backend/orm/changelog.html).

## What is assumed UNCHANGED from v19 (→ v18 → v17)

Read `odoo-19-perf.md` as the base. The perf model is assumed to carry
forward:

- **`@api.multi` gone; `@api.model_create_multi` for batch `create`.**
- **`_read_group()` / `formatted_read_group()`** over the deprecated
  `read_group()` (assumed to hold / harden in 20 — re-check whether
  `read_group()` is fully REMOVED in 20.0 vs still deprecated).
- **`search_fetch()` / `fetch()`** combined search+read.
- **OWL component perf** (`useState`, `onWillStart`, `<t t-foreach>`,
  service reuse).
- **ORM prefetch hints** (`with_prefetch`, `_prefetch_fields=False`).
- **`odoo.tools.SQL`** parameterized wrapper.
- **`search(domain=...)` keyword + `aggregator='sum'`.**
- **Index API** (`index=True`/`'btree'`/`'btree_not_null'`/`'trigram'`
  in the field declaration).
- **`compute_sudo` semantics.**

## 20-specific deltas

<!-- VERIFY(odoo-20): No Odoo 20 perf deltas can be confirmed pre-GA. The headline reported theme is deep/"agentic" AI embedding across apps — not an ORM/query-engine perf change. Before relying on this file for a 20 perf audit: (1) read the master ORM changelog for read_group removal vs deprecation, any new index types on odoo.fields.Field, search/fetch/_read_group signature drift; (2) read models.py / fields.py on the 20.0 branch; (3) re-derive ALL numeric claims from realdata_test / postgres MCP probes on the actual 20 deployment. Treat every 20 perf finding as version-tentative until GA. -->

## Hard rules (Odoo 20 deltas)

- This file is a **pre-GA cascade stub**. Apply `odoo-19-perf.md` deltas;
  flag any 20-specific finding LOW / version-tentative.
- No quantitative 20 perf claim may be cited without project-measured
  `realdata_test` / `postgres` MCP numbers AND a read of the matching
  20.0 source — the `master` branch is not frozen.
- Re-check `read_group` removal status and any new `index=` types against
  the master ORM changelog before asserting either in a finding.
