---
name: odoo-payment-flows
description: Odoo payment provider anti-patterns — hard-coded provider codes, bypassed `payment.transaction` state transitions, PCI-unsafe token logging, sandbox/prod mixed in one DB, unverified webhook signatures. Version-aware: Step 0 detects the addon's Odoo version from `__manifest__.py`, then loads `references/odoo-12-payment-acquirer.md` (pre-v16 `payment.acquirer` + `payment.token`) or `references/odoo-17-payment-provider.md` (v16+ `payment.provider` + `payment.token`, v17 `_compute_payment_state` canonical). Rename v15→v16 (rename landed in 16) is a load-bearing migration boundary — `payment.acquirer` → `payment.provider`, `acquirer_id` → `provider_id`. Audience: Odoo consultancies wiring Stripe / PayPal / VNPay / MoMo / OnePay / local PSPs. Open whenever the user says "payment", "thanh toán", "acquirer", "provider", "stripe", "paypal", "transaction", "webhook", "tokenization", "PCI", or a code-review finding flags `models/payment_*.py` / `controllers/payment_*.py`.
license: MIT
---

# Odoo — Payment Provider Integration Anti-Patterns (version-aware)

Payment bugs are the **highest-blast-radius** class in Odoo: a broken
state transition or a missing webhook signature moves money the wrong
way or replays charges. Defects surface in PSP dashboards and
accounting reconciliation, **not** in the application log — so the
agent must falsify against the transaction state machine, not the UI.

This skill enumerates the **top 5 anti-patterns** every consultancy
hits when wiring `payment.provider` (Stripe / PayPal / Adyen / VNPay /
MoMo / OnePay), with falsification recipes + invariant patterns the
`invariant_guard` hook can auto-enforce.

> Module-agnostic: never hard-codes a specific PSP's API surface.
> Use `codebase.search_model_definitions` on `payment.provider` +
> `models/payment_*.py` before pattern-matching.

Pair with `odoo-code-review` (severity anchors) and
`odoo-data-verification` (live ORM probes against `payment.transaction`).

## 0. Version detection (MANDATORY first step)

The **critical extra signal** is the model rename at v16:

1. `__manifest__.py` `version` — `codebase.read_manifest({module_path})`,
   pattern `^(\d+)\.0\.`.
2. Fallback signals (only if manifest missing):
   - `payment.acquirer` ref → ≤15. `payment.provider` → ≥16. **The
     rename landed at v16, not v15** (verified against installed Odoo
     source 2026-05-29: odoo-15.0 still ships `payment.acquirer.py`;
     odoo-16.0 ships `payment_provider.py`). Pre-v0.27.1 docs said
     v14→v15 — that was wrong.
   - `acquirer_id` field → ≤15. `provider_id` → ≥16.
   - `_compute_payment_state` is defined on **account.move**, NOT on
     payment.transaction — not a reliable provider-side signal. See
     sibling skill `odoo-account-move-overhaul` for account-side
     `payment_state` patterns.
3. Ask the user if signals are inconclusive — rename is too
   consequential to guess.

| Detected major | Reference |
|---|---|
| 12 / 13 / 14 / 15 | `references/odoo-12-payment-acquirer.md` (legacy acquirer model) |
| 16 | `references/odoo-17-payment-provider.md` + flag MEDIUM "first version with rename; verify each call site" |
| 17 | `references/odoo-17-payment-provider.md` |
| 18 / 19 / 20 | apply `references/odoo-17-payment-provider.md` + flag LOW (re-check release notes) |

Official docs: `<ODOO_PAYMENT_DOCS_URL>` (placeholder; default
`https://www.odoo.com/documentation/<version>/applications/finance/payment_providers.html`).

## Transaction state machine (constant across versions)

```
draft → pending → authorized → done
                            ↘ cancel
                            ↘ error
```

Helpers `_set_pending` / `_set_authorized` / `_set_done` /
`_set_canceled` / `_set_error` emit signals downstream cron and
automation depend on. **Never** write `state` directly — see §2.

---

## 1. Pattern A — Hard-coded provider codes instead of `provider.code` lookup

**Confidence: H**

### Problem

Branching on `provider.name == 'Stripe'` (translatable label) is brittle:

- `name` is translatable — `'Stripe'` vs `'Stripe SAS'` breaks `==`.
- A second Stripe provider (EUR vs USD) is indistinguishable.
- v15→v16 (rename landed in 16) rename `acquirer.provider` → `provider.code` turns
  every hard-coded string into a sed target.

Dispatch on `provider.code` **once** at the boundary
(controller / `_get_specific_*` override hook), never in business logic.

### Bad / Good

```python
# Bad — v17 — translatable label match
def _get_processing_url(self):
    if self.provider_id.name == 'Stripe':
        return '/payment/stripe/process'
    raise UserError('Unsupported')

# Good — v17 — override hook in each provider addon
# In payment_stripe/models/payment_transaction.py
def _get_processing_url(self):
    if self.provider_code != 'stripe':
        return super()._get_processing_url()
    return '/payment/stripe/process'

# Good — v12 — 'provider' IS the code field on payment.acquirer
def _get_processing_url(self):
    if self.acquirer_id.provider == 'stripe':
        return '/payment/stripe/process'
    return super()._get_processing_url()
```

### Falsification recipe

Install `vi_VN`, rename Stripe provider's `name` to `'Stripe SAS'`,
trigger the branch. Bug: falls into `UserError`.

```python
# realdata_test MCP eval — skeleton
stripe = self.env.ref('payment.payment_provider_stripe')
stripe.with_context(lang='vi_VN').name = 'Stripe SAS'
tx = self.env['payment.transaction'].create({'provider_id': stripe.id, ...})
self.assertEqual(tx._get_processing_url(), '/payment/stripe/process')
```

### Invariant suggestion

```json
{
  "id": "payment-no-hardcoded-provider-name",
  "applies_to": ["**/models/payment_*.py", "**/controllers/payment_*.py"],
  "rules": {
    "forbid_regex": [
      "(?:provider_id|acquirer_id)\\.name\\s*==",
      "==\\s*['\"](?:Stripe|PayPal|Adyen|VNPay|MoMo|OnePay)['\"]"
    ]
  },
  "severity": "warn",
  "rationale": "name is translatable + multi-instance fragile — see odoo-payment-flows SKILL §1."
}
```

---

## 2. Pattern B — Bypassing `payment.transaction` state transitions

**Confidence: H**

### Problem

`_set_*` helpers do three things atomically:

1. Validate the transition is legal from current state.
2. Write `state` (+ `state_message`, + v17 `last_state_change`).
3. **Emit side-effects** — post linked `account.move`, confirm
   related `sale.order`, fire `mail.template`, schedule
   post-processing cron.

`tx.write({'state': 'done'})` skips all three: tx looks paid in the
UI but the sale order stays draft and the invoice never posts — the
most common "payment went through but order stayed draft" ticket.

### Bad / Good

```python
# Bad — v17 — no signals, no downstream effects
if payload['status'] == 'succeeded':
    tx.write({'state': 'done'})

# Good — v17
if payload['status'] == 'succeeded':
    tx._set_done(state_message=payload.get('message', ''))

# Good — v12 (older helper names)
tx._set_transaction_done()
tx._post_process_after_done()  # folded into _set_done in v15+
```

### Falsification recipe

Create a `sale.order` with linked `payment.transaction` (state
`draft`). Call buggy handler with `status='succeeded'`. Assert
`tx.state == 'done'` ✓ but `so.state == 'sale'` ✗ and
`so.invoice_ids[:1].state == 'posted'` ✗.

```python
# realdata_test MCP eval — skeleton
tx._set_done()
self.assertEqual(so.state, 'sale', "sale.order not auto-confirmed — helper bypass suspected")
self.assertEqual(so.invoice_ids[:1].state, 'posted', "_set_done side-effects skipped")
```

### Invariant suggestion

```json
{
  "id": "payment-no-direct-state-write",
  "applies_to": ["**/models/payment_*.py", "**/controllers/payment_*.py"],
  "rules": {
    "forbid_regex": [
      "\\.write\\(\\{[^}]*['\"]state['\"]\\s*:\\s*['\"](?:done|authorized|pending|cancel|error)['\"]"
    ]
  },
  "severity": "blocker",
  "rationale": "Direct state write bypasses _set_*() signals — sale.order / account.move side-effects don't fire. See odoo-payment-flows SKILL §2."
}
```

(`blocker` — silent + money-relevant.)

---

## 3. Pattern C — Token storage without PCI-aware redaction

**Confidence: H**

### Problem

`payment.token` (all versions; FK `provider_id`/`provider_ref` ≥v16,
`acquirer_id`/`acquirer_ref` ≤v15) stores an
opaque provider-side ref (`provider_ref` / `acquirer_ref`) + a
**display-only masked PAN** (`name`, e.g. `**** **** **** 4242`).
Odoo never stores the full PAN — but consultancy code regularly:

1. Logs full PAN at `_logger.info` "for debug", forgets to remove.
2. Adds a custom `Char` field on `payment.token` to hold raw card data.
3. Returns the full PAN in a JSON-RPC response to a custom dashboard.

Any of these is **PCI-DSS scope contamination** — dev DB and log
aggregator inherit cardholder-data scope, which the consultancy is
almost certainly not certified for. Never store or log anything
beyond the last 4 digits + the masked display string the PSP returns.

### Bad / Good

```python
# Bad — v17 — PCI violation
_logger.info("PAN %s", payload['card_number'])
self.env['payment.token'].create({
    'provider_id': self.id, 'partner_id': payload['partner_id'],
    'provider_ref': payload['stripe_pm_id'],
    'name': payload['card_number'],          # full PAN
    'card_number_raw': payload['card_number'],  # raw custom field
})

# Good — v17 — masked + opaque handle
masked = f"**** **** **** {payload['last4']}"
_logger.info("Token for partner %s (masked: %s)", payload['partner_id'], masked)
self.env['payment.token'].create({
    'provider_id': self.id, 'partner_id': payload['partner_id'],
    'provider_ref': payload['stripe_pm_id'],
    'name': masked,
})
```

For ≤v15: model `payment.token`, FK `acquirer_id`,
redaction rule identical.

### Falsification recipe

1. `grep -rE "card_number|pan|cvv|cvc|security_code" addons/<module>` —
   any non-test hit on a non-redacted context is a finding.
2. Replay tokenization with PAN `4242 4242 4242 4242`.
3. Verify: `payment.token.name` matches `^\*+ ?\*+ ?\*+ ?\d{4}$`;
   logs (`docker logs <odoo>` / `journalctl -u odoo`) must NOT
   contain `4242424242424242`; `information_schema.columns` for
   `payment_token` has no raw-card-shaped columns.

```python
# realdata_test MCP eval — skeleton
import re
self.assertRegex(token.name, r'^\*+\s*\*+\s*\*+\s*\d{4}$',
                 "token.name is not a masked display string")
```

### Invariant suggestion

```json
{
  "id": "payment-no-raw-card-logging",
  "applies_to": ["**/models/payment_*.py", "**/controllers/payment_*.py", "**/wizards/payment_*.py"],
  "rules": {
    "forbid_regex": [
      "_logger\\.(?:info|debug|warning|error)\\([^)]*(?:card_number|pan|cvv|cvc|security_code)",
      "['\"](?:card_number_raw|pan_raw|cvv|cvc|security_code)['\"]\\s*:"
    ]
  },
  "severity": "blocker",
  "rationale": "PCI-DSS scope contamination — see odoo-payment-flows SKILL §3."
}
```

(`blocker` — compliance, not style.)

---

## 4. Pattern D — Provider sandbox vs production mixed in same DB

**Confidence: M**

### Problem

`payment.provider.state` ∈ `'disabled'` / `'enabled'` / `'test'`
(v13+ uses `state`; v12 uses `payment.acquirer.environment` with `'test'` /
`'prod'`). Flipping one row between `'test'` and `'enabled'` at
go-live causes three failures:

- **API keys** for sandbox ≠ prod; flipping `state` doesn't rotate
  them; engineers patch inline + forget to commit.
- **Saved tokens** from sandbox become invalid when the provider
  flips to `'enabled'` — recurring subscriptions break silently the
  next billing cycle.
- **Webhooks** from sandbox + prod target the same URL; without
  filtering on `provider.state`, a sandbox webhook can mark a real
  prod tx as paid.

Correct: **two `payment.provider` rows** — one `'test'`, one
`'enabled'` — and the webhook routes by PSP-side environment
indicator (Stripe `livemode`, PayPal `test_ipn`, VNPay differing
`vnp_TmnCode`).

### Bad / Good

```python
# Bad — v17 — ignores environment
@http.route('/payment/stripe/webhook', type='json', auth='public', csrf=False)
def stripe_webhook(self, **payload):
    tx = request.env['payment.transaction'].sudo().search([
        ('reference', '=', payload['data']['object']['metadata']['ref'])])
    tx._set_done()

# Good — v17 — filter on provider.state matched by livemode
@http.route('/payment/stripe/webhook', type='json', auth='public', csrf=False)
def stripe_webhook(self, **payload):
    expected_state = 'enabled' if payload.get('livemode') else 'test'
    tx = request.env['payment.transaction'].sudo().search([
        ('reference', '=', payload['data']['object']['metadata']['ref']),
        ('provider_id.code', '=', 'stripe'),
        ('provider_id.state', '=', expected_state)])
    if not tx:
        _logger.warning("Stripe webhook with no matching tx (livemode=%s)", payload.get('livemode'))
        return
    tx._set_done()
```

### Falsification recipe

Set up two providers (test + enabled). Send sandbox webhook
(`livemode=false`) referencing prod tx's reference. Bug: prod tx
marked `'done'` without a real charge.

```python
# realdata_test MCP eval — skeleton
self.url_open('/payment/stripe/webhook', json={'livemode': False,
    'data': {'object': {'metadata': {'ref': tx_prod.reference}}}})
tx_prod.invalidate_recordset()
self.assertNotEqual(tx_prod.state, 'done',
                    "Sandbox webhook crossed environment boundary")
```

### Invariant suggestion

```json
{
  "id": "payment-webhook-env-isolation",
  "applies_to": ["**/controllers/payment_*.py"],
  "rules": {
    "must_keep_regex": ["provider_id\\.state|acquirer_id\\.environment"]
  },
  "severity": "warn",
  "rationale": "Sandbox + prod webhooks share the same URL — env filter is mandatory. See odoo-payment-flows SKILL §4."
}
```

---

## 5. Pattern E — Webhook handler without signature verification

**Confidence: H**

### Problem

PSP webhooks are publicly addressable (`auth='public'`, `csrf=False`)
by necessity. Without a signature check on every request, the
endpoint is an open mutation surface:

- Attacker forges `payload['status']='succeeded'` for any enumerable
  `reference`.
- Replay: capture a legit payload, re-send N times to fire
  side-effects N times.
- Sandbox webhooks cross into production (§4).

Per-PSP signature scheme:

| PSP | Header | Verification helper |
|---|---|---|
| Stripe | `Stripe-Signature` | `stripe.Webhook.construct_event(payload, sig, secret)` |
| PayPal | `Paypal-Transmission-Sig` + `Paypal-Cert-Url` | PayPal SDK `WebhookEvent.verify` |
| Adyen | `additionalData.hmacSignature` | `HMACValidator().validate_hmac(...)` |
| VNPay | `vnp_SecureHash` | SHA-512 HMAC of sorted params w/ merchant secret |
| MoMo | `signature` field in payload | SHA-256 HMAC over canonical string |

Verify on **raw bytes** of the request body — not parsed payload —
because JSON re-serialization changes whitespace and breaks HMAC.

### Bad / Good

```python
# Bad — v17 — no signature check
@http.route('/payment/stripe/webhook', type='json', auth='public', csrf=False)
def stripe_webhook(self, **payload):
    tx = request.env['payment.transaction'].sudo().search([
        ('reference', '=', payload['data']['object']['metadata']['ref'])])
    tx._set_done()

# Good — v17 — verify raw bytes BEFORE any ORM access
import stripe
from odoo.exceptions import AccessDenied

@http.route('/payment/stripe/webhook', type='http', auth='public', csrf=False)
def stripe_webhook(self, **_kwargs):
    raw_body = request.httprequest.get_data()  # raw bytes required for HMAC
    sig = request.httprequest.headers.get('Stripe-Signature', '')
    provider = request.env['payment.provider'].sudo().search(
        [('code', '=', 'stripe'), ('state', 'in', ('enabled', 'test'))], limit=1)
    if not provider:
        raise AccessDenied("No active Stripe provider")
    try:
        event = stripe.Webhook.construct_event(raw_body, sig, provider.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise AccessDenied("Invalid Stripe signature")
    # Only NOW touch the ORM:
    tx = request.env['payment.transaction'].sudo().search([
        ('reference', '=', event['data']['object']['metadata']['ref']),
        ('provider_id', '=', provider.id)])
    if event['type'] == 'payment_intent.succeeded':
        tx._set_done()
    return ''
```

### Falsification recipe

POST forged payload (no signature header) referencing a real
`payment.transaction.reference`. Bug: 200 OK + tx flips `'done'`.
Replay: capture a signed payload, re-send within PSP TTL window.
SDK helpers (Stripe `construct_event`) include the timestamp check;
hand-rolled HMAC usually does not.

```python
# realdata_test MCP eval — skeleton
import requests
resp = requests.post(self.base_url() + '/payment/stripe/webhook',
    json={'data': {'object': {'metadata': {'ref': tx.reference}}},
          'type': 'payment_intent.succeeded'})  # no Stripe-Signature header
self.assertNotEqual(resp.status_code, 200)
tx.invalidate_recordset()
self.assertNotEqual(tx.state, 'done', "Forged webhook marked tx as paid")
```

### Invariant suggestion

```json
{
  "id": "payment-webhook-signature-required",
  "applies_to": ["**/controllers/payment_*.py"],
  "rules": {
    "must_keep_regex": [
      "construct_event\\(|validate_hmac\\(|vnp_SecureHash|hmac\\.compare_digest\\("
    ]
  },
  "severity": "blocker",
  "rationale": "Unsigned webhooks are an open mutation surface — see odoo-payment-flows SKILL §5."
}
```

(`blocker` — security, money-relevant.)

---

## 6. Code-review checklist (severity-tagged)

When `odoo-code-review` flags `models/payment_*` or
`controllers/payment_*`, apply:

| # | Check | Sev | § |
|---|---|---|---|
| 1 | No `provider_id.name == '...'` / `acquirer_id.name == '...'` | **H** | §1 |
| 2 | PSP-identity branches use `provider.code` (v16+) / `acquirer.provider` (≤v15) | **H** | §1 |
| 3 | No direct `tx.write({'state': '...'})` — must use `_set_*` helpers | **H/blocker** | §2 |
| 4 | v17+: rely on `_compute_payment_state`, no manual `account.move.payment_state` writes | M | §2 |
| 5 | No raw PAN / CVV / CVC in `_logger.*` calls | **H/blocker** | §3 |
| 6 | No custom `Char` fields on token model holding raw card data | **H/blocker** | §3 |
| 7 | Webhook controllers filter on `provider_id.state` / `acquirer_id.environment` | M | §4 |
| 8 | Saved tokens invalidated when provider flips `'test'` → `'enabled'` | M | §4 |
| 9 | Every public payment route verifies signature BEFORE any ORM mutation | **H/blocker** | §5 |
| 10 | Signature check uses `request.httprequest.get_data()` raw bytes | M | §5 |
| 11 | Replay protection via PSP SDK helper (enforces timestamp TTL) | M | §5 |
| 12 | PSP secrets declared with `groups='base.group_system'` | L | (general) |

H = blocker (money / compliance). M = major. L = nit.

## 7. Cross-references

| Concern | Skill / file |
|---|---|
| Severity anchors for payment findings | `odoo-code-review` §B + `references/odoo-<N>-rules.md` §Payment |
| Universal security checklist | `_common/code-review/references/security-checklist.md` |
| TDD harness w/ mocked PSP fixture | `odoo-tdd` §3 |
| Live ORM probes on `payment.transaction` | `odoo-data-verification` |
| Multi-company `payment.provider.company_id` routing | `odoo-multi-company` §1 + §5 |
| PSP idempotency / retry budgets | undocumented; defer to PSP docs (Stripe `Idempotency-Key`, PayPal `PayPal-Request-Id`) |

## 8. Sibling skills to call BEFORE this one

- `odoo-codebase-discovery` — locate `models/payment_*.py` + read
  manifest before pattern-matching.
- `odoo-deterministic-answers` — `lookup_canonical_decision` for
  project-specific payment rules (e.g. "always VNPay for VND",
  "tokenization disabled for B2B partners") before re-deriving.

## 9. Hard rules summary

- Never branch on `provider_id.name` / `acquirer_id.name` — always
  `provider.code` (v16+) / `acquirer.provider` (≤v15).
- Never write `payment.transaction.state` directly — always
  `_set_pending` / `_set_authorized` / `_set_done` / `_set_canceled` /
  `_set_error`.
- Never log or persist raw PAN, CVV, CVC, or any field that could
  pull the DB into PCI-DSS scope.
- Never share a single `payment.provider` row across sandbox + prod —
  two rows, routed by webhook payload's environment indicator.
- Never serve a payment webhook without verifying the PSP signature
  on the raw request body BEFORE any ORM access.

## 10. References

- `references/odoo-12-payment-acquirer.md` — pre-v16
  `payment.acquirer` + `payment.token`, `acquirer.provider`
  as code field, `_set_transaction_done` helper.
- `references/odoo-17-payment-provider.md` — v16+ `payment.provider`
  + `payment.token`, `provider.code` as code field, v17
  `_compute_payment_state` canonical state computation.
- Odoo docs: `<ODOO_PAYMENT_DOCS_URL>` (placeholder).
