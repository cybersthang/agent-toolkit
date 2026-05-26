# Enterprise accounting — depth reference

Companion to `SKILL.md` §1 (`account.move` state machine) and §2
(multi-company consolidation). All examples use placeholder names — discover
real model names via `codebase.search_model_definitions` before applying.

## `account.move` state machine — the real graph

```
            ┌──────┐  action_post()   ┌────────┐  button_cancel()  ┌────────┐
draft ─────►│ post │ ────────────────►│ posted │ ────────────────► │ cancel │
            │ed?   │                  │        │                   │        │
            └──┬───┘                  └───┬────┘                   └───┬────┘
               │                          │                            │
               │ button_draft()           │ button_draft()              │ button_draft()
               │                          │ (only if NOT locked         │ (always allowed
               │                          │  by company lock_date,      │  in v17+)
               │                          │  hash chain, or            │
               │                          │  account_audit_trail)       │
               ▼                          ▼                            ▼
```

Three gates that block `button_draft()` from a posted move:

1. **Company lock date** (`res.company.fiscalyear_lock_date` /
   `tax_lock_date`) — any move whose `date` falls before the lock is
   refused.
2. **Hash chain** (`l10n_*_edi` + `account_inalterability` in some
   localizations) — once a move is included in the SHA-256 chain, it
   cannot be drafted; only reversed via credit note.
3. **Audit trail** (`account_audit_trail`, Enterprise) — soft lock; any
   draft of a posted move emits a `mail.message` audit entry. Code must
   tolerate the extra message at write time.

`<see Odoo Enterprise account_inalterability module docs>` for the exact
list of localizations that enable hash chains by default.

## Reversal — the safe path for posted moves

```python
# v17 — reverse + new corrected move
def correct_posted_invoice(self, move, new_lines):
    reverse_action = move._reverse_moves(
        default_values_list=[{
            'invoice_date': fields.Date.context_today(self),
            'ref': 'Reversal of: %s' % move.name,
        }],
        cancel=True,   # cancel=True posts the reversal immediately
    )
    corrected = self.env['account.move'].create({
        'move_type': move.move_type,
        'partner_id': move.partner_id.id,
        'invoice_line_ids': [(0, 0, vals) for vals in new_lines],
        'company_id': move.company_id.id,
    })
    corrected.action_post()
    return corrected
```

Key invariants:
- `_reverse_moves` returns the **reversal** move(s), NOT the corrected one.
- `cancel=True` posts the reversal immediately and matches its lines
  against the original — the original ends up `payment_state = 'reversed'`.
- Audit trail: both reversal and corrected move are linked back to the
  original via `reversed_entry_id` and `reversal_move_id` fields.

## `account.move.line` — the balanced-debit-credit invariant

Every `account.move` must satisfy `sum(line_ids.debit) == sum(line_ids.credit)`
in the move's currency. Code that constructs lines by hand often:

```python
# BAD — unbalanced (debit-only)
move = self.env['account.move'].create({
    'move_type': 'entry',
    'line_ids': [
        (0, 0, {'account_id': debit_acc.id, 'debit': 100, 'credit': 0}),
        # forgot the credit leg
    ],
})
move.action_post()  # raises UserError("This entry is not balanced")
```

```python
# GOOD — explicit balanced legs
move = self.env['account.move'].create({
    'move_type': 'entry',
    'line_ids': [
        (0, 0, {'account_id': debit_acc.id, 'debit': 100, 'credit': 0}),
        (0, 0, {'account_id': credit_acc.id, 'debit': 0, 'credit': 100}),
    ],
})
move.action_post()
```

For multi-currency: the balance check happens **in the move's currency**
(`amount_currency` for foreign lines, `debit`/`credit` for the company
currency). Both must balance independently.

## Tax computation — `_compute_taxes()` vs `_recompute_dynamic_lines()`

Posting a customer invoice triggers tax/term lines via
`_recompute_dynamic_lines()` — but only on `write` to specific fields
(`partner_id`, `invoice_line_ids`, `invoice_date`, `currency_id`, …).

Code that mutates `invoice_line_ids` via direct SQL or via `with_context(
check_move_validity=False)` bypasses this recompute → the move posts
with stale tax lines.

```python
# Inspect dynamic-line trigger fields for the target version
fields_recomputed = self.env['account.move']._get_dynamic_line_field_names()
# <see Odoo 17/18 account.move._recompute_dynamic_lines docs>
```

## Pitfalls checklist (paste into review)

- [ ] Any `move.write({...})` on a posted move? If yes, is it preceded
      by `move.button_draft()` AND followed by `move.action_post()`?
- [ ] Any `move.line_ids.unlink()` / `.create(...)` outside an `onchange`
      or `_recompute_dynamic_lines` cycle?
- [ ] Any `check_move_validity=False` context? If yes, what compensates
      for the skipped balance check?
- [ ] Any consolidation loop summing `amount_total` across companies
      without `currency._convert()`? (see SKILL §2)
- [ ] Any direct SQL write to `account_move_line` table? — bypasses
      hash chain, audit trail, and tax recompute.
