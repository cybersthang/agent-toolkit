# Odoo ≥16 — `payment.provider` subsystem (standalone)

Standalone reference. Load when Step 0 detected major **16 / 17** (apply
to 18/19/20 too, then re-check release notes). The model is
`payment.provider` here — renamed from `payment.acquirer` in **v16**
(PR odoo/odoo#90899, "[IMP] payment(_*), *: rename acquirer to provider",
merged into master = 16.0, Sept 2022). The rename also flipped
`acquirer_id` → `provider_id` and the code field `provider` → `code`.

> Verified against odoo/odoo branches 16.0 / 17.0 + the 16.0/17.0
> developer reference (payment_provider.html, payment_transaction.html)
> 2026-05-29. **v16 is the FIRST version with the rename** — flag MEDIUM
> and verify each call site when the addon targets 16.

## Models

| Model | Code field | Mode field | Tx FK | Opaque ref | Masked display |
|---|---|---|---|---|---|
| `payment.provider` | **`code`** (Selection, "technical code") | `state` = `disabled`/`enabled`/`test` | — | — | — |
| `payment.transaction` | `provider_code` (related `provider_id.code`) | — | `provider_id` → `payment.provider` | — | — |
| `payment.token` | — | — | `provider_id` | **`provider_ref`** | **`payment_details`** (clear part, formatted `•••• 1234` via `_build_display_name`) |

Token field renames vs ≤15: `acquirer_id`→`provider_id`,
`acquirer_ref`→`provider_ref`, masked `name`→`payment_details`. Model name
stays `payment.token`. Full card data is NEVER persisted — only
`provider_ref` (opaque handle) + the clear part in `payment_details`.

## Provider model — dispatch on `code`

```python
prov = self.env['payment.provider'].search([('code', '=', 'stripe')], limit=1)
# self.provider_id.code == 'stripe'   ← stable, the canonical dispatch key
# self.provider_code    == 'stripe'   ← related shortcut on the tx
# self.provider_id.name == 'Stripe'   ← translatable, NEVER ==
```

`state` gates sandbox vs prod: `'disabled'` / `'enabled'` / `'test'`.
Two rows (one `test`, one `enabled`), routed by the PSP-side env flag —
see SKILL.md §4.

### Provider override hooks (v16/17 dev reference)

```python
class PaymentProvider(models.Model):
    _inherit = 'payment.provider'
    code = fields.Selection(selection_add=[('stripe', 'Stripe')],
                            ondelete={'stripe': 'set default'})

    def _compute_feature_support_fields(self):   # tokenization/refund/capture flags
        super()._compute_feature_support_fields()
        ...
    def _get_supported_currencies(self): ...
    def _get_default_payment_method_codes(self): ...
    def _should_build_inline_form(self, is_validation=False): ...   # direct vs redirect
    def _get_redirect_form_view(self, is_validation=False): ...
```

`_get_compatible_providers` filters by company / partner country /
currency / required features — do not re-implement that filtering.

## Transaction state machine

```python
# v16/17 helper names — short form (verified)
tx._set_pending(state_message=None)
tx._set_authorized(state_message=None)
tx._set_done(state_message=None)
tx._set_canceled(state_message=None)
tx._set_error('reason')                  # state_message required
```

State selection (constant): `draft / pending / authorized / done /
cancel / error`. **Never** `tx.write({'state': ...})` — the helpers fire
sale.order confirmation, account.move posting, and post-processing. (Note:
`_compute_payment_state` lives on **account.move**, not payment.transaction.)

## Webhook / notification flow — "notification" terminology

The ≤15 "feedback" methods are renamed to **"notification"** in v16+
(verified 16.0/17.0). Override these in the PSP addon:

```python
class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'stripe' or tx:
            return tx
        ref = notification_data.get('reference')
        return self.search([('reference', '=', ref),
                            ('provider_code', '=', 'stripe')], limit=1)

    def _process_notification_data(self, notification_data):   # rarely called directly
        if self.provider_code != 'stripe':
            return super()._process_notification_data(notification_data)
        self.provider_reference = notification_data.get('id')
        status = notification_data.get('status')
        if status == 'succeeded':
            self._set_done()
        elif status in ('processing', 'requires_action'):
            self._set_pending()
        elif status == 'failed':
            self._set_error(notification_data.get('message', ''))
```

`_handle_notification_data(provider_code, notification_data)` is the public
entry point: it matches the tx (`_get_tx_from_notification_data`), then
processes it (`_process_notification_data`) and returns the recordset.
Controller calls it AFTER verifying the signature (security-checklist.md).

## Controller flow

```python
# Generic routes in addons/payment/controllers/portal.py (v16/17):
#   /payment/pay            http   public   — render the form
#   /payment/transaction    json   public   — create draft tx, return processing values
#   /my/payment_method      http   user     — manage tokens
#   /payment/confirmation   http   public   — post-payment landing
#   /payment/archive_token  json   user
#
# /payment/transaction validates the client amount via an HMAC access_token
# bound to (partner_id, amount, currency_id) — NOT raw trust. Then:
#   tx_sudo = ..._create_transaction(...)     # sudo() on the public route
#   return tx_sudo._get_processing_values()    # carries flow: redirect|direct|token
```

`flow ∈ {'redirect','direct','token'}` selects QWeb redirect form vs
inline (S2S) vs saved-token charge. PSP-specific values come from
`_get_specific_processing_values` / `_get_specific_rendering_values`.

## S2S (direct / inline) + tokenization

```python
# Direct charge + tokenize: store ONLY opaque handle + masked display.
self.env['payment.token'].create({
    'provider_id': self.provider_id.id,
    'partner_id': partner.id,
    'provider_ref': psp_payment_method_id,   # opaque PSP handle
    'payment_details': last4,                # clear part only (e.g. '4242')
})
# tx._send_payment_request()   — charge a saved token (S2S)
# tx._send_refund_request()    — refund (creates a refund child tx)
# tx._create_child_transaction(...) — partial capture / split
```

`_send_payment_request` / `_send_refund_request` are the v16/17 S2S entry
points (verified 16.0/17.0). Never store full PAN/CVV — PCI scope.

## Hard rules (≥16)

- Code field is **`code`** on `payment.provider`; dispatch on
  `provider_id.code` / `provider_code` — never `name`.
- Token: FK **`provider_id`**, handle **`provider_ref`**, masked display
  **`payment_details`** (not `name`, not `acquirer_*`).
- Webhook methods are **`_..._notification_data`** (renamed from
  `_..._feedback_data` at v16).
- Helpers `_set_pending/_set_authorized/_set_done/_set_canceled/_set_error`
  only — never write `state`.
- v16 is the rename boundary: when targeting 16, verify every call site;
  ≤15 addons use `payment.acquirer` / `acquirer_id` / `provider` field
  (see odoo-12-payment-acquirer.md).
