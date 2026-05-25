# Odoo 12 — multi-company specifics (pre-`with_company` era)

Standalone reference: 12 does NOT cascade from 17 — the API surface for
multi-company is fundamentally different (no `with_company()` helper, no
`_check_company_auto`, `env.company` is per-recordset not per-environment).

Load this when Step 0 detected major = **12**.

## 1. The `force_company` context key

In Odoo 12 the canonical way to switch company context for an ORM
operation is `with_context(force_company=<id>)`. This is read by:

- `res.company.compute_currency_rates()` / currency rate lookups.
- `res.users._get_company()` (when the user has multiple `company_ids`).
- The cache key for company-dependent fields (`company_dependent=True`).
- Default value resolution (`default=lambda s: s.env['res.company']._company_default_get(...)`).

```python
# v12 — explicit force_company on every cross-company op
invoice = self.env['account.invoice'].with_context(
    force_company=order.company_id.id,
).create({
    'company_id': order.company_id.id,
    'partner_id': order.partner_id.id,
    # ...
})
```

The `company_id` in `vals` is ALSO required — `force_company` only
affects defaults / lookups, not the final stored value. Both are needed.

## 2. `self.env.user.company_id` vs `self.env.user.company_ids`

- `company_id` (singular) — the user's *currently active* company (the
  one selected in the top-right switcher). Volatile, racy, request-scoped.
- `company_ids` (plural) — the set of companies the user is allowed to
  access. Stable.

Use `company_ids` in `ir.rule` domains. Use `company_id` only when you
explicitly want the active switcher state (rare — almost always a bug).

```xml
<!-- security/x_security.xml — v12-compatible multi-company rule -->
<record id="my_model_company_rule" model="ir.rule">
    <field name="name">my.model: multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">
        ['|',('company_id','=',False),('company_id','in',company_ids)]
    </field>
</record>
```

The `('company_id','=',False)` arm lets records with NO company (shared
catalog data) be visible to everyone — drop it if your model is strictly
per-company.

## 3. `_company_default_get` for default company on a Many2one

```python
# v12 — canonical default-company lambda
class MyModel(models.Model):
    _name = 'my.model'

    company_id = fields.Many2one(
        'res.company',
        default=lambda s: s.env['res.company']._company_default_get('my.model'),
    )
```

The `_company_default_get(model_name)` helper consults
`ir.property` overrides before falling back to `self.env.user.company_id`.
Use this instead of bare `lambda s: s.env.user.company_id` — it
respects per-model property overrides.

In v17+ this is replaced by `default=lambda s: s.env.company`.

## 4. `company_dependent=True` fields

In v12, `company_dependent=True` on a field stores the value in
`ir.property` keyed by company. Reading the field automatically returns
the value for `self.env.user.company_id` (or `force_company` if in
context).

```python
property_account_payable_id = fields.Many2one(
    'account.account',
    company_dependent=True,
    string='Account Payable',
)
```

Pitfall: writing `company_dependent=True` fields without
`force_company` writes to the *active* company's property — not the
record's company. Always wrap writes in
`.with_context(force_company=rec.company_id.id)`.

## 5. `mail.mail` / `mail.thread` company resolution in v12

`mail.template.send_mail()` in v12 reads `self.env.user.company_id`
(via `force_company` if present in context) to pick the outgoing
`ir.mail_server`. There is NO `with_company()` chain in v12.

Always wrap cron / batch mail dispatch:

```python
def _cron_send(self):
    for rec in self.env['my.model'].search([]):
        template.with_context(
            force_company=rec.company_id.id,
        ).send_mail(rec.id, force_send=True)
```

## 6. Tests for multi-company in v12

`SavepointCase` is available (renamed in 17+). Standard 2-company
fixture pattern:

```python
from odoo.tests.common import SavepointCase

class TestMultiCompany(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Company = cls.env['res.company']
        cls.company_a = cls.Company.create({'name': 'Company A'})
        cls.company_b = cls.Company.create({'name': 'Company B'})
        cls.multi_user = cls.env['res.users'].create({
            'name': 'Multi-User',
            'login': 'multi@test',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
        })
```

`@api.multi` decorator is still required on recordset-iterating
methods in v12 — including any multi-company helper methods you write.

## 7. Currency rate lookup in v12

`res.currency._convert(from_amount, to_currency, company, date)` exists
in v12 but the signature is older — verify by `<see Odoo 12 currency
module source>`. The `company` argument controls which company's
`res.currency.rate` rows are consulted (rates are stored per-company in
v12 via `ir.property`).

Pitfall: passing the wrong company picks the wrong rate table and
produces silent FX drift. See `references/odoo-multi-currency.md`.

## 8. v12-specific hard rules

- Never use bare `s.env.user.company_id` as a default — use
  `_company_default_get('<model>')`.
- Never write `company_dependent=True` fields without
  `with_context(force_company=...)`.
- Never use `with_company()` — does not exist in v12; will raise
  `AttributeError`.
- `ir.rule` domains must reference `company_ids` (plural), never
  `user.company_id.id` (singular) — singular is request-scoped and
  breaks the multi-company UX.
- `@api.multi` required on every recordset-iterating method, including
  the multi-company helpers in this skill.
