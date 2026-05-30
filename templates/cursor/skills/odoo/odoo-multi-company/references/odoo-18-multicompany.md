# Odoo 18 — multi-company specifics (neighbour = v17)

> odoo-18 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load this when Step 0 detected major = **18**. The multi-company API
(`with_company()`, `_check_company_auto`, `check_company=True`,
`self.env.company` / `self.env.companies`, `company_dependent=True`) was
introduced in v13/v14 and is fully mature by 17 — so **almost everything
cascades unchanged from v17**. Read `odoo-17-multicompany.md` as the
base; this file flags only the 18-specific points: the ORM signature
renames that touch multi-company call sites, the documented
`check_company` rules, and the `name_get` → display-name removal.

## What is UNCHANGED from v17

The following are identical in 18 — see `odoo-17-multicompany.md` for the
full treatment (verified against the Odoo 18 "Multi-company Guidelines",
/documentation/18.0/developer/howtos/company.html):

- **§1 `with_company(company_or_id)`** — same propagation (defaults,
  `company_dependent` reads/writes, currency rate lookup, mail server,
  `_check_company_auto`). `company_id` in `vals` still required. The 18
  guidelines restate the contract explicitly:
  `record.with_company(company_B).env.company == company_B`.
- **§2 `self.env.company` vs `self.env.companies` vs
  `self.env.user.company_id`** — same semantics; prefer `self.env.company`.
- **§3 `_check_company_auto = True` + `check_company=True`** on
  relational `Many2one` fields — same auto-validation on create/write
  (raises *"Some records are incompatible with the company of the
  record."*; read the exact phrasing off the 18.0 branch when it is
  load-bearing).
- **§4 `ir.rule` `company_ids` placeholder** — same domain form;
  `companies` placeholder also available.
- **§5 `default=lambda s: s.env.company`** — canonical (the 18 docs spell
  this out as the required pattern on a `required=True` `company_id`).
- **§6 `mail.template.send_mail()`** — chain `with_company` BEFORE the
  send call.
- **§7 Tests** — `TransactionCase` with savepoint isolation;
  `self.env(user=..., company=...)` constructor kwarg works.
- **§8 Currency `_convert(from_amount, to_currency, company, date,
  round=True)`** — per-company `res.currency.rate` rows, no
  `ir.property` indirection.

## 18-specific notes / DELTAS vs 17

These are framework-wide ORM/signature changes (verified against the
Odoo 18.0 ORM changelog, /documentation/18.0/developer/reference/backend/orm/changelog.html)
that surface inside multi-company code paths — not new multi-company
semantics per se. The multi-company *model* is unchanged from v17.

### `company_id` field must NOT carry `check_company=True`

The 18 guidelines state this explicitly: *"The field `company_id` must
not be defined with `check_company=True`."* `check_company=True` belongs
on the OTHER relational fields (the ones pointing at company-scoped
targets), where it adds the default domain
`['|', ('company_id', '=', False), ('company_id', '=', company_id)]`
restricting the target to the record's own company (or a no-company
shared record). This is documented as v17 behaviour too, but the 18 docs
are the first to phrase the `company_id`-itself prohibition as a hard
rule — call it out in an 18 audit.

```python
# v18 — canonical company-scoped model
class MyModel(models.Model):
    _name = 'my.model'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env.company,
    )                                       # NO check_company=True here
    partner_id = fields.Many2one('res.partner', check_company=True)
```

### `company_dependent=True` computes need `@api.depends_context('company')`

The 18 docs make this explicit: a computed field that reads a
`company_dependent` field must declare `@api.depends_context('company')`
so it recomputes when the active company changes. Without it the cache
returns a stale per-company value after a `with_company()` switch.

```python
# v18 — company-context-aware compute
margin = fields.Float(compute='_compute_margin')

@api.depends('amount')
@api.depends_context('company')
def _compute_margin(self):
    for rec in self:
        rec.margin = rec.amount - rec.standard_price  # standard_price is company_dependent
```

This decorator exists in v17 as well; the 18 guidelines elevate it to a
documented requirement for company-dependent computes — flag a missing
`@api.depends_context('company')` on such a compute in an 18 audit.

### ORM signature renames at multi-company call sites

Verified against the Odoo 18.0 ORM changelog:

- **`search()` / `search_count()` / `_search()`: `args=` → `domain=`**.
  An `ir.rule`-adjacent `search(args=[('company_id','in',...)])` in 18
  code should be `search(domain=[...])`. Positional form is unchanged; no
  behaviour delta — flag the keyword only if the code passes `args=` by
  name.
- **`check_access_rights()` + `check_access_rule()` → unified
  `check_access(operation)`** (#179148; sibling helpers `has_access`,
  `_filtered_access`). Multi-company ACL guards that hand-rolled the two
  legacy calls collapse to one in 18. The cross-company access decision
  is unchanged in semantics; only the call shape changed.

### `name_get()` removed — company-qualified labels move to display_name

This is the one place an 18 multi-company *customization* diverges from
the v17 reference. `name_get()` was deprecated in saas-16.4 (#122085) and
search-by-name is now `_search_display_name` (#174967); on 18.0 the
company-qualified label override goes through `_compute_display_name`,
not `name_get()`.

```python
# v18 — company-qualified label override (replaces v16 name_get form)
@api.depends('name', 'company_id')
def _compute_display_name(self):
    for rec in self:
        prefix = rec.company_id.name if rec.company_id else ''
        rec.display_name = f"[{prefix}] {rec.name}" if prefix else rec.name
```

A v16-style `name_get()` override carried into an 18 module is a
migration bug (the label silently won't apply), not just a style nit.

## 18-specific hard rules

- `with_company(rec.company_id)` over `with_context(force_company=...)`
  — same as v17.
- `_check_company_auto = True` + `check_company=True` supersedes
  hand-rolled company-consistency checks — same as v17; but NEVER put
  `check_company=True` on `company_id` itself (18 docs hard rule).
- `default=lambda self: self.env.company` on a `required=True`
  `company_id` — documented requirement in 18.
- A `company_dependent`-reading compute MUST carry
  `@api.depends_context('company')`.
- `self.env.company` over `self.env.user.company_id` for new code —
  same as v17.
- Company-qualified DISPLAY labels go through `_compute_display_name`;
  a `name_get()` override is a migration bug on 18.
- `search(domain=...)` keyword and unified `check_access(...)` are the
  18 forms — flag legacy `args=` / `check_access_rights()+rule()` at
  multi-company call sites as migration cleanup, not behaviour bugs.

See `references/odoo-multi-currency.md` for cross-company FX rate
selection rules (version-agnostic).
