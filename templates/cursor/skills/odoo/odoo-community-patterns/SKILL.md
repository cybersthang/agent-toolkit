---
name: odoo-community-patterns
description: Odoo Community-only depth patterns — sale.order→account.move flow without Enterprise helpers, stock.move reservation chain (multi-warehouse pitfalls), website/eCommerce controller routing (CSRF, sudo-leak, sitemap), product variant Cartesian explosion, mail.compose.message fallback (no marketing_automation). Each pattern carries a falsification recipe that reproduces the bug on a vanilla Community install (no `account_accountant`, no `sale_subscription`, no `helpdesk`). Module-agnostic — placeholder model names. Open whenever the user says "community", "no enterprise", "free version", "sale to invoice", "stock.move", "website controller", "product variant", "mail composer", or when an edition-detection branch is needed. Pair with `odoo-enterprise-patterns` (forward-reference — Agent J), `odoo-multi-company`, `odoo-performance`.
---

# Odoo — Community Edition patterns (depth)

Community-only subsystems where Enterprise helper modules
(`account_accountant`, `sale_subscription`, `helpdesk` full,
`mrp_workorder`, `marketing_automation`) are NOT installed. Each
pattern carries a *falsification recipe* — concrete steps to reproduce
the bug on a vanilla Community install.

> **Module-agnostic.** Placeholders (`my.model`, `my.lead`). Discover
> real models via `codebase.search_model_definitions`. Confidence tags:
> H (stable), M (version-sensitive), L (uncertain). Version-sensitive
> claims should be re-checked against the target Odoo version's release
> notes before being cited in a customer-facing report.

## 0. Edition detection (MANDATORY first step)

Full method in `references/community-vs-enterprise-detection.md`:

```python
def _is_enterprise(self):
    return bool(self.env['ir.module.module'].sudo().search([
        ('name', '=', 'account_accountant'),
        ('state', '=', 'installed'),
    ], limit=1))
```

| Topic | Reference |
|---|---|
| Sale → invoice flow | `references/community-sale-flow.md` |
| Stock move / picking reservation | `references/community-inventory.md` |
| Website / eCommerce routing | `references/community-website-controller.md` |
| Edition detection helpers | `references/community-vs-enterprise-detection.md` |

## 1. Pattern A — Sales order to invoice (Community accounting) — H

**Problem.** `sale.order.action_confirm()` does NOT auto-create the
invoice — it flips SO to `sale` + triggers stock picking. Invoice
creation needs explicit `_create_invoices()`. The `account.move` lives
in `account` (Community); NO `account_accountant`, so analytic
dimensions, budget reconciliation, follow-up rules, audit trail are
absent. Code calling `move._follow_up_send()` silently no-ops.

```python
# BAD: assumes confirm creates invoice
order.action_confirm()
order.invoice_ids[:1].action_post()  # empty recordset → no-op or error

# GOOD: explicit creation + defensive empty-check
order.action_confirm()
invoices = order._create_invoices()
if invoices:
    invoices.action_post()
```

**Falsification recipe.**
1. Community + `sale` + `account` (NOT `account_accountant`); SO 1 line;
   `action_confirm()` → assert `len(order.invoice_ids) == 0`.
2. `_create_invoices()` → 1 `account.move` returned.
3. `move.button_draft()` succeeds (no audit-trail block); on
   Enterprise the hash-chain gate refuses — see
   `odoo-enterprise-patterns` §1.

See `references/community-sale-flow.md` for analytic fallback.

**vs Enterprise.** Enterprise blocks `button_draft()` via audit-trail
+ hash chain; on Community NONE of those guards exist.

## 2. Pattern B — Stock move chain reservation — H

**Problem.** `stock.move._action_assign()` reserves `stock.quant` rows
**warehouse-scoped via `move.location_id`**. Multi-warehouse code that
filters quants by `product_id` alone reserves from the WRONG
warehouse, leaving the source picking with unreserved moves while a
sibling warehouse shows phantom shortage. Without Enterprise
`mrp_workorder` / `stock_barcode` there is no auto-rebalance.

```python
# BAD: quant search omits location_id → cross-warehouse reservation
quants = self.env['stock.quant'].search([
    ('product_id', '=', move.product_id.id),  # missing location_id
    ('quantity', '>', 0),
])

# GOOD: delegate to Odoo's engine (honors location_id, removal strategy,
# lot/owner). Then verify per-move:
picking.action_assign()
for m in picking.move_ids:
    if m.state != 'assigned':
        _logger.warning("move %s short at %s (%s/%s)",
            m.id, m.location_id.complete_name,
            m.reserved_availability, m.product_uom_qty)
```

**Falsification recipe.**
1. 2 warehouses (WH1, WH2). 10 P in WH1/Stock, 0 in WH2/Stock.
2. Picking WH2/Stock → WH2/Output for 5 P; `action_assign()`.
3. Assert `move.state == 'confirmed'`, `reserved_availability == 0`. If
   `assigned` with availability 5 — code reserves cross-warehouse.

See `references/community-inventory.md` for FIFO/FEFO + lot pitfalls.

**vs Enterprise.** Base `_action_assign` identical; Community angle:
no auto-rebalance via planned work orders.

## 3. Pattern C — Website / eCommerce controller routing — M

**Problem.** Three repeating bugs on Community website controllers:
1. **CSRF default**: older majors (v12–v15) default `csrf=False`; later
   majors flipped the default to `True`. Always declare `csrf=`
   explicitly in code rather than relying on the version-specific
   default — confirm the target version's behaviour before assuming
   either way.
2. **`sudo()` leak**: `auth='public'` runs as `public`; broad
   `sudo()` on POST handlers lets anonymous traffic create records
   as superuser.
3. **SEO**: only routes with `website=True` appear in
   `website._enumerate_pages` sitemap.

```python
# BAD: sudo leak + no csrf + invisible to sitemap
@http.route('/my/submit', type='http', auth='public', methods=['POST'])
def submit(self, **post):
    return request.env['my.lead'].sudo().create(post)

# GOOD: explicit csrf, validated payload, narrow sudo, sitemap-visible
@http.route('/my/submit', type='http', auth='public',
            methods=['POST'], csrf=True, website=True)
def submit(self, **post):
    vals = self._validate_lead_payload(post)  # whitelist + sanitize
    if not vals:
        return request.render('website.404')
    request.env['my.lead'].sudo().create(vals)
    return request.render('my_module.thanks')
```

**Falsification recipe.**
1. Community + `website`. Route `csrf=False` + `auth='public'` on 16+;
   POST via `curl` with NO csrf_token. 12–15: accepted. 16+: 400.
2. Sudo-leak: malicious POST → verify created record has
   `create_uid == 1` (admin).

See `references/community-website-controller.md` for decorator matrix.

**vs Enterprise.** `website_sale_*` adds payment-acquirer + richer SEO;
base routing identical.

## 4. Pattern D — Product variant explosion — H

**Problem.** `product.template` × N `product.attribute` values = up to
`product(values_per_attr)` `product.product` rows. Calling
`template._create_variant_ids()` without a cap explodes from 100 →
10,000 → millions in a few clicks. Community has NO `product_matrix`
widget — the only safeguard is a hard cap.

```python
# BAD: blindly attach + regenerate → Cartesian explosion (100 → 10k → ...)
line.value_ids = [(4, new_val.id)]
template._create_variant_ids()

# GOOD: project count, enforce cap BEFORE creating
MAX_VARIANTS = 500
projected = len(line.value_ids) + 1
for l in (template.attribute_line_ids - line):
    projected *= max(1, len(l.value_ids))
if projected > MAX_VARIANTS:
    raise UserError(_("Would create %d variants (cap %d)",
                      projected, MAX_VARIANTS))
self.env['product.attribute.value'].create(
    {'attribute_id': attribute.id, 'name': name})
template._create_variant_ids()
```

**Falsification recipe.**
1. `product.template` + 3 attributes × 10 values; `_create_variant_ids()`
   → 1000 variants.
2. Add 4th attribute × 10 values → 10,000. With cap, raises `UserError`
   before exploding.

**vs Enterprise.** `product_matrix` grid UX + bulk archiving exist;
math identical. Cross-ref `odoo-performance` for SQL impact.

## 5. Pattern E — Mail composer fallback (no marketing_automation) — M

**Problem.** Enterprise `marketing_automation` = drip campaigns + A/B +
lead scoring. Community has `mail.compose.message` and (in recent
majors) `mass_mailing.mailing` as a stand-alone module — the exact
major where `mass_mailing` was split out from `marketing_automation`
depends on the version, so always probe `ir.module.module` for
`mass_mailing` rather than gating on a hard-coded major. Code that does
`from odoo.addons.marketing_automation...` raises `ImportError` on
Community boot.

```python
# BAD: import-time crash on Community boot
from odoo.addons.marketing_automation.models.campaign import Campaign

# GOOD: runtime branch on ir.module.module (full dispatcher in
# references/community-vs-enterprise-detection.md §3)
def _send_batch(self, partners, template):
    if self._has_module('mass_mailing'):
        self.env['mailing.mailing'].create(self._mailing_vals(
            partners, template)).action_send_mail()
    else:
        for p in partners:
            self.env['mail.compose.message'].with_context(
                default_model='res.partner', default_res_id=p.id,
                default_use_template=True, default_template_id=template.id,
                default_composition_mode='comment',
            ).create({})._action_send_mail()
```

**Falsification recipe.**
1. Community WITHOUT `mass_mailing`; module importing
   `odoo.addons.marketing_automation` → `ImportError` at boot.
2. Good `_send_batch` with `mail` only + 3 partners → 3 `mail.mail` rows.
3. Install `mass_mailing`, re-run → 1 `mailing.mailing` + 3
   `mailing.trace`. Confirms branch dispatch.

**vs Enterprise.** `odoo-enterprise-patterns` (forward-ref — Agent J)
covers `marketing_automation` workflow + drip-campaign state machine.

## Sibling skills

- `odoo-enterprise-patterns` — forward-ref (Agent J); Enterprise shape.
- `odoo-multi-company` — `company_id` mechanics shared with Pattern A.
- `odoo-performance` — Pattern D SQL pressure on `product.product`.
- `odoo-data-verification` — live ORM probes via `realdata_test` MCP.
- `odoo-code-review` — finding gate.
