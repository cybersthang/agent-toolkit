---
name: odoo-17-code-review
description: Exhaustive code review for Odoo 17 modules — applies the shared `code-review` workflow plus Odoo-17-specific checklist (recordset-default ORM, `@api.model_create_multi`, removed `attrs/states`, OWL frontend, monkey-patches). Open whenever the user asks "review", "audit", "phân tích sâu", "tìm bug" against Odoo 17 code. Module-agnostic.
---

# Odoo 17 — Code Review Overlay

Read `_common/code-review` first — it owns the workflow, severity rubric,
PROOF contract, and reporting format. This file only adds the Odoo-17-specific
checklist and tool routing.

## 0. Tool routing (Odoo 17 stack)

| Need                              | MCP             | Tool                                                            |
|-----------------------------------|-----------------|-----------------------------------------------------------------|
| Confirm addon roots in scope      | `codebase`      | `workspace_status`, `discover_modules({root_hint})`             |
| Identify the model + extensions   | `codebase`      | `find_inheritance_chain({model})`                               |
| List tests + check coverage gaps  | `codebase`      | `list_test_targets`                                             |
| Cross-check XML IDs               | `codebase`      | `search_xml_ids`                                                |
| Static text search (cite path:line) | `codebase`    | `search_text({pattern, root_hint})`                             |
| Live-verify a Medium against DB   | `realdata_test` | `eval_orm_expression`, `consistency_check_eval`                 |
| Inspect raw SQL state             | `postgres`      | `run_select`                                                    |
| Recurring project answer          | `codebase`      | `lookup_canonical_decision({topic})`                            |

## 1. Severity examples grounded in Odoo 17

| Severity | Concrete Odoo-17 example |
|----------|--------------------------|
| BLOCKER | Override `create()` declared with `@api.model` instead of `@api.model_create_multi(vals_list)` → batch creates silently apply only to the first record |
| BLOCKER | Compute method calls `search()` inside the `for record in self` loop → N+1 that explodes on a large recordset |
| BLOCKER | OWL component reads a payload key the backend stopped writing — UI silently shows blanks |
| MEDIUM  | View ships `attrs="{...}"` or `states="…"` (removed in 17) — install will raise on upgrade, blocks deploy |
| MEDIUM  | Controller missing `csrf=True` (or the explicit JSON-RPC convention) on a state-changing endpoint |
| MEDIUM  | `json.dumps(payload)` without `ensure_ascii=False` — non-ASCII identifiers mangled in stored data |
| MEDIUM  | Default value drift: Python field default ≠ XML data record default |
| MEDIUM  | Memory dict that only grows (no prune in a cron / on `_unregister_hook`) |
| LOW     | Hard-coded `base.user_admin` in `security.xml` — fragile across DBs |
| LOW     | Missing multi-company `ir.rule` on a shared model |
| LOW     | OWL component uses `useService("rpc")` instead of the modern `useService("orm")` helper |
| LOW     | Capped list `[:1000]` with no `truncated` flag downstream |

## 2. Odoo-17-specific dimensions (additions to the shared matrix)

### A. ORM / API decorators (17 differs from 12/13/14)
- `@api.multi` is **removed**. If you see it: BLOCKER on import-time error, MEDIUM if the import is dead but still loaded.
- Methods are **recordset by default** — `for record in self:` is the canonical loop, no decorator needed.
- `@api.model_create_multi` is required to override `create()`. Single-record `@api.model` `create()` will silently break batch creates.
- `@api.depends`, `@api.constrains`, `@api.onchange`, `@api.depends_context` as before.
- `ensure_one()` whenever the method assumes a single record.

### B. Loops + N+1 (same as 12)
- No `search()` / `browse(id)` inside Python loops.
- `search_count()` over `len(search())`.
- Computed fields with `store=False` referenced repeatedly in a loop — flag as Medium perf.

### C. Views (17 syntax)
- `attrs="{...}"` and `states="..."` are **removed**. Any new file shipping them: MEDIUM (install raises) or BLOCKER (install blocks deploy of unrelated changes).
- Use `invisible="<expr>"`, `readonly="<expr>"`, `required="<expr>"` directly with Python expressions on the field.
- Inheritance: `<xpath expr position="after|before|inside|replace|attributes">`.
- XML IDs stable across releases — rename without migration = LOW.

### D. Frontend (OWL, no jQuery)
- New jQuery selectors → MEDIUM (legacy debt) or BLOCKER if they target a node the OWL render no longer produces.
- OWL components: `static template = "<module>.<Name>"`, `setup()` calls `useService("orm" | "notification" | "action")`.
- Templates are OWL XML with `t-*` directives — legacy 12.x widget classes are gone.
- `static/src/` registers components into `registry.category(...)`.

### E. Security / multi-company
- Every new model has a row in `ir.model.access.csv`.
- Multi-company models inherit `mail.thread` only when chatter is needed — otherwise it bloats tables.
- Record rules align with the parent's `_inherit` chain — verify before adding new ones.

### F. Monkey-patches / install/uninstall symmetry
- Registry hooks: `_register_hook` paired with a teardown path so uninstall restores originals.
- Patching base classes in 17 still goes through `setattr` — but verify the addon doesn't rely on import-order side effects.

### G. Manifest hygiene
- `data` order: `security/` → `data/` → `views/` → menus.
- `depends` lists exactly the modules referenced by imports / inherits.
- `version`: `17.0.<major>.<minor>.<patch>`.
- `license`: matches project default (`LGPL-3` or `OEEL-1` for Enterprise).
- `installable: True`; `application` only when top-level app.

### H. SQL + persisted JSON
- ILIKE on `additional_info` columns that may contain compressed blobs → MEDIUM, doesn't match inner JSON.
- Indexes: missing index for hot WHERE / ORDER BY → MEDIUM perf.
- JSON path through gzip wrappers → BLOCKER if it returns wrong rows.

## 3. Live-verify recipes (Odoo 17 + `realdata_test`)

```python
# Confirm `@api.model_create_multi` is in effect
type(env['<model>'].create).__name__  # 'method' — but check signature accepts list

# Drift between Python default and DB-stored values
env['<model>'].search_count([('<field>', '=', <python_default>)])

# Determinism of an aggregation
sum(env['<model>'].search([(<domain>)]).mapped('<field>'))
# Run via consistency_check_eval (runs=3); fingerprints must match.

# OWL consumer / backend producer cross-check
env['<model>'].search([], limit=10).mapped(lambda r: r._read_format(['field_a', 'field_b']))
```

Raw SQL (when JSON / index suspicion) goes through `postgres.run_select` —
`realdata_test` only accepts ORM expressions, no statements.

## 4. Reporting (Odoo 17 specifics)

Per-finding block adds:

```
- Module: <addon-root>/<module-name>
- Odoo 17 touchpoints: <e.g. "OWL component", "removed attrs/states", "model_create_multi override">
```

Lock file convention: `.codex/audit_findings_<module>_locked.md`. Header
includes the methodology lock paragraph from `_common/code-review` so the
count cannot drift silently.

## 5. Anti-patterns specific to Odoo 17 review

- Flagging missing `@api.multi` — it is correctly absent in 17.
- Suggesting `attrs="..."` / `states="..."` "for backwards compatibility" — they are removed.
- Treating OWL like QWeb-only or jQuery-based — they are different runtimes.
- Re-running an audit without consulting `.codex/audit_findings_*_locked.md` first — that is how counts drift across sessions.

## 6. Final self-check (run BEFORE sending the report)

In addition to the four from `_common/code-review` Step 9, verify:

5. Did I confirm the Odoo version of the addon (`__manifest__.py` `version` field) before applying 17-only rules?
6. Did I cover every Odoo-17-specific dimension (A–H above), not just the generic 16?
7. Did I open `_common/code-review/references/security-checklist.md` when walking Dimension 4 / 9, and `performance-checklist.md` when walking Dimension 2 / 3 / 13 / 15? They contain items not duplicated here.
