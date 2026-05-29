# Odoo 13 — multi-company specifics (env.company arrives, no `with_company` yet)

> odoo-13 reference (drafted v0.29). Deltas vs odoo-12-multicompany.md web-verified where cited; `<!-- VERIFY -->` items need DEV confirmation.

Standalone reference: 13 does NOT cascade from 17. Load when Step 0
detected major = **13**.

Odoo 13 is the **transition release** for multi-company: it introduced
the modern environment-level company (`self.env.company`,
`self.env.companies`, the `allowed_company_ids` context) and the
`_check_company_auto` consistency mechanism — but it does NOT yet have
`with_company()` (that arrived in **v14**). So 13 sits between v12 and
v17: use `self.env.company` for defaults/reads, but switch company for
cross-company ops with the `force_company` **context key**, not a
`with_company()` chain.

Verified against `odoo/odoo` 13.0 `odoo/api.py`,
`addons/base/models/res_company.py`, `odoo/models.py`, and the official
[Odoo 13.0 Multi-company Guidelines](https://www.odoo.com/documentation/13.0/howtos/company.html).

## 1. `self.env.company` / `self.env.companies` — NEW in 13

```python
# v13 — env-level active company (NOT in v12)
company = self.env.company             # the active company
allowed = self.env.companies           # recordset of allowed companies
```

- `self.env.company` reads from the `allowed_company_ids` context key
  (first allowed company / the switcher selection). Source: 13.0
  `odoo/api.py` `company`/`companies` properties (~line 528 / 558).
- `allowed_company_ids` is the 13 multi-company switcher mechanism — a
  user can be logged into **multiple companies at once** (new in 13).
- `self.env.user.company_id` still exists (request-scoped switcher
  state) but prefer `self.env.company` in new 13 code.

Pitfall: in cron / batch jobs `allowed_company_ids` is usually empty, so
`self.env.company` falls back to the user's default. Set company
explicitly per record in batch loops (see §5).

## 2. Default company on a Many2one — use `self.env.company`

```python
# v13 — canonical default (verified: official 13.0 multi-company guide)
class MyModel(models.Model):
    _name = 'my.model'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
```

DELTA vs v12: `_company_default_get('<model>')` is **DEPRECATED in 13**
(verified: 13.0 `res_company.py` line ~205 emits *"The method
'_company_default_get' on res.company is deprecated and shouldn't be
used anymore"*). Replace it with `lambda self: self.env.company`.

## 3. `_check_company_auto` + `check_company=True` — NEW in 13

```python
# v13 — auto cross-company consistency (NOT in v12)
class MyModel(models.Model):
    _name = 'my.model'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True)
    partner_id = fields.Many2one('res.partner', check_company=True)
```

- `_check_company_auto = True` makes create/write call `_check_company()`
  (verified: 13.0 `odoo/models.py` `_check_company` ~line 3187, invoked
  ~3668 / 3864).
- `check_company=True` on a `Many2one` enforces that the target record's
  `company_id` is compatible (same company, or shared/no-company).
- Use this instead of hand-rolled
  `if rec.partner_id.company_id != rec.company_id: raise ...`.

When the exact `UserError` wording matters in an audit, read
`_check_company` on the 13.0 branch directly — phrasing differs across
majors.

## 4. `company_dependent=True` fields + `force_company` context

`company_dependent=True` still stores per-company values in
`ir.property` (unchanged storage from v12). To **read/write** the value
for a company other than the active one, use the `force_company` context
key — `with_company()` does NOT exist in 13 (verified: absent from 13.0
`odoo/models.py`; `force_company` honoured at ~line 3235).

```python
# v13 — read a company-dependent field for another company
val = record.with_context(force_company=company_b.id).property_account_payable_id

# v13 — compute that varies by company MUST depend on the context key
@api.depends_context('force_company')
def _compute_x(self):
    for rec in self:
        rec.x = rec.with_context(force_company=rec.company_id.id).some_company_dep_field
```

DELTA vs v12: `@api.depends_context(...)` is available in 13 (verified:
13.0 `odoo/api.py` ~line 209) — use it so company-dependent computes
recompute when `force_company` / the active company changes. (v12 had no
`depends_context`.)

## 5. `ir.rule` for multi-company — `company_ids` placeholder

```xml
<record id="my_model_company_rule" model="ir.rule">
    <field name="name">my.model: multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">
        ['|',('company_id','=',False),('company_id','in',company_ids)]
    </field>
</record>
```

Unchanged from v12 — the `company_ids` placeholder auto-expands to the
user's allowed companies at rule-eval time. Drop the
`('company_id','=',False)` arm for strictly-per-company models.

## 6. `mail.template` / `mail.thread` company resolution in 13

`mail.template.send_mail()` resolves the outgoing `ir.mail_server` from
the active company / `force_company` context — there is NO
`with_company()` chain in 13. Wrap cron/batch dispatch:

```python
def _cron_send(self):
    for rec in self.env['my.model'].search([]):
        template.with_context(
            force_company=rec.company_id.id,
        ).send_mail(rec.id, force_send=True)
```

## 7. Tests for multi-company in 13

`SavepointCase` is available in 13 (verified: 13.0
`odoo/tests/common.py`). Standard 2-company fixture:

```python
from odoo.tests.common import SavepointCase

class TestMultiCompany(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})
        cls.multi_user = cls.env['res.users'].create({
            'name': 'Multi-User',
            'login': 'multi13@test',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
        })

    def test_active_company(self):
        # v13: switch the active company via allowed_company_ids context
        env_b = self.env(user=self.multi_user)
        rec = env_b['my.model'].with_context(
            allowed_company_ids=self.company_b.ids,
        ).create({'name': 'X', 'company_id': self.company_b.id})
        self.assertEqual(rec.company_id, self.company_b)
```

DELTA vs v12: no `@api.multi` on helper methods (removed in 13). Switch
the active company in tests via the `allowed_company_ids` context.
There is NO `company=` kwarg on the `self.env(...)` constructor in 13 —
13.0 `odoo/api.py` (line ~485) defines
`Environment.__call__(self, cr=None, user=None, context=None, su=None)`
(and `__new__(cls, cr, uid, context, su=False)`), neither of which
accepts `company`. The active company is derived from the
`allowed_company_ids` context key, so set it with
`.with_context(allowed_company_ids=company.ids)` (as in the example
above), never `self.env(company=...)`. (The `company=` env kwarg used in
some 14+/17 examples does not exist in 13.)

## 8. Currency rate lookup in 13

`res.currency._convert(from_amount, to_currency, company, date,
round=True)` exists in 13; the `company` argument controls which
company's rate rows are consulted. Read `addons/base/models/res_currency.py`
on the 13.0 branch when an audit hinges on the exact signature. See
`references/odoo-multi-currency.md`.

## 9. v13-specific hard rules

- Use `default=lambda self: self.env.company` — `_company_default_get`
  is **deprecated** in 13.
- Use `self.env.company` (env-level) over `self.env.user.company_id`.
- Switch company for cross-company ops with
  `with_context(force_company=...)` — `with_company()` does NOT exist in
  13 (v14+). Calling it raises `AttributeError`.
- Company-dependent computes MUST use
  `@api.depends_context('force_company')`.
- Prefer `_check_company_auto = True` + `check_company=True` over manual
  company-consistency checks.
- `ir.rule` domains reference `company_ids` (plural placeholder), never
  `user.company_id.id` (singular, request-scoped).
- No `@api.multi` on multi-company helper methods — removed in 13.
