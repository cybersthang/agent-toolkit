---
name: odoo-account-move-overhaul
description: Odoo accounting refactor anti-patterns — v13→v14 merged `account.invoice` into `account.move` (with `move_type` selector), v17+ refined `_compute_taxes()` + helper methods (`is_invoice()`, `is_purchase_document()`). Most disruptive accounting overhaul in Odoo's history; breaks 3rd-party modules silently. Version-aware: Step 0 detects addon's Odoo version from `__manifest__.py`, then loads `references/odoo-12-account-invoice.md` (legacy), `references/odoo-14-account-move-unification.md` (merge + `move_type`), or `references/odoo-17-account-refinements.md` (tax recompute + helpers). Open whenever the user says "account.move", "account.invoice", "invoice", "hóa đơn", "move_type", "payment_state", "accounting refactor", "v14 migration", "tax recompute", or when a code-review finding flags hardcoded `state == 'open'` / direct `account.invoice` references.
license: MIT
---

# Odoo — `account.move` Overhaul (v13→v14 merge, v17 refinements)

The `account.invoice` → `account.move` unification (v14) is the most
disruptive accounting refactor in Odoo's history. Modules written for
v12/v13 reference a model that **no longer exists** on v14+; modules
forward-ported to v14/15/16 hit subtly broken tax recompute paths on v17+.

This skill enumerates the **top 5 anti-patterns** every Odoo consultancy
hits when migrating accounting addons across the v13→v14 boundary or
the v16→v17 refinement boundary, with falsification recipes and
invariant suggestions.

> Module-agnostic: never hard-codes journal / tax / fiscal position
> names from a specific project. Discover the target model with
> `codebase.search_model_definitions` before pattern-matching.

Pair with `odoo-code-review` (severity anchors), `odoo-data-verification`
(live ORM probes), and `odoo-multi-company` (accounting is always
company-scoped — patterns compound).

## 0. Version detection (MANDATORY first step)

Same protocol as `odoo-code-review` / `odoo-multi-company`:

1. **`__manifest__.py` `version`** — `codebase.read_manifest({module_path})`,
   pattern `^(\d+)\.0\.`.
2. **Fallback signals** (only if manifest missing):
   - Any reference to `account.invoice` model → ≤13.
   - `move_type` field in code → ≥14.
   - `state in ('open', 'paid')` filter on accounting records → ≤13.
   - `_compute_taxes()` call on `account.move` → ≥17.
   - `is_invoice()` / `is_purchase_document()` helper call → ≥17.
3. **Ask the user** only if signals are inconclusive.

Then load the matching reference:

| Detected major | Reference |
|---|---|
| 12 | `references/odoo-12-account-invoice.md` (legacy `account.invoice`) |
| 13 | both legacy + unification — flag MEDIUM transitional (both models coexist; deprecation warnings) |
| 14 / 15 / 16 | `references/odoo-14-account-move-unification.md` (unified `account.move` + `move_type`) |
| 17 | `references/odoo-17-account-refinements.md` (`_compute_taxes()`, `is_invoice()`, helper-method era) |
| 18 / 19 / 20 | apply `odoo-17-account-refinements.md` + re-check target major's release notes + flag LOW |

### `move_type` field — the five values

| Value | Meaning |
|---|---|
| `out_invoice` | Customer invoice (AR) |
| `out_refund` | Customer credit note |
| `in_invoice` | Vendor bill (AP) |
| `in_refund` | Vendor refund |
| `entry` | Misc journal entry (not invoice-shaped) |

**Never hardcode in business logic** — use helpers (§4).

## 1. Pattern A — Referencing `account.invoice` on v14+

**Confidence: H**

### Problem

`account.invoice` was **removed** in v14. Any reference to
`self.env['account.invoice']`, `comodel_name='account.invoice'`, or XML
view inheritance against `account.invoice_form` raises `KeyError` at
module load — OR (worse) silently no-ops if wrapped in try/except.
Forward-ported modules often miss subtle references in `_inherit`
lists, action XML, security rules, and SQL views.

### Bad

```python
# v14+ — KeyError at runtime, or silent skip if wrapped
def _create_credit_note(self, invoice):
    return self.env['account.invoice'].create({
        'partner_id': invoice.partner_id.id,
        'type': 'out_refund',                       # field also removed!
        'origin_invoice_ids': [(6, 0, [invoice.id])],
    })
```

### Good

```python
# v14+ — use account.move with move_type
def _create_credit_note(self, invoice):
    return self.env['account.move'].create({
        'partner_id': invoice.partner_id.id,
        'move_type': 'out_refund',                  # selection field
        'reversed_entry_id': invoice.id,            # replaces origin_invoice_ids
    })
```

```xml
<!-- v14+ — point action at account.move + filter by move_type -->
<record id="my_invoice_action" model="ir.actions.act_window">
    <field name="res_model">account.move</field>
    <field name="view_id" ref="account.view_move_form"/>
    <field name="domain">[('move_type','in',('out_invoice','out_refund'))]</field>
</record>
```

### Falsification recipe

```python
# 1. grep the addon
#    grep -rn "account\.invoice" --include='*.py' --include='*.xml'
# 2. confirm via eval_orm_expression — model truly gone on v14+:
self.env['ir.model'].search([('model','=','account.invoice')])
# expected on v14+: empty recordset
```

### Invariant suggestion

```json
{
  "id": "account-no-legacy-invoice-model-on-v14plus",
  "description": "account.invoice removed in v14 — references must migrate to account.move.",
  "applies_to": ["**/models/*.py", "**/wizards/*.py", "**/views/*.xml", "**/data/*.xml", "**/security/*.xml"],
  "rules": {"must_not_contain_regex": ["account\\.invoice(?!_)"]},
  "severity": "blocker",
  "rationale": "Dangling account.invoice references crash on load — see odoo-account-move-overhaul SKILL §1."
}
```

---

## 2. Pattern B — Hardcoded `state == 'open'` (legacy invoice state)

**Confidence: H**

### Problem

On v12/v13, `account.invoice.state` had values `draft / proforma / open
/ in_payment / paid / cancel`. On v14+, `account.move.state` only has
`draft / posted / cancel`; payment is tracked separately via
`payment_state`. Code branching on `state == 'open'` is **silently
dead** on v14+ — the filter matches nothing, the cron never fires, the
bug is invisible until a user notices "the reminder never sent".

### Bad

```python
# v14+ — search returns empty; cron silently does nothing
def _cron_dunning(self):
    overdue = self.env['account.move'].search([
        ('move_type','=','out_invoice'),
        ('state','=','open'),                       # v12/v13 only
        ('invoice_date_due','<', fields.Date.today()),
    ])
    overdue.send_reminder()
```

### Good

```python
# v14+ — posted + unpaid via payment_state
def _cron_dunning(self):
    overdue = self.env['account.move'].search([
        ('move_type','=','out_invoice'),
        ('state','=','posted'),
        ('payment_state','in', ('not_paid','partial')),
        ('invoice_date_due','<', fields.Date.today()),
    ])
    overdue.send_reminder()
```

### Falsification recipe

```python
# Audit: grep -rn "state.*['\"]open['\"]" --include='*.py' --include='*.xml'
# Confirm dead filter on the running DB:
self.env['account.move'].search_count([('state','=','open')])
# expected on v14+: 0 (no record can have this state)
```

### Invariant suggestion

```json
{
  "id": "account-no-legacy-state-open-on-v14plus",
  "description": "state='open' is a v12/v13 account.invoice value — v14+ uses state='posted' + payment_state.",
  "applies_to": ["**/models/*.py", "**/wizards/*.py", "**/views/*.xml", "**/report/*.xml"],
  "rules": {"must_not_contain_regex": ["'state'\\s*,\\s*'='\\s*,\\s*'open'"]},
  "severity": "blocker",
  "rationale": "Silent dead code path — see odoo-account-move-overhaul SKILL §2."
}
```

---

## 3. Pattern C — Treating `payment_state` as a boolean

**Confidence: H**

### Problem

`payment_state` is a **Selection** with 6 values:
`not_paid / in_payment / paid / partial / reversed / invoicing_legacy`.
Code that treats it as truthy/falsy (`if move.payment_state:`) is
**always** True (every move has a value). Worse, hardcoded
`payment_state == 'paid'` ignores `in_payment` (bank statement not yet
posted) and `partial` cases — double-charging customers or skipping
legitimate paid invoices.

### Bad

```python
# v14+ — meaningless: payment_state is always truthy
def is_done(self, move):
    if move.payment_state:                          # always True
        return True
    return False

# v14+ — misses 'in_payment' and 'reversed' cases
def get_unpaid(self):
    return self.search([('payment_state', '!=', 'paid')])
```

### Good

```python
# v14+ — explicit enumeration over the Selection values
PAID_STATES = ('paid', 'in_payment', 'reversed')

def is_done(self, move):
    return move.payment_state in PAID_STATES

def get_unpaid(self):
    return self.search([('payment_state', 'in', ('not_paid', 'partial'))])
```

### Falsification recipe

```python
# How many "paid-equivalent" moves does a naive == 'paid' filter MISS?
self.env['account.move'].search_count([
    ('move_type','=','out_invoice'),
    ('state','=','posted'),
    ('payment_state','in', ('in_payment','reversed')),
])
# any non-zero count = the naive filter drops real paid moves
```

### Invariant suggestion

```json
{
  "id": "account-payment-state-is-selection-not-bool",
  "description": "payment_state is a Selection — never use as bool; always compare against the 6 known values.",
  "applies_to": ["**/models/*.py", "**/wizards/*.py"],
  "rules": {
    "must_keep_regex": ["payment_state\\s*(?:==|!=|in|not in)\\s*[\\('\\\"]"]
  },
  "severity": "warn",
  "rationale": "Bare `if move.payment_state:` is always True — see odoo-account-move-overhaul SKILL §3."
}
```

---

## 4. Pattern D — Hardcoding `move_type` instead of helpers

**Confidence: H**

### Problem

Hardcoding `move_type in ('out_invoice', 'in_invoice')` is unreadable
and breaks when Odoo adds a new type (e.g. `out_receipt` /
`in_receipt`). v17+ ships official helpers:

| Helper | True when `move_type` is |
|---|---|
| `is_invoice(include_receipts=False)` | `out_invoice`, `out_refund`, `in_invoice`, `in_refund` (+receipts if flag) |
| `is_purchase_document()` | `in_invoice`, `in_refund`, `in_receipt` |
| `is_sale_document()` | `out_invoice`, `out_refund`, `out_receipt` |
| `is_inbound()` | `out_invoice`, `in_refund` (money flowing in) |
| `is_outbound()` | `in_invoice`, `out_refund` (money flowing out) |

### Bad

```python
# v17 — hardcoded tuple, misses receipts, no semantic intent
def _apply_discount(self, move):
    if move.move_type in ('out_invoice', 'in_invoice'):
        return self._compute_discount(move)
```

### Good

```python
# v17+ — semantic helper, forward-compatible
def _apply_discount(self, move):
    if move.is_invoice(include_receipts=True):
        return self._compute_discount(move)

# v14/15/16 (helpers less complete) — extract the tuple at least
INVOICE_TYPES = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')

def _apply_discount(self, move):
    if move.move_type in INVOICE_TYPES:
        return self._compute_discount(move)
```

### Falsification recipe

```python
# Grep:  grep -rn "move_type.*in.*(" --include='*.py'
# Confirm helpers exist on the target version:
hasattr(self.env['account.move'], 'is_invoice')   # True on v17+
```

### Invariant suggestion

```json
{
  "id": "account-prefer-is-invoice-helper-on-v17plus",
  "description": "Prefer is_invoice() / is_purchase_document() over hardcoded move_type tuples on v17+.",
  "applies_to": ["**/models/*.py", "**/wizards/*.py"],
  "rules": {
    "must_keep_regex": ["\\.is_(?:invoice|purchase_document|sale_document|inbound|outbound)\\("]
  },
  "severity": "warn",
  "rationale": "Hardcoded move_type tuples break on new selection values — see odoo-account-move-overhaul SKILL §4."
}
```

---

## 5. Pattern E — Manual tax/total computation bypassing `_compute_taxes()`

**Confidence: H**

### Problem

On v17+, `account.move._compute_taxes()` is the canonical entry point
for recomputing tax lines after any structural edit (price, quantity,
tax_ids, fiscal_position_id). It handles rounding strategies
(`round_per_line` vs `round_globally`), price-include taxes, discount
cascading, and tax group merging — all interacting in non-trivial ways.

Manual computation (`amount = sum(l.price_subtotal for l in lines) * 1.10`)
produces off-by-cent drift especially with multi-line invoices,
tax-included prices, cascading taxes (tax-on-tax), and fiscal-position
remappings.

Same problem on raw SQL `UPDATE account_move_line ...` bypassing the
ORM — `account.move.line.parent_state` cache, analytic distribution,
and balance recompute all silently desync.

### Bad

```python
# v17+ — drifts cents on multi-line / mixed-tax invoices
def _recompute_total(self, move):
    untaxed = sum(line.price_subtotal for line in move.invoice_line_ids)
    move.amount_untaxed = untaxed
    move.amount_tax = untaxed * 0.10
    move.amount_total = untaxed * 1.10

# v17+ — raw SQL silently desyncs parent_state, analytic, audit trail
self.env.cr.execute("""
    UPDATE account_move_line SET balance = balance * 1.05 WHERE move_id = %s
""", (move.id,))
```

### Good

```python
# v17+ — mutate lines via ORM, then trigger canonical recompute
def _recompute_total(self, move):
    move.invoice_line_ids = [(1, line.id, {'price_unit': new_price})
                              for line, new_price in updates]
    move._compute_taxes()       # rounding, price-include, cascading all handled
    # amount_untaxed / amount_tax / amount_total are computed fields —
    # never assign them directly
```

### Falsification recipe

```python
# Drift probe — before/after _compute_taxes() must match if your manual
# math is correct. Any delta = silent drift accumulating across batches.
before = move.amount_total
move._compute_taxes()
after  = move.amount_total
assert before == after, f"drift detected: {before} != {after}"
```

### Invariant suggestion

```json
{
  "id": "account-no-manual-total-recompute-on-v17plus",
  "description": "Use account.move._compute_taxes() — never assign amount_total/amount_tax directly, never raw SQL on account_move_line.",
  "applies_to": ["**/models/*.py", "**/wizards/*.py"],
  "rules": {"must_keep_regex": ["\\._compute_taxes\\(\\)"]},
  "severity": "blocker",
  "rationale": "Manual recompute drifts cents; raw SQL desyncs parent_state — see odoo-account-move-overhaul SKILL §5."
}
```

---

## 6. Migration probe recipes (`eval_orm_expression`)

Use `odoo-data-verification`'s `eval_orm_expression` MCP tool to probe
the running database before/after migration:

```python
# 1. Does the legacy model still exist? (sanity check)
self.env['ir.model'].search([('model','=','account.invoice')])
# expected on v14+: empty

# 2. Count dead state filters in actual data
self.env['account.move'].search_count([('state','=','open')])
# expected on v14+: 0

# 3. Audit view references to the removed model
self.env['ir.ui.view'].search_count([('arch_db','ilike','account.invoice')])
# any non-zero on v14+ = dangling view inheritance

# 4. Audit menu / action references
self.env['ir.actions.act_window'].search([('res_model','=','account.invoice')])
# any non-empty on v14+ = broken menu entry

# 5. payment_state histogram — confirm tests exercise all 6 cases
self.env['account.move'].read_group(
    [('move_type','=','out_invoice'), ('state','=','posted')],
    ['payment_state'], ['payment_state'],
)
```

## 7. Code-review checklist (H/M/L tags)

| Check | Tag | Where |
|---|---|---|
| No `'account.invoice'` string in `.py` / `.xml` on v14+ | **H** | §1 |
| No `state == 'open'` on `account.move` | **H** | §2 |
| `payment_state` compared against explicit value tuple, never bare-truthy | **H** | §3 |
| Hardcoded `move_type` tuples replaced with `is_invoice()` / `is_purchase_document()` on v17+ | **M** | §4 |
| Tax recompute via `_compute_taxes()`, never manual `sum * rate` | **H** | §5 |
| No raw SQL on `account_move_line` (parent_state / analytic / balance desync) | **H** | §5 |
| `migrations/14.0.x.y.z/pre-*.py` renames `type` → `move_type` on legacy data | **M** | §1 + OCA OpenUpgrade |
| Reports / QWeb templates use `payment_state` selection labels, not strings | **L** | §3 |
| Inter-company invoice flows scope to source company via `with_company()` | **M** | cross-link `odoo-multi-company` §1 |

## 8. Cross-references

| Concern | Skill / file |
|---|---|
| Severity anchors for accounting findings | `odoo-code-review` §D + `references/odoo-<N>-rules.md` §F |
| Multi-company accounting (every move is company-scoped) | `odoo-multi-company` §1 + §4 |
| Live ORM probes against posted moves | `odoo-data-verification` `eval_orm_expression` |
| TDD harness for accounting tests (`AccountTestInvoicingCommon`) | `odoo-tdd` §3 |
| Index strategy on large move tables (`company_id, state, payment_state`) | `odoo-performance` |
| Migration scripts (OCA OpenUpgrade patterns) | `odoo-codebase-discovery` references |

## 9. Sibling skills to call BEFORE this one

- `odoo-codebase-discovery` — locate the target accounting model + read
  its manifest before pattern-matching.
- `odoo-deterministic-answers` — call `lookup_canonical_decision` for
  project-specific accounting rules before re-deriving.
- `odoo-multi-company` — accounting is **always** company-scoped;
  patterns from that skill compound on every check here.

## 10. Hard rules summary

- Never reference `account.invoice` on v14+ — model removed.
- Never filter `account.move.state == 'open'` on v14+ — state is
  `draft / posted / cancel`.
- Never treat `payment_state` as a boolean — it is a 6-value Selection.
- Never hardcode `move_type` tuples on v17+ — use `is_invoice()` /
  `is_purchase_document()` helpers.
- Never assign `amount_total` / `amount_tax` directly; recompute via
  `_compute_taxes()` (v17+) or a draft/post round-trip (v14–v16).
- Never `UPDATE account_move_line` via raw SQL — `parent_state`,
  analytic distribution, and balance cache desync silently.
