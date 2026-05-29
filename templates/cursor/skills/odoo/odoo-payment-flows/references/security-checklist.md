# Payment integration — security checklist (Odoo)

Focused checklist for `controllers/payment_*.py` + `models/payment_*.py`.
Version-neutral; field/method names follow the detected era — see
`odoo-12-payment-acquirer.md` (≤15) / `odoo-17-payment-provider.md` (≥16).

> Anchors verified against odoo/odoo 16.0/17.0 + the payment dev reference
> (2026-05-29): `payment_utils.generate_access_token` / `check_access_token`
> (HMAC + `consteq`), `_handle_notification_data` (≥16) /
> `_handle_feedback_data` (≤15), `_set_*` helpers, `payment.token` with
> `provider_ref` (≥16) / `acquirer_ref` (≤15).

## 1. Webhook signature verification — on RAW bytes, BEFORE the ORM

A PSP webhook is `auth='public', csrf=False` by necessity → an open
mutation surface. Verify the signature on the **raw request body** before
touching the ORM. JSON re-serialization changes whitespace and breaks HMAC.

```python
@http.route('/payment/stripe/webhook', type='http', auth='public', csrf=False)
def stripe_webhook(self, **_kw):
    raw = request.httprequest.get_data()                  # raw bytes — required
    sig = request.httprequest.headers.get('Stripe-Signature', '')
    prov = request.env['payment.provider'].sudo().search(   # ≤15: payment.acquirer
        [('code', '=', 'stripe'), ('state', 'in', ('enabled', 'test'))], limit=1)
    try:
        event = stripe.Webhook.construct_event(raw, sig, prov.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise Forbidden()                                  # reject 4xx, do NOT _set_done
    # only NOW: search tx + _handle_notification_data(...)
```

- [ ] Every public payment route verifies the PSP signature first.
- [ ] Verification uses `request.httprequest.get_data()` raw bytes, not `**post`.
- [ ] Hand-rolled HMAC uses `hmac.compare_digest` / `odoo.tools.consteq`
      (constant-time) — never `==`.
- [ ] Per-PSP scheme: Stripe `Stripe-Signature` (`construct_event`),
      PayPal `Paypal-Transmission-Sig`, Adyen `hmacSignature`,
      VNPay `vnp_SecureHash` (SHA-512 HMAC of sorted params),
      MoMo `signature` (SHA-256 HMAC of canonical string).
- [ ] Webhook secret stored on the provider with `groups='base.group_system'`.

## 2. Idempotency + replay protection

Webhooks are retried by the PSP and replayable by an attacker. Firing
side-effects twice double-posts invoices / double-confirms orders.

- [ ] Outbound charges send a PSP idempotency key (Stripe `Idempotency-Key`,
      PayPal `PayPal-Request-Id`) so retries don't double-charge.
- [ ] Inbound webhooks are idempotent: `_set_done` is naturally guarded
      (illegal transition from `done`), but custom side-effects must
      no-op when `tx.state` is already terminal.
- [ ] Replay window enforced: SDK helpers (Stripe `construct_event`) check
      the timestamp; hand-rolled HMAC must add a freshness/TTL check.
- [ ] Dedupe on the PSP event id where one is provided.

## 3. Never trust the client amount

The client must not be able to set what it pays. Odoo's own
`/payment/transaction` accepts `amount` from the payload but binds it with
an HMAC `access_token`:

```python
# payment_utils.generate_access_token(partner_id, amount, currency_id)
#   → HMAC(db_secret, 'partner|amount|currency')   ← server-side, at render
# payment_utils.check_access_token(token, partner_id, amount, currency_id)
#   → consteq() constant-time compare; mismatch ⇒ ValidationError
```

- [ ] Custom transaction-create routes regenerate/verify the access_token
      (or re-derive the amount from the linked sale.order / account.move
      server-side) — never charge a bare client-supplied figure.
- [ ] On webhook, reconcile the PSP-reported amount + currency against
      `tx.amount` / `tx.currency_id` before `_set_done`; mismatch ⇒ error.
- [ ] State is moved only via `_set_*` helpers — a forged
      `status: succeeded` reaches a verified handler, never a raw write.

## 4. CSRF + route hygiene

- [ ] `csrf=False` appears ONLY on PSP-callback routes (machine-to-machine);
      signature check (§1) is the compensating control. Never disable CSRF
      on a user-driven form route.
- [ ] Callback routes are `auth='public'` (PSP is unauthenticated) but
      do the minimum before signature verification.
- [ ] Reject with 4xx (`Forbidden` / `AccessDenied`) on bad signature —
      a 200 invites replay and tells the attacker the endpoint is live.
- [ ] Validate/normalize the `reference` before searching — never
      interpolate payload into raw SQL (use the ORM domain).

## 5. `sudo()` discipline

Public callbacks legitimately need `sudo()` (no logged-in user), but scope
it tightly.

- [ ] `sudo()` is used only to reach the specific provider/tx record, not
      sprinkled across the whole handler.
- [ ] Searches under `sudo()` are constrained by `provider_id`/`acquirer_id`
      + `reference` so one PSP's webhook can't mutate another's tx.
- [ ] Sandbox/prod isolation: filter on `provider.state` (≥16) /
      `acquirer.environment` (v12) / `acquirer.state` (v13-15) matched to
      the PSP env flag (Stripe `livemode`, PayPal `test_ipn`) — a sandbox
      webhook must not mark a prod tx paid.
- [ ] No `with_user`/key escalation beyond what the callback needs.

## 6. PCI scope — keep the DB out of cardholder scope

Storing or logging raw card data pulls the whole DB + log aggregator into
PCI-DSS scope the consultancy almost certainly isn't certified for.

- [ ] No full PAN / CVV / CVC / `security_code` in `_logger.*` (even at
      `debug`). Log the masked display + `provider_ref`, never the secret.
- [ ] No custom `Char` on `payment.token` holding raw card data. Store
      only `provider_ref` (opaque handle, ≥16) / `acquirer_ref` (≤15) +
      the masked display (`payment_details` ≥16 / `name` ≤15).
- [ ] No raw card data returned in any JSON-RPC / dashboard endpoint.
- [ ] Tokenization is delegated to the PSP (Stripe.js / Elements, hosted
      fields) so the raw PAN never transits the Odoo server (SAQ-A scope).
- [ ] Grep gate: `card_number|pan|cvv|cvc|security_code` on non-test,
      non-redacted code is a finding.

## 7. Secrets + config

- [ ] API keys / webhook secrets declared with `groups='base.group_system'`
      so non-admins can't read them.
- [ ] Sandbox and prod use distinct provider rows with distinct keys —
      flipping `state` does not rotate keys.
- [ ] Secrets sourced from config/env at deploy, never committed.

## Severity mapping (for odoo-code-review)

| Check | Sev | SKILL § |
|---|---|---|
| Unsigned / non-raw-bytes webhook | **blocker** | §5 |
| Direct `state` write (bypasses `_set_*`) | **blocker** | §2 |
| Raw PAN/CVV logged or stored | **blocker** | §3 |
| Client amount trusted without token/reconcile | **blocker** | §1+§5 |
| Missing idempotency / replay window | major | §5 |
| Sandbox/prod env not filtered | major | §4 |
| Broad/unscoped `sudo()` | major | — |
| `csrf=False` on a non-callback route | major | §5 |
| Secrets without `group_system` | nit | §6 |

blocker = money / compliance / security. See SKILL.md for falsification
recipes + `invariant_guard` regex patterns.
