# Odoo 19 — Code Review Reference (Version-Specific Deltas)

Load this file when Step 0 of `odoo-code-review/SKILL.md` detects major
version **19**. Combine with the shared dimensions in the parent SKILL.md,
the cross-version checklists under `_common/code-review/references/`, and
— since 19 is mostly an evolution of 18 — `odoo-18-rules.md` for all the
17→18 changes.

Odoo 19 was released in **October 2025**. Most 18-era APIs still apply.
The 19-specific deltas are the new `Domain` API, controller type renames,
declarative constraints/indexes, and the Python 3.12 recommendation.

## A. Inherits all 18 rules

Treat every Odoo-18 rule (`odoo-18-rules.md`) as applying to 19 unless
explicitly overridden below.

## B. Python runtime

- **Python 3.12 is recommended**; 3.10 is the minimum still supported.
- Flag LOW if `__manifest__.py` declares anything below 3.10 in dev environment instructions.
- New 3.12-specific syntax allowed (PEP 695 generic syntax, etc.) — use sparingly until team comfort confirmed.

## C. Controller type renames (NEW in 19 — common 18→19 break)

The internal web client renames JSON-RPC controller types to avoid confusion:

| Old (v18 or earlier) | New (v19+) | Migration |
|----------------------|------------|-----------|
| `type="json"` | `type="jsonrpc"` | Rename the `type=` keyword. Both `/web/dataset/call_kw` and any custom `/<endpoint>` decorated with `type='json'` need the rename. |
| (n/a) | `type="json2"` | New cleaner JSON family — opt in for new endpoints; do NOT rewrite existing `jsonrpc` endpoints without a migration plan. |
| `/jsonrpc` HTTP endpoint | Same path, scheduled for **removal in Odoo 22** (fall 2028) | Stay on `jsonrpc` for now; plan migration to JSON-2 before 22. |

External integrations:
- `/xmlrpc`, `/xmlrpc/2`, `/jsonrpc` endpoints scheduled for removal in 22. Flag LOW if a new integration uses XML-RPC.

### Severity calibration (controller types)

| Severity | Example |
|----------|---------|
| BLOCKER  | Controller uses `@http.route(type='json')` in a 19 codebase where the framework already migrated to `jsonrpc` — endpoint silently breaks |
| MEDIUM   | New endpoint declares `type='json'` — works during transition but flagged in framework deprecation warnings |
| LOW      | Existing `type='jsonrpc'` endpoint not yet migrated to `json2` — acceptable until 22 |
| LOW      | New integration uses `/xmlrpc/2` instead of `jsonrpc` — works until 22 |

## D. New `Domain` API + `any!` operator

Odoo 19 introduces `odoo.Domain` and `odoo.domain` for programmatic domain manipulation:

```python
from odoo import Domain

dom = Domain('state', '=', 'done') & Domain('partner_id', '=', partner.id)
records = env['sale.order'].search(dom)
```

New `any!` operator for complex OR logic in domains — reduces need for raw SQL fallbacks:

```python
# OR across multiple Many2one fields
Domain('any!', [
    ('partner_id', '=', partner.id),
    ('parent_id.partner_id', '=', partner.id),
])
```

### Severity calibration (Domain API)

| Severity | Example |
|----------|---------|
| MEDIUM   | Code uses raw SQL or Python-level filtering for a multi-OR domain that `any!` could express cleanly |
| LOW      | Manual list-based domain construction (`[('a','=',1), ('b','=',2)]`) where new `Domain` API would be clearer — style only |
| LOW      | Helper function still takes `args` parameter name (legacy) — rename to `domain` to match 18+ rename |

## E. Declarative constraints + indexes (NEW in 19)

Constraints and indexes can now be declared as **model attributes** instead of `_sql_constraints` / `_sql` migration scripts:

```python
class MyModel(models.Model):
    _name = 'my.model'

    _constraints = [
        ('check_amount_positive', 'CHECK(amount > 0)', 'Amount must be positive'),
    ]
    _indexes = [
        ('my_model_name_unique', '(name)', 'unique'),
    ]
```

`_sql_constraints` (the 12-era tuple list) still works but is **legacy**; new models should use the declarative form.

### Severity calibration (declarative constraints)

| Severity | Example |
|----------|---------|
| MEDIUM   | New model in 19 codebase still uses `_sql_constraints` — works, but flag for consistency with 19 style |
| LOW      | Indexes declared in a migration script instead of `_indexes` attribute — works |

## F. Performance changes

- Module **install** times are 30–50% faster (no review action — informational).
- Module **update** times are ~50% faster.
- Flag LOW only if a custom install hook adds artificial delays / sleeps for "compatibility" with old slow install times — drop them.

## G. AI-powered Server Actions (NEW in 19)

`ir.actions.server` can now declare AI-driven steps using natural-language prompts (Odoo's wrapper around LLM calls):

- Flag MEDIUM if a server action uses AI to mutate critical financial / accounting / customer-PII data without an explicit audit trail.
- Flag MEDIUM if the AI prompt embeds untrusted user input directly (prompt injection risk).
- Flag LOW if the AI step has no fallback path when the model is unavailable.

This is mostly out-of-scope for code review of a single addon — but the addon may **call** a server action, in which case verify the action's safety.

## H. Other 19 changes

- New `_default_*` field convenience methods (consult `__manifest__.py` external dep list).
- `mail.thread` improvements: `track_visibility` becomes `tracking=True` shorthand. Old syntax still works.
- New `Property` field type for per-record dynamic schema. Flag if used: ensure migration path on uninstall.

## Severity anchors (Odoo-19-specific)

| Severity | Concrete example |
|----------|------------------|
| BLOCKER  | All BLOCKER cases from `odoo-18-rules.md` (since 19 inherits 18 deltas) |
| BLOCKER  | Controller `type='json'` in 19 framework already migrated to `jsonrpc` — endpoint 404s |
| MEDIUM   | New endpoint uses `type='json'` instead of `type='jsonrpc'` |
| MEDIUM   | Server action with AI step mutates accounting data without audit trail |
| MEDIUM   | Helper still accepts `args=` keyword (legacy from pre-18 rename) |
| LOW      | New model uses `_sql_constraints` tuple-list instead of declarative `_constraints` |
| LOW      | Complex OR domain hand-built with Python instead of `any!` operator |
| LOW      | External integration uses XML-RPC instead of JSON-RPC / JSON-2 (works until 22) |

## Live-verify recipes (Odoo 19 + realdata_test MCP)

```python
# Confirm Domain API available
from odoo import Domain
hasattr(Domain, 'any')  # or whatever the public API exposes

# Detect controllers still using old type='json'
# (search statically via codebase MCP — no live ORM call needed)

# Module install/update timing baseline
# Run `odoo-bin -u <module> --stop-after-init -d <db>` and time it — 19 should be ~50% faster than 18.
```

## Anti-patterns specific to Odoo-19 review

- Flagging `type='jsonrpc'` as "renamed JSON-RPC concept" — it IS the new canonical type in 19.
- Suggesting external integrations move to `json2` immediately — `jsonrpc` is fine until Odoo 22 (2028).
- Recommending `_sql_constraints` removal for "consistency" without verifying the declarative form fully replaces the migration script.
- Applying v18 controller patterns blindly — `type='json'` in 19 will silently break.

## Migration notes (18 → 19)

When reviewing code that's mid-migration from 18 to 19:
- Grep for `@http.route(..., type='json'` → rename to `type='jsonrpc'`.
- Grep for `args=` keyword in helper functions → align with 18+ `domain=` convention.
- Identify new endpoints worth opting into `type='json2'` for cleaner JSON family.
- Verify Python target ≥ 3.10 (no syntax that requires < 3.10).
- Audit `_sql_constraints` candidates for migration to declarative `_constraints` / `_indexes`.
- Any custom XML-RPC integration → plan a JSON-RPC / JSON-2 path before Odoo 22.
