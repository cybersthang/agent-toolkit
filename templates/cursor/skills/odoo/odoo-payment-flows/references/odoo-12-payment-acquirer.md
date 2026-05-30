# Odoo ≤15 — legacy `payment.acquirer` subsystem (standalone)

Standalone reference. Load when Step 0 detected major **12 / 13 / 14 / 15**.
The model is `payment.acquirer` here; it is renamed to `payment.provider`
in **v16** (PR odoo/odoo#90899, merged into master = 16.0). Everything
below uses `acquirer_id` / `acquirer.provider`.

> Verified against odoo/odoo branches 12.0 / 13.0 / 15.0
> (2026-05-29). Field/method names confirmed per-branch — see the
> version-delta table; do NOT assume cross-version uniformity.

## Models

| Model | Notes |
|---|---|
| `payment.acquirer` | The PSP config row. Code field is **`provider`** (a Selection), NOT a `code` field. |
| `payment.transaction` | The money record + state machine. FK `acquirer_id` → `payment.acquirer`; opaque ref in `acquirer_reference`. |
| `payment.token` | Saved payment method. Model name is **`payment.token`** (NOT `payment.acquirer.token`). FK `acquirer_id`; opaque handle `acquirer_ref`. |

## Version deltas WITHIN the legacy era (load-bearing)

| Fact | v12 | v13 / v14 | v15 |
|---|---|---|---|
| Acquirer mode field | `environment` = `test` / `prod` | `state` = `disabled` / `enabled` / `test` | `state` (same) |
| Tx state helpers | `_set_transaction_done` … | `_set_transaction_done` … | **`_set_done`** … (short form) |
| Webhook entry method | hand-rolled per PSP | hand-rolled per PSP | `_handle_feedback_data` / `_get_tx_from_feedback_data` / `_process_feedback_data` |
| Controller create route | per-PSP | per-PSP | `/payment/transaction` → `_get_processing_values` |
| Token masked display | `short_name` (computed) | `short_name` / `name` | **`name`** (anonymized acquirer ref) |

> The "feedback" naming + `/payment/transaction` + `_get_processing_values`
> are the **v14→v15 payment rewrite**. v13 still ships `_set_transaction_*`
> and per-PSP controllers. **v14 is a transition release** — verify each
> method name on the 14.0 branch before relying on it (do not assume v15
> shape applies to 14).

## Acquirer model — the `provider` code field

```python
# payment.acquirer (v12-15) — branch on the CODE, never the label
acq = self.env['payment.acquirer'].search([('provider', '=', 'stripe')], limit=1)
# self.acquirer_id.provider == 'stripe'   ← stable
# self.acquirer_id.name    == 'Stripe'    ← translatable, NEVER ==
```

`environment` (v12) vs `state` (v13+) gates sandbox/prod — see anti-pattern
§4 in SKILL.md. v12: `environment in ('test','prod')`; v13+:
`state in ('disabled','enabled','test')`.

## Transaction state machine — helper names differ

```python
# v12 / v13 / v14 — LEGACY helper names (verified v12, v13)
tx._set_transaction_pending()
tx._set_transaction_authorized()
tx._set_transaction_done()        # NOT _set_done in v12-13
tx._set_transaction_cancel()
tx._set_transaction_error(msg)

# v15 — short form (post-rewrite, verified 15.0)
tx._set_pending()
tx._set_authorized()
tx._set_done(state_message='')
tx._set_canceled()
tx._set_error('reason')
```

State selection is constant across the era:
`draft / pending / authorized / done / cancel / error`. **Never** write
`state` directly — the helper fires sale.order / account.move side-effects.

## Webhook / form feedback

```python
# v15 — override these in the PSP addon (feedback terminology)
class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _get_tx_from_feedback_data(self, provider, data):
        if provider != 'stripe':
            return super()._get_tx_from_feedback_data(provider, data)
        ref = data.get('reference')
        return self.search([('reference', '=', ref),
                            ('acquirer_id.provider', '=', 'stripe')], limit=1)

    def _process_feedback_data(self, data):
        if self.acquirer_id.provider != 'stripe':
            return super()._process_feedback_data(data)
        # verify signature on RAW bytes BEFORE this point (controller)
        if data['status'] == 'succeeded':
            self._set_done()
        elif data['status'] == 'failed':
            self._set_error(data.get('message', ''))

# Controller dispatches to _handle_feedback_data (matches + processes)
# request.env['payment.transaction'].sudo()._handle_feedback_data('stripe', data)
```

For v12-14 there is no canonical `_handle_feedback_data` — PSP addons
hand-roll the controller → search `acquirer_id` → `_set_transaction_*`
sequence. Verify the exact entry point on the target branch.

## Controller flow (v15)

```python
# /payment/transaction is type='json', auth='public' (v15)
# It validates the client amount via an HMAC access_token bound to
# (partner_id, amount, currency_id), then:
#   tx_sudo = self._create_transaction(...)        # sudo on public route
#   return tx_sudo._get_processing_values()         # flow: redirect|direct|token
```

The `flow` concept (`'redirect'` / `'direct'` / `'token'`) and
`_get_processing_values` exist from **v15**. Pre-v15 each PSP exposed its
own `/payment/<psp>/...` routes.

## S2S (server-to-server / direct + tokenization)

```python
# Tokenization: store ONLY the opaque handle + masked display.
self.env['payment.token'].create({
    'acquirer_id': self.acquirer_id.id,
    'partner_id': partner.id,
    'acquirer_ref': psp_token_id,     # opaque PSP handle
    'name': f'**** **** **** {last4}',# masked display (v15: `name`)
})
# NEVER store full PAN / CVV / CVC — PCI scope. See security-checklist.md.
```

S2S charge with a saved token routes through the same `_set_*` helpers
after the PSP confirms — never flip `state` manually.

## Hard rules (legacy era)

- Code field is **`provider`** on `payment.acquirer` (NOT `code`).
- Token model is **`payment.token`** with FK **`acquirer_id`** (NOT
  `payment.acquirer.token`).
- v12 mode = `environment`(test/prod); v13+ = `state`(disabled/enabled/test).
- v12-13 helpers are `_set_transaction_*`; v15 is `_set_*`. Verify v14.
- Feedback methods (`_handle_feedback_data`) are **v15+**; the v16 rename
  flips them to `_..._notification_data` (see odoo-17 reference).
- Always verify the exact name on the detected branch — this era spans a
  full payment-module rewrite at v15.
