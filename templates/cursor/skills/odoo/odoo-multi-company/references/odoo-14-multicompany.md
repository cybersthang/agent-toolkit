> odoo-14 reference (drafted v0.29). Deltas vs odoo-12-multicompany.md (nearest-neighbour) web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

# Odoo 14 — multi-company specifics (`with_company` era)

Standalone reference. **Important**: on multi-company, Odoo 14 is the
OPPOSITE of v12 — it is in the `with_company()` / `env.company` era, not the
`force_company` era. Do NOT cascade the v12 multi-company file; almost every
v12 idiom (`force_company`, `_company_default_get`, per-recordset
`env.company`) is deprecated or dead in 14. The 14 API is essentially the
same as 17, with the nuances below.

Load this when Step 0 detected major = **14**.

## 1. `with_company()` is the canonical context switch

Verified against `odoo/odoo` 14.0 `odoo/models.py` (`def with_company`):
`recordset.with_company(company)` returns a new recordset whose
`env.company` is the passed company (and adds it to `env.companies`). It
propagates to default resolution, `company_dependent` field reads/writes,
currency lookups, `mail.template` server selection, and
`_check_company_auto` checks. Argument is a `res.company` record or `int`.

```python
# v14 — canonical
invoice = self.env['account.move'].with_company(order.company_id).create({
    'company_id': order.company_id.id,
    'partner_id': order.partner_id.id,
})
```

The `company_id` in `vals` is STILL required — `with_company()` shifts
defaults/lookups, not the stored value. Both needed.

## 2. `force_company` context key is DEAD in 14

This is the headline delta vs v12. Verified `odoo/models.py` 14.0
`with_context` logs:

> "Context key 'force_company' is no longer supported. Use
> with_company(company) instead."

`with_context(force_company=...)` no longer switches the company — it only
emits a warning and is ignored. Any v12-era `force_company` code carried
into 14 is a silent bug. Replace with `with_company()`.

## 3. `env.company` / `env.companies` / `env.user.company_id`

Verified `odoo/api.py` 14.0 (`Environment.company`, `Environment.companies`):

- `self.env.company` — the currently active company on the env (set by
  `with_company()` chain or by the user's switcher). This is **env-level**
  in 14, NOT per-recordset like v12.
- `self.env.companies` — the set of allowed companies.
- `self.env.user.company_id` — request-scoped switcher state (same as v12).

**Rule of thumb**: in 14 code use `self.env.company` set explicitly via
`with_company`, not `self.env.user.company_id`.

## 4. `_check_company_auto = True` + `check_company=True`

Verified present in `odoo/models.py` 14.0 (`_check_company_auto` class attr,
`_check_company` method):

```python
class MyModel(models.Model):
    _name = 'my.model'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True)
    partner_id = fields.Many2one('res.partner', check_company=True)
```

`check_company=True` auto-validates on create/write that the target's
`company_id` is compatible with the parent's. Read `_check_company` on the
14.0 branch for the exact `UserError` phrasing before quoting it in a
finding. Use this instead of hand-rolled `if ... raise` company checks.

## 5. `ir.rule` — `company_ids` placeholder (unchanged from v12)

```xml
<record id="my_model_company_rule" model="ir.rule">
    <field name="name">my.model: multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">
        ['|',('company_id','=',False),('company_id','in',company_ids)]
    </field>
</record>
```

Identical syntax to v12/v17 — the `company_ids` placeholder auto-expands to
the user's allowed companies at rule-eval time. The `('company_id','=',False)`
arm shares no-company records; drop it for strictly-per-company models.

## 6. Default company — `s.env.company`, NOT `_company_default_get`

```python
company_id = fields.Many2one(
    'res.company',
    default=lambda s: s.env.company,
)
```

Verified `addons/base/models/res_company.py` 14.0: `_company_default_get`
is DEPRECATED ("The method '_company_default_get' on res.company is
deprecated and shouldn't be used anymore"). The v12 idiom
`_company_default_get('my.model')` still runs in 14 but logs a warning —
use `lambda s: s.env.company` instead.

## 7. `company_dependent=True` fields

`company_dependent=True` still stores per-company values via `ir.property`
and reads back the value for `self.env.company`. Delta vs v12: scope writes
with `with_company(rec.company_id)`, **not** the dead
`with_context(force_company=...)`.

```python
property_account_payable_id = fields.Many2one(
    'account.account', company_dependent=True, string='Account Payable',
)
# write under the right company:
rec.with_company(rec.company_id).property_account_payable_id = acct
```

## 8. `mail.template` company resolution

```python
template.with_company(rec.company_id).send_mail(rec.id, force_send=True)
```

`with_company()` propagates into `ir.mail_server` selection and From/footer
resolution. Pitfall: chaining `with_company` AFTER `send_mail` does nothing
— it must precede the call. (Same as v17 — see odoo-17-multicompany.md §6.)

## 9. Tests for multi-company in v14

`SavepointCase` and `TransactionCase` BOTH exist in 14 (verified
`odoo/tests/common.py` 14.0). `SavepointCase` is NOT yet merged into
`TransactionCase` — that consolidation is 17+. Use `SavepointCase` for
shared class fixtures.

```python
from odoo.tests.common import SavepointCase

class TestMultiCompany(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'A'})
        cls.company_b = cls.env['res.company'].create({'name': 'B'})
        cls.multi_user = cls.env['res.users'].create({
            'name': 'Multi-User', 'login': 'multi14@test',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
        })

    def test_cross_company_create(self):
        rec = self.env['my.model'].with_company(self.company_b).create({
            'name': 'X', 'company_id': self.company_b.id,
        })
        self.assertEqual(rec.company_id, self.company_b)
```

**Delta vs v17**: the `self.env(company=...)` constructor kwarg does NOT
exist in 14 — verified `odoo/api.py` 14.0 `Environment.__call__(cr, user,
context, su)` takes no `company`. Switch companies in 14 tests via
`.with_company(...)`, not `env(company=...)`.

## 10. Currency rate lookup in v14

`res.currency._convert(from_amount, to_currency, company, date, round=True)`
— verified identical signature to v17 (`addons/base/models/res_currency.py`
14.0). The `company` arg selects which company's `res.currency.rate` rows
are consulted. See `references/odoo-multi-currency.md`.

## 11. v14-specific hard rules

- **Never `with_context(force_company=...)`** — dead in 14, only warns.
  Use `with_company(company)`.
- **Never `_company_default_get`** for new code — deprecated in 14. Use
  `default=lambda s: s.env.company`.
- `self.env.company` (env-level) over `self.env.user.company_id` for new code.
- `_check_company_auto = True` + `check_company=True` supersedes hand-rolled
  company checks.
- `ir.rule` domains reference the `company_ids` placeholder.
- In tests, switch company with `.with_company()` — the `env(company=...)`
  kwarg is 17+, not in 14.
- No `@api.multi` — removed in 13; do not decorate multi-company helpers.
