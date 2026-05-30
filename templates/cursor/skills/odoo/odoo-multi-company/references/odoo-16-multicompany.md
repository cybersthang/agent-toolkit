# Odoo 16 — multi-company specifics (neighbour = v17)

> odoo-16 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load this when Step 0 detected major = **16**. The multi-company API
(`with_company()`, `_check_company_auto`, `check_company=True`,
`self.env.company` / `self.env.companies`) was introduced in v13/v14 and
is fully mature by 16 — so **almost everything cascades unchanged from
v17**. Read `odoo-17-multicompany.md` as the base; this file only flags
the few 16-specific points and the one display-layer divergence.

## What is UNCHANGED from v17

The following are identical in 16 — see `odoo-17-multicompany.md` for the
full treatment (verified against Odoo 16 "Multi-company Guidelines",
/documentation/16.0/developer/howtos/company.html):

- **§1 `with_company(company_or_id)`** — same propagation (defaults,
  `company_dependent` reads/writes, currency rate lookup, mail server,
  `_check_company_auto`). `company_id` in `vals` still required.
- **§2 `self.env.company` vs `self.env.companies` vs
  `self.env.user.company_id`** — same semantics; prefer `self.env.company`.
- **§3 `_check_company_auto = True` + `check_company=True`** on
  `Many2one` — same auto-validation on create/write (raises *"Some
  records are incompatible with the company of the record."*; read the
  exact phrasing off the 16.0 branch when it is load-bearing).
- **§4 `ir.rule` `company_ids` placeholder** — same domain form;
  `companies` placeholder also available.
- **§5 `default=lambda s: s.env.company`** — canonical; legacy
  `_company_default_get` still present but unneeded.
- **§6 `mail.template.send_mail()`** — chain `with_company` BEFORE the
  send call.
- **§7 Tests** — `TransactionCase` with savepoint isolation;
  `self.env(user=..., company=...)` constructor kwarg works.
- **§8 Currency `_convert(from_amount, to_currency, company, date,
  round=True)`** — per-company `res.currency.rate` rows, no
  `ir.property` indirection.

## 16-specific notes / DELTAS vs 17

### `with_company()` is the canonical switch in 16

`with_context(force_company=...)` is the legacy v12-era form;
`with_company()` is canonical in 16, exactly as in v17. No 16-specific
change here — listed for completeness.

### Cross-company display labels still go through `name_get()`

When a multi-company widget or report shows a company-qualified label
(e.g. `[COMP-A] Partner`), the **16.0** override point is **`name_get()`**,
not `_compute_display_name` (the v17 form). `name_get` is deprecated from
saas-16.4 (PR #122085) and removed in 17.0, so on a 16.4+ SaaS target
prefer `_compute_display_name`. This is the one place a multi-company
customization diverges from the v17 reference.

```python
# v16 — company-qualified label override
def name_get(self):
    result = []
    for rec in self:
        prefix = rec.company_id.name if rec.company_id else ''
        result.append((rec.id, f"[{prefix}] {rec.name}" if prefix else rec.name))
    return result
```

### `ir.rule` view-side: 16 uses `attrs`, not inline expr

Multi-company *views* that toggle a `company_id` field's visibility use
`attrs="{...}"` in 16 (inline `invisible="<expr>"` is v17+). This is a
view-layer concern, not an ORM one — see
`odoo-code-patterns/references/odoo-16-patterns.md` §View.

### company-dependent fields + JSONB translations

In 16, translated fields are stored as JSONB (verified: odoo/odoo
#97692/#101115). This is orthogonal to `company_dependent` storage
(which uses `ir.property`-style per-company values) — do not conflate
the two when auditing a multi-company + translated field.

## 16-specific hard rules

- `with_company(rec.company_id)` over `with_context(force_company=...)`
  — same as v17.
- `_check_company_auto = True` + `check_company=True` supersedes
  hand-rolled company-consistency checks — same as v17.
- `default=lambda s: s.env.company` is canonical — same as v17.
- `self.env.company` over `self.env.user.company_id` for new code —
  same as v17.
- For a company-qualified DISPLAY label, override **`name_get()`** on
  16.0 (or `_compute_display_name` on 16.4+ SaaS / 17). This is the only
  16 divergence from the v17 multi-company patterns.

See `references/odoo-multi-currency.md` for cross-company FX rate
selection rules (version-agnostic).
