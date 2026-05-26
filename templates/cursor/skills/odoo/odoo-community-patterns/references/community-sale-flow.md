# Community sale → invoice flow — depth reference

Companion to `SKILL.md` §1 (Sales order to invoice). All examples use
placeholders — discover real model names via
`codebase.search_model_definitions`.

## The full Community sale → invoice graph

```
draft ──action_confirm()──► sale ──_create_invoices()──► account.move (draft)
                              │                                  │
                              │ (creates stock.picking            │ action_post()
                              │  via procurement)                 ▼
                              ▼                                posted
                          done (after delivery)
```

Key Community-vs-Enterprise differences at each edge:

| Edge | Community | Enterprise |
|---|---|---|
| `action_confirm()` | Creates picking via `procurement.group` | Same + `account_subscription` triggers if SO has recurring lines |
| `_create_invoices()` | Single `account.move` per partner | Same + analytic dimension auto-fill if `account_analytic_default` configured |
| `action_post()` | Locks `state`, computes taxes | Same + audit-trail message + (l10n) hash-chain entry |
| `button_draft()` (posted) | Always allowed (Community has no audit-trail block) | Refused if hash-chained or audit-trail strict mode |

## Analytic accounting on Community

The `analytic_account` module ships with Community but is NOT
auto-installed. Detection + fallback:

```python
def _post_with_analytic(self, invoices, analytic):
    if not analytic:
        invoices.action_post()
        return
    has_analytic = bool(self.env['ir.module.module'].sudo().search([
        ('name', '=', 'analytic'),
        ('state', '=', 'installed'),
    ], limit=1))
    if has_analytic:
        # Field name varies across versions — `analytic_account_id`
        # (single Many2one) in older majors, `analytic_distribution`
        # (JSON dict) once the multi-distribution refactor landed. Probe
        # `hasattr(line, 'analytic_distribution')` rather than gating
        # on a hard-coded major.
        for inv in invoices:
            for line in inv.invoice_line_ids:
                if hasattr(line, 'analytic_distribution'):
                    line.analytic_distribution = {str(analytic.id): 100}
                else:
                    line.analytic_account_id = analytic.id
    invoices.action_post()
```

## `_create_invoices()` signature drift

> The signature + return-type bands below are the typical shape observed
> across the listed majors; the exact cutoffs (especially around the
> `account.invoice` → `account.move` rename and the line-schema
> tightening) shift between point releases. Read the actual method on
> the target Odoo version before quoting the signature in a fix-sketch.

| Version | Signature | Returns |
|---|---|---|
| 12–13 | `_create_invoices(grouped=False, final=False)` | `account.invoice` recordset |
| 14–15 | `_create_invoices(grouped=False, final=False, date=None)` | `account.move` (model renamed) |
| 16+ | `_create_invoices(grouped=False, final=False, date=None)` | `account.move`; line schema changed (`tax_ids` → `tax_ids` Many2many semantics tightened) |

DEV: always log the return type when porting across major versions —
the field rename `account.invoice` → `account.move` in 13 is the most
common port-blocker.

## Partial delivery → partial invoice (Community-specific)

Enterprise `sale_management` adds a "Down payment" wizard that creates
a single `account.move` for the deposit. Community has NO wizard —
the dev must compute `delivered_qty` manually and pass it to
`_create_invoices()` via `default_invoice_policy='delivery'` on the
product OR via the `invoice_status` filter on `order.line`:

```python
# Community-safe partial invoice: only lines with delivered > invoiced
def _create_partial_invoice(self, order):
    pending = order.order_line.filtered(
        lambda l: l.qty_delivered > l.qty_invoiced
    )
    if not pending:
        return self.env['account.move']
    # Set the to_invoice qty on each line, then call _create_invoices
    for line in pending:
        line.qty_to_invoice = line.qty_delivered - line.qty_invoiced
    return order._create_invoices()
```

## Refund / credit note (Community)

Use `account.move.action_reverse()` (the wizard model is
`account.move.reversal`) — same on Community + Enterprise. The
Community-specific bite: no `account_followup` module, so reversed
moves don't trigger dunning workflow automatically.

```python
def reverse_invoice(self, move, reason):
    wizard = self.env['account.move.reversal'].with_context(
        active_model='account.move', active_ids=move.ids,
    ).create({
        'reason': reason,
        'refund_method': 'refund',  # 'refund' | 'cancel' | 'modify'
        'date_mode': 'custom',
        'date': fields.Date.today(),
    })
    res = wizard.reverse_moves()
    return self.env['account.move'].browse(res['res_id'])
```

## Sibling references

- `references/community-vs-enterprise-detection.md` — edition-detection
  helpers + `_has_module()` utility.
- `odoo-multi-company` skill — multi-company SO posting +
  `company_id` mechanics.
- `odoo-enterprise-patterns` §1 — Enterprise `account.move` state
  machine with audit-trail / hash-chain gates that Community lacks.
