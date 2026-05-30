# Community vs Enterprise — runtime edition detection

Companion to `SKILL.md` §0. Referenced by every other pattern in this
skill — `_is_enterprise()` / `_has_module()` are the canonical
branching primitives.

## Why detect at runtime (not at import time)

A single codebase often ships to BOTH editions. Hard-coding
`from odoo.addons.account_accountant...` makes the module
**uninstallable on Community** (ImportError at module load before
`@api.depends` can run). Runtime detection via `ir.module.module`
lets the same code path branch safely.

## Canonical Enterprise markers

The `account_accountant` module is the most reliable Enterprise
marker — every Enterprise tenant has it auto-installed; no Community
tenant has it. Secondary markers (use when `account_accountant` might
be uninstalled e.g. in test fixtures):

| Module | Edition | Notes |
|---|---|---|
| `account_accountant` | Enterprise | **Canonical marker** — auto-installed on Enterprise |
| `sale_subscription` | Enterprise | Recurring billing — moved into `sale.order` in 17+ |
| `mrp_workorder` | Enterprise | MRP work-order lifecycle + tablet UI |
| `helpdesk` | Enterprise | Full helpdesk (Community has only `mail` ticket pattern) |
| `marketing_automation` | Enterprise | Drip campaigns |
| `documents` | Enterprise | Document management |
| `studio` | Enterprise | Visual model designer — `web_studio` in some versions |
| `voip` | Enterprise | Click-to-call |
| `quality` | Enterprise | Quality control points |
| `field_service` | Enterprise | FSM scheduling |

> The Enterprise module list above is a *typical* snapshot — the exact
> set of Enterprise-only modules shifts between majors (e.g.
> `sale_subscription` was folded into `sale.order` in 17+,
> `web_studio`/`studio` naming differs across versions). Always probe
> `ir.module.module` at runtime for the target deployment rather than
> hard-coding the membership list per major.

## Reusable detection helpers

Put on a base mixin or on a `res.config.settings` extension so every
model can call them:

```python
class EditionDetectMixin(models.AbstractModel):
    _name = 'my.edition.detect.mixin'
    _description = 'Edition detection helpers'

    @api.model
    def _has_module(self, module_name):
        """Return True if the given module is installed."""
        return bool(self.env['ir.module.module'].sudo().search([
            ('name', '=', module_name),
            ('state', '=', 'installed'),
        ], limit=1))

    @api.model
    def _is_enterprise(self):
        """Canonical Enterprise check."""
        return self._has_module('account_accountant')

    @api.model
    def _enterprise_modules_installed(self):
        """Return the set of known Enterprise modules currently installed."""
        candidates = [
            'account_accountant', 'sale_subscription', 'mrp_workorder',
            'helpdesk', 'marketing_automation', 'documents', 'studio',
            'voip', 'quality', 'field_service',
        ]
        installed = self.env['ir.module.module'].sudo().search([
            ('name', 'in', candidates),
            ('state', '=', 'installed'),
        ]).mapped('name')
        return set(installed)
```

## §3 — Mail composer fallback (full dispatcher referenced from SKILL.md §5)

```python
class MyOutreach(models.Model):
    _name = 'my.outreach'
    _inherit = ['my.edition.detect.mixin']  # gives us _has_module
    _description = 'Outreach (Community-safe)'

    def _mailing_vals(self, partners, template):
        return {
            'name': self.display_name,
            'mailing_model_id': self.env['ir.model']._get_id('res.partner'),
            'mailing_domain': repr([('id', 'in', partners.ids)]),
            'subject': template.subject,
            'body_html': template._render_field(
                'body_html', partners.ids)[partners[:1].id],
        }

    def _send_batch(self, partners, template_xmlid):
        template = self.env.ref(template_xmlid)
        if self._has_module('mass_mailing'):
            # Community 14+ OR Enterprise — broadcast path
            self.env['mailing.mailing'].create(
                self._mailing_vals(partners, template)
            ).action_send_mail()
        else:
            # vanilla Community pre-14 — per-partner compose
            for p in partners:
                self.env['mail.compose.message'].with_context(
                    default_model='res.partner', default_res_id=p.id,
                    default_use_template=True, default_template_id=template.id,
                    default_composition_mode='comment',
                ).create({})._action_send_mail()
```

## Lazy-import pattern for Enterprise-only models

When you NEED to call into an Enterprise model from shared code:

```python
def _post_to_subscription(self, subscription_id, payload):
    if not self._has_module('sale_subscription'):
        _logger.info("skip subscription post — Community edition")
        return
    Sub = self.env.get('sale.subscription') or self.env.get('sale.order')
    # 17+ merged sale.subscription into sale.order — try both
    if not Sub:
        raise UserError(_("Subscription model not found on this edition"))
    Sub.browse(subscription_id).write(payload)
```

## Detection in `__manifest__.py` is NOT supported

The manifest is a **static dict** — it loads BEFORE `ir.module.module`
exists. Do NOT try `'depends': ['account_accountant'] if is_enterprise else ['account']`.
Instead, ship TWO modules:

- `my_module` (depends on `account`) — Community + Enterprise safe.
- `my_module_enterprise` (depends on `my_module` + `account_accountant`)
  — only installs on Enterprise; can `_inherit` and extend.

## Testing edition branches

In `tests/test_*.py`, use `ir.module.module` patching:

```python
from odoo.tests.common import TransactionCase
from unittest.mock import patch

class TestEditionBranch(TransactionCase):
    def test_community_path(self):
        with patch.object(
            self.env['my.outreach'], '_has_module', return_value=False,
        ):
            self.env['my.outreach']._send_batch(self.partners, 'my.tpl')
            # assert mail.compose.message path taken

    def test_enterprise_path(self):
        with patch.object(
            self.env['my.outreach'], '_has_module', return_value=True,
        ):
            self.env['my.outreach']._send_batch(self.partners, 'my.tpl')
            # assert mailing.mailing path taken
```

## Sibling references

- `odoo-enterprise-patterns` SKILL — Enterprise-specific patterns
  (Agent J's deliverable, forward-reference).
- `references/community-sale-flow.md` — applies `_has_module('analytic')`.
- `references/community-inventory.md` — applies `_has_module('product_expiry')`.
- `references/community-website-controller.md` — applies
  `_has_module('website_sale_subscription')`.
