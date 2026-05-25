# Odoo 17 — multi-company specifics (mature `with_company` API)

Load this when Step 0 detected major = **17** (or **16** transitional
with a LOW flag, or **18/19/20** until a dedicated delta is written —
`<see Odoo 18+ multi-company guide>` to confirm no new semantics).

The `with_company()` chain was introduced in **Odoo 14** and matured in
**Odoo 15-17**. It supersedes the old `with_context(force_company=...)`
pattern. Both technically still work in 17, but `with_company()` is the
canonical form, and the `force_company` context key is on a deprecation
trajectory.

## 1. `with_company()` — what it actually does

`recordset.with_company(company)` returns a new recordset whose
`env.company` is the passed company. It propagates to:

- Default value resolution (`default=lambda s: s.env.company`).
- `company_dependent=True` field reads / writes.
- Currency rate lookups (`res.currency._convert(...)`).
- `mail.template.send_mail()` outgoing-server resolution.
- `_check_company_auto = True` cross-record consistency checks.

Argument can be `res.company` record or `int` (id).

```python
# v17 — canonical
invoice = self.env['account.move'].with_company(order.company_id).create({
    'company_id': order.company_id.id,
    'partner_id': order.partner_id.id,
    'invoice_line_ids': [(0, 0, line) for line in lines],
})
```

The `company_id` in `vals` is STILL required — `with_company()` only
shifts defaults / lookups, not the final stored value. Both are needed.

## 2. `self.env.company` vs `self.env.user.company_id`

In 17+:

- `self.env.company` — the *currently active* company on the env, set
  either by `with_company()` chain or by the user's switcher.
- `self.env.companies` — the set of allowed companies (replaces v12
  `user.company_ids` in many code paths; `user.company_ids` still
  exists).
- `self.env.user.company_id` — same as v12 (request-scoped switcher
  state).

**Rule of thumb**: in v17 code, use `self.env.company` (set explicitly
via `with_company`) instead of `self.env.user.company_id`. The latter
is still valid but reads less clearly.

## 3. `_check_company_auto = True`

Class attribute introduced in v13+, fully mature in 17. When set:

```python
class MyModel(models.Model):
    _name = 'my.model'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True)
    partner_id = fields.Many2one('res.partner', check_company=True)
```

The `check_company=True` flag on a `Many2one` auto-validates on
create / write: the target record's `company_id` must be compatible
with the parent's `company_id` (same company OR target is a
multi-company / no-company shared record).

Verification (`<see Odoo 17 _check_company implementation>`): the auto
check fires from `_inverse_field` / `write` hooks. If a related record
is from another company AND has a non-False `company_id`, raises
`UserError("Some records are incompatible with the company of the
record.")`.

Use this instead of writing manual `if rec.partner_id.company_id != rec.company_id: raise ...` checks.

## 4. `ir.rule` for v17 — `company_ids` placeholder unchanged

```xml
<record id="my_model_company_rule" model="ir.rule">
    <field name="name">my.model: multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">
        ['|',('company_id','=',False),('company_id','in',company_ids)]
    </field>
</record>
```

Identical to v12 syntax. The `company_ids` placeholder in the domain
expression still auto-expands to the user's allowed companies at rule
evaluation time.

New in v17: the `domain_force` evaluator supports the additional
placeholder `companies` (matching `self.env.companies`). Prefer
`company_ids` for backwards-compat unless the project has standardized
on `companies`.

## 5. Default company in v17

```python
class MyModel(models.Model):
    _name = 'my.model'

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda s: s.env.company,
    )
```

Cleaner than v12's `_company_default_get('my.model')` helper. The
helper still exists for backwards-compat but is no longer needed for
new code.

## 6. `mail.template.send_mail()` in v17

```python
# v17 — canonical
template.with_company(rec.company_id).send_mail(rec.id, force_send=True)
```

The `with_company()` chain propagates into:

- `ir.mail_server` selection (the company's outgoing SMTP).
- "From" address resolution (`company.email` or the user's email per
  company config).
- The signature footer (`mail.template`'s placeholders like
  `${object.company_id.name}` resolve via the chained company).

Pitfall: chaining `with_company` *after* `send_mail` does nothing —
the call must be `template.with_company(...).send_mail(...)`, not
`template.send_mail(...).with_company(...)`.

## 7. Tests for multi-company in v17

`TransactionCase` is the modern equivalent of v12's `SavepointCase` —
savepoint isolation is now built in.

```python
from odoo.tests.common import TransactionCase

class TestMultiCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'A'})
        cls.company_b = cls.env['res.company'].create({'name': 'B'})
        cls.multi_user = cls.env['res.users'].create({
            'name': 'Multi-User',
            'login': 'multi17@test',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
        })

    def test_cross_company_create(self):
        env_a = self.env(user=self.multi_user, company=self.company_a)
        rec = env_a['my.model'].with_company(self.company_b).create({
            'name': 'X',
            'company_id': self.company_b.id,
        })
        self.assertEqual(rec.company_id, self.company_b)
```

The `self.env(...)` constructor accepts a `company=` kwarg directly in
v17+ (more readable than chaining `.with_company()` everywhere).

## 8. Currency rate lookup in v17

`res.currency._convert(from_amount, to_currency, company, date,
round=True)` — the `company` argument controls which company's
`res.currency.rate` rows are consulted. Rates are stored per-company
on the `res.currency.rate` model directly (no `ir.property` indirection
like v12).

```python
# v17 — convert across companies
amount_target = src_currency._convert(
    amount, target_currency, rec.company_id, fields.Date.today(),
)
```

See `references/odoo-multi-currency.md` for cross-company FX rate
selection rules.

## 9. v17-specific hard rules

- Prefer `with_company(rec.company_id)` over
  `with_context(force_company=rec.company_id.id)` — the latter is
  legacy and slated for removal (`<see Odoo 18+ deprecation status>`).
- `_check_company_auto = True` + `check_company=True` on `Many2one`
  fields supersedes hand-rolled company-consistency checks.
- `default=lambda s: s.env.company` is canonical; `_company_default_get`
  is legacy.
- `self.env.company` (env-level) over `self.env.user.company_id`
  (user-level switcher state) for new code.
- `mail.template`/`mail.thread` must be company-chained BEFORE the
  send / post call.
