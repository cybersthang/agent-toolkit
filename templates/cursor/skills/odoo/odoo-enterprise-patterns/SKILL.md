---
name: odoo-enterprise-patterns
description: Odoo Enterprise depth patterns — account.move state machine, multi-company accounting consolidation, sale_subscription auto-billing, helpdesk SLA breach detection, MRP work-order lifecycle. Each pattern carries a falsification recipe. Module-agnostic; uses placeholder model names. Pair with `odoo-multi-company` (consolidation overlap) and `odoo-performance` (BOM explosion = N+1 risk). Open whenever the user says "enterprise", "account.move", "subscription", "MRP", "manufacturing", "helpdesk SLA", "consolidation", or when an Enterprise-only addon (`account_consolidation`, `sale_subscription`, `helpdesk`, `mrp_workorder`) is in scope.
---

# Odoo — Enterprise patterns (depth)

Five Enterprise-only bug classes. Each has a *falsification recipe* —
concrete steps to deterministically verify the bug exists.

> Module-agnostic — discover real models via `codebase.search_model_definitions`.
> Confidence tags: **H** stable; **M** version-sensitive (verify against
> release notes); **L** placeholder. Unstable Enterprise internals tagged
> `<see Odoo X release notes>` instead of invented details.

## 0. Version detection (MANDATORY)

Read `__manifest__.py` via `codebase.read_manifest`. Fallback signals:
`@api.multi` → ≤13; `_check_company_auto = True` → ≥13;
`mrp.workorder.working_state` → ≥13; `subscription_state` on `sale.order` → ≥17.

| Topic | Reference |
|---|---|
| Accounting + `account.move` | `references/enterprise-accounting.md` |
| Subscription / recurring billing | `references/enterprise-subscription.md` |
| MRP / BOM / work orders | `references/enterprise-mrp.md` |

Helpdesk SLA stays inline (§4).

## 1. Pattern A — `account.move`: cannot edit posted (H)

**Problem.** `account.move` is a state machine: `draft` → `posted` →
(optional) `cancel`. Once posted, `_check_lock_date` + `_check_balanced`
+ audit trail forbid modifying lines or date. Naive `move.write({...})`
on a posted move either raises `UserError` deep in a controller or
silently rolls back. Safe path: `button_draft()` → modify →
`action_post()`, OR `_reverse_moves(...)`.

**Bad:**
```python
def fix_amount(self, move, new_amount):
    move.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')\
        .write({'price_unit': new_amount})  # raises / rolls back silently
```

**Good:**
```python
def fix_amount(self, move, new_amount):
    if move.state == 'posted':
        move.button_draft()
    move.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')\
        .write({'price_unit': new_amount})
    move.action_post()
```
For periods past the lock date, `button_draft()` itself refuses — use
`_reverse_moves(default_values_list=[{...}], cancel=True)`.
`<see Odoo 17/18 account.move._reverse_moves docs>` for the exact signature.

**Falsify.** Create + post a customer invoice. Attempt
`move.line_ids[0].write({'price_unit': 999})`. Observe either `UserError`
mentioning "posted", OR write appears to succeed but value unchanged
after fresh ORM read. If neither — codebase has monkey-patched the
constraint; flag.

## 2. Pattern B — Multi-company consolidation (M)

`<see Odoo Enterprise account_consolidation docs>` for the target version.

**Problem.** Each company has its own sub-ledger, currency, chart of
accounts. Consolidation means **per-currency conversion at line level** —
NOT a flat sum. The bug: summing `amount_total` across companies without
converting per move date. Off-by-cent drift scales with rate volatility ×
line count. Overlaps with `odoo-multi-company` Pattern B (currency
rounding) — read that first for conversion mechanics.

**Bad:**
```python
def consolidated_revenue(self, companies, date_range):
    total = 0.0
    for company in companies:
        moves = self.env['account.move'].search([
            ('company_id', '=', company.id), ('state', '=', 'posted'),
            ('invoice_date', '>=', date_range[0]),
            ('invoice_date', '<=', date_range[1]),
        ])
        total += sum(moves.mapped('amount_total'))  # mixes currencies
    return total
```

**Good:**
```python
def consolidated_revenue(self, companies, date_range, target_currency):
    total = 0.0
    for company in companies:
        moves = self.env['account.move'].search([
            ('company_id', '=', company.id), ('state', '=', 'posted'),
            ('invoice_date', '>=', date_range[0]),
            ('invoice_date', '<=', date_range[1]),
        ])
        for move in moves:
            src = move.currency_id
            amount = src.round(move.amount_total)
            total += amount if src == target_currency else src._convert(
                amount, target_currency, company, move.invoice_date,
            )
    return total
```

**Falsify.** Two companies, different currencies (USD parent, EUR
child). Post 1 invoice each, both `amount_total = 100`. Consolidate
targeting USD. Assert result == `100 + (100 * EUR→USD rate)`, NOT `200`.
If exactly `200` → mixing currencies.

## 3. Pattern C — Subscription auto-billing: card-failure (M)

`<see Odoo 17/18 sale_subscription release notes>` — merging into `sale.order`.

**Problem.** Recurring crons charge cards. On decline, naive code either
lets the exception bubble (whole cron transaction rolls back → ALL subs
fail), or silently swallows (sub stays `in_progress`, no invoice, no
dunning). Correct shape: per-subscription `savepoint`, persist failure,
trigger dunning.

**Bad:**
```python
def _cron_recurring_invoice(self):
    for sub in self.search([('state', '=', 'in_progress'),
                            ('recurring_next_date', '<=', fields.Date.today())]):
        invoice = sub._recurring_create_invoice()
        sub._do_payment(invoice)  # raises on decline → kills whole batch
        sub.recurring_next_date = sub._next_invoice_date()
```

**Good:**
```python
def _cron_recurring_invoice(self):
    for sub in self.search([('state', '=', 'in_progress'),
                            ('recurring_next_date', '<=', fields.Date.today())]):
        with self.env.cr.savepoint():
            try:
                invoice = sub._recurring_create_invoice()
                sub._do_payment(invoice)
                sub.write({'recurring_next_date': sub._next_invoice_date(),
                           'payment_failure_count': 0, 'payment_last_error': False})
            except (UserError, ValidationError) as exc:
                sub.write({'payment_failure_count': sub.payment_failure_count + 1,
                           'payment_last_error': str(exc)})
                sub._trigger_dunning()
```

**Falsify.** Three subs: A (good), B (declined), C (good); all
`recurring_next_date = today`. Run cron. Assert A + C have new invoices
and advanced dates; B has `payment_failure_count == 1` and unchanged
date. If A and C are unchanged → whole batch rolled back; no savepoint.

## 4. Pattern D — Helpdesk SLA breach detection (M)

`<see Odoo Enterprise helpdesk release notes>` for `time` field unit.

**Problem.** `helpdesk.sla` honors `resource.calendar` (business hours)
but the breach flag is recomputed by a cron, not on write. Two bugs:
(1) reading `ticket.sla_status` right after create sees stale `False`;
(2) custom escalation uses raw `datetime.now() - create_date`, ignoring
team calendar — produces different breach timestamps than SLA cron.

**Bad:**
```python
def is_breached(self, ticket):
    elapsed = fields.Datetime.now() - ticket.create_date
    return elapsed.total_seconds() / 3600 > ticket.sla_policy_id.time  # raw clock
```

**Good:**
```python
def is_breached(self, ticket):
    calendar = ticket.team_id.resource_calendar_id
    if not calendar:
        return False
    deadline = calendar.plan_hours(ticket.sla_policy_id.time, ticket.create_date)
    return fields.Datetime.now() > deadline
```

**Falsify.** SLA `time = 2` hours, team with "9–5 Mon–Fri" calendar.
Create ticket Friday 4pm. Wait until Monday 10am (clock ~66h, business
~2h). Assert `ticket.sla_deadline` ≈ Monday 10am, NOT Friday 6pm. If
escalation flags Friday 6pm → calendar-aware logic missing.

## 5. Pattern E — MRP work-order lifecycle (M)

`<see Odoo Enterprise mrp_workorder release notes>` for `state` selection.

**Problem.** MO must explode in order: `action_confirm` (explode BOM)
→ `action_assign` (reserve components) → loop WOs
(`button_start`/`button_finish`) → `button_mark_done`. Skip reservation
→ backflush writes negative `qty_available`. Bonus N+1 risk: looping
`bom_line_ids` with per-line `get_stock` — pair with `odoo-performance` §1.1.

**Bad:**
```python
def produce_batch(self, product, qty):
    mo = self.env['mrp.production'].create({
        'product_id': product.id, 'product_qty': qty,
        'bom_id': product.bom_ids[:1].id,
    })
    mo.button_finish()  # skips confirm → explode → reserve
```

**Good:**
```python
def produce_batch(self, product, qty):
    mo = self.env['mrp.production'].create({
        'product_id': product.id, 'product_qty': qty,
        'bom_id': product.bom_ids[:1].id,
    })
    mo.action_confirm()   # explodes BOM
    mo.action_assign()    # reserves components
    for wo in mo.workorder_ids:
        wo.button_start(); wo.qty_producing = qty; wo.button_finish()
    mo.button_mark_done()
```

**Falsify.** BOM with 1 finished + 2 components; set component stock = 0.
Call the "bad" routine — expect no exception. Inspect `stock.quant`. If
`qty_available < 0` → backflushed without reservation. If `UserError`
raises at `button_finish` mentioning missing components → code refused.
Either confirms reservation was the gate.

## Sibling skills

- `odoo-multi-company` — read first for currency conversion mechanics
  before §2 (consolidation overlap).
- `odoo-performance` — §5 (BOM explosion) is an N+1 risk; cite
  `references/odoo-<N>-perf.md` §1.1 for measurement protocol.
- `odoo-code-review` — finding gate (severity anchors).
- `odoo-data-verification` — live ORM probes for the falsification
  recipes via `realdata_test` MCP.
