# Odoo 15 — multi-company specifics (`with_company` era)

> odoo-15 reference (drafted v0.29). Deltas vs odoo-12 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Standalone reference: load this when Step 0 detected major = **15**.

CRITICAL DELTA vs v12: the v12 multi-company model (`force_company`-only,
`_company_default_get`, `env.user.company_id`) was OVERHAULED in v13–14.
v15 has the **modern API** — `self.env.company`, `with_company()`,
`_check_company_auto` — and matches v17 far more than v12 here. Most of
odoo-12-multicompany.md is WRONG for v15; the deltas below replace it.

## 1. `self.env.company` replaces the v12 `force_company` pattern

In Odoo 13+ a user can be logged into multiple companies at once. The
company-switch widget no longer flips `res.users.company_id`; the active
company is read via `self.env.company` and the allowed set via
`self.env.companies` (web-verified, 13.0/14.0 multi-company guidelines).

```python
# v15 — active company / allowed companies
active = self.env.company           # singleton res.company (replaces v12 env.user.company_id idiom)
allowed = self.env.companies        # recordset of allowed companies
```

DELTA: in v12 you read `self.env.user.company_id`; in v15 use
`self.env.company`. Web-verified.

## 2. `with_company()` is the cross-company switch (v14+)

```python
# v15 — switch company context for an ORM op
invoice = self.env['account.move'].with_company(order.company_id).create({
    'company_id': order.company_id.id,
    'partner_id': order.partner_id.id,
})
```

DELTA vs v12: replace `with_context(force_company=<id>)` with
`with_company(<company_record_or_id>)` (introduced v14, web-verified).
The v12 `force_company` context key STILL works in v13–15 for backward
compat, but `with_company()` is the idiom from v14 onward — flag bare
`force_company` in new v15 code as outdated.
As in v12, the `company_id` in `vals` is still required separately —
`with_company()` only affects defaults/lookups, not the stored value.

## 3. Default company on a Many2one — `env.company`, not `_company_default_get`

```python
# v15 — canonical default-company
class MyModel(models.Model):
    _name = 'my.model'

    company_id = fields.Many2one(
        'res.company',
        default=lambda s: s.env.company,
    )
```

DELTA vs v12: the v12 `_company_default_get('<model>')` helper is the old
API. In v15 use `default=lambda s: s.env.company`.

NOTE: `_company_default_get` is **NOT removed in 15.0 — it is deprecated
but still callable**. In `addons/base/models/res_company.py` (odoo/odoo
15.0) it is defined as a thin `@api.model` shim that logs a deprecation
warning and returns `self.env.company`:
`_logger.warning("The method '_company_default_get' ... is deprecated ...")`.
So old code calling it won't crash, but new v15 code MUST use
`default=lambda s: s.env.company`.

## 4. `_check_company_auto` — automatic company-consistency check (NEW vs v12)

```python
class MyModel(models.Model):
    _name = 'my.model'
    _check_company_auto = True

    company_id = fields.Many2one('res.company')
    partner_id = fields.Many2one('res.partner', check_company=True)
```

DELTA vs v12: setting `_check_company_auto = True` makes the ORM validate,
on create/write, that every relational field flagged `check_company=True`
points at a record in the same company. This mechanism does NOT exist in
v12 (web-verified: documented from 13.0 multi-company guidelines onward).
Mismatches raise a `UserError` automatically — no manual cross-company
guard needed.

## 5. `company_dependent=True` fields

Still `ir.property`-backed in v15, but the read/write company is resolved
via `self.env.company` (and `with_company()` to target another company)
rather than the v12 `force_company` context. The v12 pitfall ("writes go
to the active company's property") is fixed by wrapping in
`with_company(rec.company_id)` instead of `with_context(force_company=...)`.

## 6. `ir.rule` multi-company domain

```xml
<record id="my_model_company_rule" model="ir.rule">
    <field name="name">my.model: multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">
        ['|',('company_id','=',False),('company_id','in',company_ids)]
    </field>
</record>
```

The `company_ids` placeholder in `ir.rule` domains resolves to the user's
allowed companies — unchanged structurally from v12 (see
odoo-12-multicompany.md §2). The `('company_id','=',False)` arm shares
no-company records; drop it for strictly per-company models.

## 7. Tests for multi-company in v15

```python
from odoo.tests.common import TransactionCase   # or SavepointCase (both exist in v15)

class TestMultiCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})
        cls.multi_user = cls.env['res.users'].create({
            'name': 'Multi-User',
            'login': 'multi@test',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
        })
```

DELTA vs v12: NO `@api.multi` on helper methods (removed v13). Both
`SavepointCase` and `TransactionCase` exist in v15 (they merge in v16/v17,
web-verified). See odoo-15-tdd-pitfalls.md.

## 8. v15-specific hard rules

- Use `self.env.company` (active) / `self.env.companies` (allowed) — NOT
  the v12 `self.env.user.company_id`.
- Use `with_company(<company>)` for cross-company ops — NOT the v12
  `with_context(force_company=...)` (still works but outdated).
- Use `default=lambda s: s.env.company` — NOT `_company_default_get(...)`.
- Set `_check_company_auto = True` + `check_company=True` on relational
  fields to get automatic consistency validation (new vs v12).
- `ir.rule` domains reference `company_ids` (plural) — unchanged from v12.
- No `@api.multi` anywhere — removed in v13.
