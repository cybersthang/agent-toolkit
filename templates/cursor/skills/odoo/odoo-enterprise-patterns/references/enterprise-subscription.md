# Enterprise subscription — depth reference

Companion to `SKILL.md` §3 (subscription auto-billing). All examples use
placeholder names — discover real model names via
`codebase.search_model_definitions` before applying.

> **Version note.** `sale.subscription` was a standalone model in
> Odoo 12–16. From 17 onward it has been progressively merged into
> `sale.order` via a `subscription_state` field on the order. Check
> `<see Odoo 17/18 sale_subscription release notes>` for the exact
> rename in your target version. The patterns below use the v12–16
> standalone shape; for v17+, substitute `sale.order` with
> `subscription_state` filter.

## The recurring-invoice cron — anatomy

```python
# Pseudocode for the standard sale_subscription cron
def _cron_recurring_invoice(self):
    today = fields.Date.today()
    domain = [
        ('state', '=', 'in_progress'),
        ('recurring_next_date', '<=', today),
    ]
    for sub in self.search(domain):
        with self.env.cr.savepoint():
            try:
                invoice = sub._recurring_create_invoice()  # creates draft
                invoice.action_post()                       # posts
                sub._do_payment(invoice)                    # charges card
                sub._advance_next_date()                    # next cycle
            except Exception as exc:
                sub._record_payment_failure(exc)
                sub._trigger_dunning()
```

Three pitfall classes inside this loop:

### A. Missing savepoint → batch-poisoning

Without `with self.env.cr.savepoint()`, an exception in one subscription
rolls back the **entire cron transaction**. All subscriptions processed
before the failing one are reverted.

Symptom: cron logs "succeeded" for 50 subscriptions, but no invoices
appear in the DB because subscription #51 raised on `_do_payment`.

### B. `action_post()` before `_do_payment()` — partial state

If `_do_payment` raises but `action_post()` already succeeded, the
invoice is posted (final, in the customer's ledger) but unpaid. The
next cron run will try to charge again, creating a duplicate invoice
unless the code is idempotent.

Fix: either post-then-charge inside one savepoint (the failure rolls
back the post automatically), or charge first then post on success.

### C. `_advance_next_date()` outside the try-block

```python
# BAD — advances even on failure
try:
    sub._do_payment(invoice)
except UserError:
    sub._record_payment_failure(exc)
sub._advance_next_date()  # still runs → skip a billing cycle
```

The next cycle's billing attempt is silently skipped. Customer notices
when the renewal email arrives 60 days later instead of 30.

## Dunning workflow — minimum viable shape

After a failed charge, the dunning workflow should:

1. Set `sub.payment_failure_count += 1`.
2. Set `sub.payment_last_error = str(exc)` for audit / support visibility.
3. Email the customer via a templated `mail.template` (Enterprise:
   `sale_subscription.mail_template_subscription_payment_failure`).
4. Schedule the next retry: `sub.recurring_next_date = today + retry_delta`.
   Common pattern: `[+3 days, +5 days, +7 days, suspend]`.
5. If `failure_count >= max_retries`, transition to `state = 'close'`
   and notify the sales rep via an activity.

```python
def _trigger_dunning(self):
    self.ensure_one()
    max_retries = int(self.env['ir.config_parameter'].sudo()
                      .get_param('subscription.max_payment_retries', '3'))
    if self.payment_failure_count >= max_retries:
        self.write({'state': 'close', 'close_reason_id': self._dunning_close_reason().id})
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary='Subscription closed after %d payment failures' % max_retries,
            user_id=self.user_id.id,
        )
    else:
        retry_offsets = [3, 5, 7]
        delta = retry_offsets[min(self.payment_failure_count - 1, len(retry_offsets) - 1)]
        self.recurring_next_date = fields.Date.today() + relativedelta(days=delta)
        self.message_post_with_template(self._dunning_template().id)
```

`<see Odoo Enterprise sale_subscription dunning workflow docs>` for the
exact default `mail.template` xmlids and `close_reason_id` records
shipped per version.

## Idempotency — the safety net for cron reruns

A subscription cron MUST be safe to run twice in a row (e.g. after a
crash). The standard idempotency key:

```python
# Before creating a new invoice, check for an existing draft on the same period
existing = self.env['account.move'].search([
    ('invoice_origin', '=', sub.code),
    ('invoice_date', '=', sub.recurring_next_date),
    ('state', 'in', ['draft', 'posted']),
], limit=1)
if existing:
    return existing
return sub._recurring_create_invoice()
```

If your codebase lacks this guard, simulate a crash mid-cron (kill the
worker between `_recurring_create_invoice` and `_advance_next_date`) and
re-run — expect duplicate draft invoices for the same period.

## Prorated upgrades / downgrades — the gotcha

When a subscription line changes mid-cycle (upgrade from Tier-A to
Tier-B), the standard Enterprise flow:

1. Generate a credit note for the unused portion of Tier-A.
2. Generate a new invoice for the prorated Tier-B from change date → next renewal.
3. Update `sub.recurring_total` for the next full cycle.

Naive implementations charge the full new amount immediately AND don't
credit the old one — customer is double-charged for overlapping days.

```python
# Sketch — proration math
def _prorate_amount(self, line, change_date):
    days_used = (change_date - self.recurring_last_date).days
    days_in_cycle = (self.recurring_next_date - self.recurring_last_date).days
    return line.price_subtotal * (days_used / days_in_cycle)
```

## Pitfalls checklist (paste into review)

- [ ] Is the per-subscription loop wrapped in `env.cr.savepoint()`?
- [ ] Does `_advance_next_date()` only run on successful payment?
- [ ] Is there an idempotency check before `_recurring_create_invoice()`?
- [ ] Does dunning persist `payment_failure_count` AND `payment_last_error`?
- [ ] Is `max_retries` configurable via `ir.config_parameter`, not hardcoded?
- [ ] On upgrade/downgrade: does proration produce BOTH a credit note
      and a new prorated invoice?
- [ ] On `state = 'close'`, is a follow-up activity scheduled for sales rep?
