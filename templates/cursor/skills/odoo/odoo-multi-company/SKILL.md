---
name: odoo-multi-company
description: Odoo multi-company anti-patterns — missing `with_company()` context, currency rounding mismatch across companies, `ir.rule` per-company gaps, multi-company SQL constraints, mail/notification routing wrong company. Version-aware: Step 0 detects the addon's Odoo version from `__manifest__.py`, then loads the matching `references/odoo-<N>-multicompany.md` (v12 pre-`with_company` era; v13-16 dedicated packs; v17 mature `with_company` API). Cross-company currency conversion patterns in `references/odoo-multi-currency.md`. Audience: Odoo consultancies using Enterprise multi-company. Open whenever the user says "multi-company", "đa công ty", "company context", "cross-company", `with_company`, `company_id` issues, or when a code-review finding flags missing company guards.
---

# Odoo — Multi-Company Anti-Patterns (version-aware)

Multi-company bugs are the silent class: code works in single-company
dev / staging, then leaks data, miscomputes totals, or sends mail from
the wrong sender in production where 2+ companies are active.

This skill enumerates the **top 5 anti-patterns** every Odoo consultancy
hits on Enterprise multi-company deployments, with falsification
recipes (how to deterministically reproduce the bug) and invariant
suggestions (`must_keep_regex` patterns the `invariant_guard` hook can
auto-enforce).

> Module-agnostic: never hard-codes model names from a specific project.
> Discover the target model with `codebase.search_model_definitions`
> before pattern-matching.

Pair with `odoo-code-review` (severity anchors for multi-company
findings) and `odoo-data-verification` (live ORM probes against real
multi-company data).

## 0. Version detection (MANDATORY first step)

Same protocol as `odoo-code-review` / `odoo-code-patterns`:

1. **`__manifest__.py` `version` field** — `codebase.read_manifest({module_path})`.
   Pattern `^(\d+)\.0\.`.
2. **Fallback signals** (only if manifest missing):
   - `@api.multi` decorator → ≤13 (treat as 12 in our scope).
   - `with_company()` ORM call anywhere in the addon → ≥14.
   - `_check_company_auto = True` class attribute → **mainstream from 16+**
     (introduced earlier as opt-in around 13 partial / 14, but typical
     v13-15 code does NOT set it; default-True only became standard in 16).
   - `@api.model_create_multi` decorator → ≥14.
3. **Ask the user** only if signals are inconclusive.

Then load the matching reference:

| Detected major | Reference (multi-company specifics) |
|---|---|
| 12 | `references/odoo-12-multicompany.md` (pre-`with_company` era) |
| 13 | load `references/odoo-13-multicompany.md` |
| 14 | load `references/odoo-14-multicompany.md` |
| 15 | load `references/odoo-15-multicompany.md` |
| 16 | load `references/odoo-16-multicompany.md` (+ note: backports some v17 conventions) |
| 17 | `references/odoo-17-multicompany.md` |
| 18 / 19 / 20 | apply `odoo-17-multicompany.md` (no dedicated delta written yet — re-check the target major's multi-company release notes before relying on this for an audit) + flag LOW |

Currency conversion is **not version-locked** — always load
`references/odoo-multi-currency.md` regardless of detected version.

## 1. Pattern A — Missing `with_company()` when creating records

**Confidence: H**

### Problem

Records created without an explicit company context fall back to
`self.env.company` (the user's *current* company), not the company the
business object logically belongs to. In multi-company workflows where
a user has access to N companies, `self.env.company` reflects the
**last switcher click**, which is fragile, racy, and silently
cross-pollinates data.

### Bad

```python
# v17 — silently picks self.env.company, may NOT be the order's company
def _create_invoice(self, order):
    return self.env['account.move'].create({
        'partner_id': order.partner_id.id,
        'invoice_line_ids': [(0, 0, line) for line in self._build_lines(order)],
    })
```

### Good

```python
# v17 — explicit company context = the order's company
def _create_invoice(self, order):
    return self.env['account.move'].with_company(order.company_id).create({
        'company_id': order.company_id.id,
        'partner_id': order.partner_id.id,
        'invoice_line_ids': [(0, 0, line) for line in self._build_lines(order)],
    })
```

```python
# v12 — pre-with_company API; force context manually
def _create_invoice(self, order):
    return self.env['account.invoice'].with_context(
        force_company=order.company_id.id,
        company_id=order.company_id.id,
    ).create({
        'company_id': order.company_id.id,
        'partner_id': order.partner_id.id,
        # ...
    })
```

### Falsification recipe

1. Create 2 companies (`Company A`, `Company B`) sharing a parent user.
2. Switch the user's `env.company` to `Company A`.
3. Trigger the code path that creates a record logically belonging to
   `Company B` (e.g. order placed under Company B).
4. Assert the created record's `company_id` equals `Company B`.
5. If the assertion fails — the code is leaking `env.company` instead
   of using the source record's company.

```python
# realdata_test MCP eval — generic skeleton
order = self.env['sale.order'].search([('company_id','=', company_b.id)], limit=1)
self.env = self.env(user=multi_co_user, company=company_a)  # switcher mismatch
invoice = order.action_create_invoice()
self.assertEqual(invoice.company_id, company_b,
                 "leaked env.company instead of using order.company_id")
```

### Invariant suggestion (auto-enforce)

Detect: `create({` calls on company-scoped models that don't appear
inside a `with_company(` chain on the same call.

```json
{
  "id": "multicompany-with-company-on-create",
  "description": "Creates on company-scoped models must go through with_company() (Odoo 14+).",
  "applies_to": ["**/models/*.py"],
  "rules": {
    "must_keep_regex": [
      "\\.with_company\\([^)]+\\)\\.create\\("
    ]
  },
  "severity": "warn",
  "rationale": "Without with_company(), env.company silently substitutes — see odoo-multi-company SKILL §1."
}
```

(Severity `warn` because not every `create()` is company-scoped — promote
to `blocker` only on a specific model path once verified.)

---

## 2. Pattern B — Currency rounding rules mismatch across companies

**Confidence: H**

### Problem

Each `res.company` has a `currency_id`, and each `res.currency` has its
own `rounding` and `decimal_places`. When code aggregates monetary
values across companies (consolidated reports, inter-company invoices,
cross-company reconciliation), using one currency's rounding for
another's amount produces off-by-one-cent drift that compounds over
thousands of rows.

The pitfall: developers cache `self.env.company.currency_id` once at
the top of a method, then apply that rounding to records belonging to
*other* companies.

### Bad

```python
# v17 — uses one currency's rounding for every record's amount
def _summarize(self, records):
    home_currency = self.env.company.currency_id
    total = 0.0
    for rec in records:
        total += home_currency.round(rec.amount)  # WRONG if rec.company_id differs
    return total
```

### Good

```python
# v17 — round each amount in its own currency first, then convert + sum
def _summarize(self, records, target_currency=None):
    target_currency = target_currency or self.env.company.currency_id
    total = 0.0
    today = fields.Date.context_today(self)
    for rec in records:
        src = rec.currency_id
        amount_rounded = src.round(rec.amount)
        if src == target_currency:
            total += amount_rounded
        else:
            total += src._convert(
                amount_rounded, target_currency, rec.company_id, today,
            )
    return target_currency.round(total)
```

### Falsification recipe

1. Create 2 companies with different currencies (`USD`, `JPY`) — JPY
   typically has `rounding=1.0`, USD `rounding=0.01`.
2. Create N records (e.g. 100) under Company-JPY with `amount=0.49`
   (will round to 0 in JPY, to 0.49 in USD).
3. Call the summarizer in the user's `env.company = USD` context.
4. Compare total to what should be — bug: ~49 USD reported; correct:
   ~0 USD (JPY rounds the per-record 0.49 to 0, sum is 0).
5. For exact per-currency rounding semantics, refer to
   `res.currency.round()` in `odoo/odoo` `odoo/addons/base/models/res_currency.py`
   on the branch matching the target Odoo version (rounding helper
   implementations drift between majors — read the version under audit).

### Invariant suggestion (auto-enforce)

Detect: monetary aggregations that use a single cached `currency_id`
across a loop over heterogeneous records.

```json
{
  "id": "multicompany-no-cached-currency-across-records",
  "description": "Monetary aggregations over multi-company records must use rec.currency_id, not env.company.currency_id captured outside the loop.",
  "applies_to": ["**/models/*.py", "**/report/*.py"],
  "rules": {
    "must_keep_regex": [
      "rec(?:ord)?\\.currency_id\\.(?:round|_convert)\\("
    ]
  },
  "severity": "warn",
  "rationale": "Cached env.company.currency_id applied to other companies' amounts produces silent rounding drift — see odoo-multi-company SKILL §2 + references/odoo-multi-currency.md."
}
```

---

## 3. Pattern C — `ir.rule` per-company gaps allowing cross-company leak

**Confidence: H**

### Problem

A new `models.Model` with `company_id = fields.Many2one('res.company')`
**does not automatically** get an `ir.rule` filtering by
`user.company_ids`. Without an explicit record rule, every user can
read / write rows from other companies regardless of the model's
`company_id` value. This is the most common multi-company security
finding in code review.

The matching pattern in standard modules (e.g. `sale_order_company_rule`):
domain `[('company_id', 'in', user.company_ids.ids)]`, applied to read
+ write + create + unlink, `global=True` (no group restriction).

### Bad

```xml
<!-- security/ir.model.access.csv only — no ir.rule -->
my_model_user_access,my.model.user,model_my_model,base.group_user,1,1,1,0
```

```python
# models/my_model.py — company_id declared but no rule registered
class MyModel(models.Model):
    _name = 'my.model'
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)
```

### Good

```xml
<!-- security/my_model_security.xml -->
<record id="my_model_company_rule" model="ir.rule">
    <field name="name">my.model: multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">[('company_id','in',company_ids)]</field>
    <field name="global" eval="True"/>
</record>
```

`company_ids` (plural) in the domain auto-expands to the user's allowed
companies — never hard-code `user.company_id.id` (singular) since that
breaks the "I'm switched to Company A but can still read Company B"
expected UX.

### Falsification recipe

1. Create 2 companies + 1 user with access to both.
2. Create one `my.model` record under each company.
3. Switch user's `env.company` to Company A.
4. Call `self.env['my.model'].search([])` — does it return both records
   or only Company A's?
5. Bug: returns both (or wrong one). Correct: returns both because the
   user has access to both companies — but if the user is restricted to
   only Company A, must return ONLY Company A's record.
6. Repeat with a single-company user: must return ONLY that user's company.

```python
# realdata_test MCP eval — generic skeleton
user_a_only = self.env['res.users'].search([('company_ids','=', company_a.id)], limit=1)
rec_b = self.env['my.model'].create({'name':'X','company_id': company_b.id})
visible = self.env['my.model'].with_user(user_a_only).search([])
self.assertNotIn(rec_b, visible, "Company B record leaked to a Company-A-only user")
```

### Invariant suggestion (auto-enforce)

Detect: new model files declaring `company_id` without a matching
`ir.rule` record nearby in `security/`.

```json
{
  "id": "multicompany-ir-rule-required-on-company-id",
  "description": "Models declaring company_id must have a matching ir.rule with domain on company_ids.",
  "applies_to": ["**/models/*.py"],
  "rules": {
    "must_keep_call": ["company_id"]
  },
  "severity": "warn",
  "rationale": "Without ir.rule, company_id is decorative — cross-company read/write is silently allowed. See odoo-multi-company SKILL §3."
}
```

(Note: this is a `warn` because the actual rule lives in XML; full
enforcement requires a sibling check on `security/*.xml`. Promote via
a project-specific custom probe — see `probe-add` skill.)

---

## 4. Pattern D — Multi-company SQL constraints (unique-per-company, not global)

**Confidence: H**

### Problem

`_sql_constraints` with `UNIQUE(column)` enforce a *global* uniqueness
that ignores the company boundary. In multi-company setups, the same
"natural key" (invoice number, internal reference, supplier code) is
legitimately reusable across companies — but a `UNIQUE(name)` constraint
blocks Company B from using a name already taken in Company A.

The fix is **always** `UNIQUE(company_id, <natural_key>)`, ensuring the
constraint is scoped to a single company.

### Bad

```python
# v17 — blocks reuse across companies
class MyModel(models.Model):
    _name = 'my.model'
    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True)

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'Name must be unique.'),
    ]
```

### Good

```python
# v17 — uniqueness scoped per-company
class MyModel(models.Model):
    _name = 'my.model'
    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True)

    _sql_constraints = [
        ('name_company_uniq',
         'UNIQUE(company_id, name)',
         'Name must be unique within a company.'),
    ]
```

For `_inherit` extending a base model that already has a global
`UNIQUE(...)`, dropping the original and re-declaring with the
company-scoped variant requires a migration (Odoo `migrations/<version>/pre-*.py`
hook pattern — see Odoo official docs "Module migration scripts"
and `OCA/openupgrade` examples) — never modify in-place without a
`pre-init` hook that drops the old constraint. When writing the
fix-sketch, ground the pre-init example in an actual migration script
from the project under audit (or an OCA reference) — generic snippets
hide the per-table constraint name.

### Falsification recipe

1. Create 2 companies.
2. Create `my.model` record `name='ABC'` under Company A.
3. Attempt to create `my.model` record `name='ABC'` under Company B.
4. Bug: raises `psycopg2.IntegrityError` on the global UNIQUE.
5. Correct: succeeds (per-company UNIQUE allows reuse).

```python
# realdata_test MCP eval — generic skeleton
self.env['my.model'].create({'name': 'ABC', 'company_id': company_a.id})
try:
    self.env['my.model'].create({'name': 'ABC', 'company_id': company_b.id})
    success = True
except Exception:
    success = False
self.assertTrue(success, "Global UNIQUE blocks legitimate cross-company reuse")
```

### Invariant suggestion (auto-enforce)

Detect: `_sql_constraints` entries on models with `company_id` that use
`UNIQUE(<col>)` without including `company_id`.

```json
{
  "id": "multicompany-sql-constraint-includes-company-id",
  "description": "UNIQUE _sql_constraints on company-scoped models must include company_id.",
  "applies_to": ["**/models/*.py"],
  "rules": {
    "must_keep_regex": [
      "UNIQUE\\s*\\(\\s*company_id\\s*,"
    ]
  },
  "severity": "warn",
  "rationale": "Global UNIQUE on a company-scoped model blocks legitimate cross-company reuse — see odoo-multi-company SKILL §4."
}
```

(`warn` because not every model has `company_id`. The hook would
need a sibling check to confirm — escalate to `blocker` once verified
in the project's invariant context.)

---

## 5. Pattern E — Mail / notification routing wrong company context

**Confidence: M**

### Problem

`mail.thread.message_post()` and `mail.template.send_mail()` resolve
sender / outgoing mail server (`ir.mail_server`) / footer / signature
from `self.env.company` at send time. When a cron / background job
sends mail across multiple companies in a loop, every mail goes out
under the **cron user's** `env.company` rather than the record's
`company_id` — wrong sender, wrong "Reply-To", wrong signature.

The same bug applies to `mail.alias.alias_defaults` and notification
preference resolution (`mail.notification` rows).

### Bad

```python
# v17 — cron sends ALL mails under self.env.company, not rec.company_id
def _cron_send_reminders(self):
    template = self.env.ref('my_module.reminder_template')
    for rec in self.env['my.model'].search([('state','=','reminder')]):
        template.send_mail(rec.id, force_send=True)  # wrong company context
```

### Good

```python
# v17 — switch company per record so mail server + sender resolve correctly
def _cron_send_reminders(self):
    template = self.env.ref('my_module.reminder_template')
    for rec in self.env['my.model'].search([('state','=','reminder')]):
        template.with_company(rec.company_id).send_mail(rec.id, force_send=True)
```

```python
# v12 — pre-with_company; pass force_company via context
def _cron_send_reminders(self):
    template = self.env.ref('my_module.reminder_template')
    for rec in self.env['my.model'].search([('state','=','reminder')]):
        template.with_context(
            force_company=rec.company_id.id,
        ).send_mail(rec.id, force_send=True)
```

### Falsification recipe

1. Create 2 companies, each with its own `ir.mail_server` (different
   SMTP relay, different "From" address).
2. Create one `my.model` record under each company in `state='reminder'`.
3. Trigger the cron (or call the method directly).
4. Inspect outgoing `mail.mail` records — check `mail_server_id` and
   `email_from` per message.
5. Bug: both mails routed through the same `ir.mail_server` (the
   cron user's default). Correct: each mail routed through its
   record's company's mail server.

```python
# realdata_test MCP eval — generic skeleton
self.env['my.model']._cron_send_reminders()
mails = self.env['mail.mail'].search([('model','=','my.model')])
for m in mails:
    rec = self.env['my.model'].browse(m.res_id)
    expected_server = rec.company_id.mail_server_id  # company-level config
    self.assertEqual(m.mail_server_id, expected_server,
                     "Mail routed through wrong company's mail server")
```

### Invariant suggestion (auto-enforce)

Detect: `send_mail(` / `message_post(` calls inside a loop iterating
records, without a `with_company(` (v17+) or `with_context(force_company=`
(v12) on the same chain.

```json
{
  "id": "multicompany-mail-with-company",
  "description": "send_mail / message_post inside loops must scope to record.company_id.",
  "applies_to": ["**/models/*.py", "**/wizards/*.py"],
  "rules": {
    "must_keep_regex": [
      "\\.with_(?:company|context)\\([^)]*(?:company_id|force_company)[^)]*\\)\\.(?:send_mail|message_post)\\("
    ]
  },
  "severity": "warn",
  "rationale": "Mail server + sender resolve from env.company at send time — see odoo-multi-company SKILL §5."
}
```

---

## 6. Cross-references

| Concern | Skill / file |
|---|---|
| Severity anchors for multi-company findings in code review | `odoo-code-review` §D + `references/odoo-<N>-rules.md` §E |
| Universal security checklist (incl. multi-company `ir.rule`) | `_common/code-review/references/security-checklist.md` |
| TDD harness for multi-company tests (`SavepointCase` + 2-company fixture) | `odoo-tdd` §3 (test layer decision tree) |
| Live ORM probes against real multi-company data | `odoo-data-verification` |
| Pattern snippets (model / CRUD / cron) baseline | `odoo-code-patterns` references |
| Performance overlap — `read_group` over multi-company tables uses indexes correctly only when `company_id` is the leading column | currently lives in `odoo-code-review` §B (perf) — no dedicated `odoo-performance` skill yet; flag as cross-link if/when it's created |

## 7. Sibling skills to call BEFORE this one

- `odoo-codebase-discovery` — locate the target model + read its
  manifest before pattern-matching.
- `odoo-deterministic-answers` (or `<stack>-deterministic-answers`) —
  call `lookup_canonical_decision` for project-specific multi-company
  rules (e.g. "always use parent.company_id, never user.company_id")
  before re-deriving.

## 8. Hard rules summary

- Never `create()` on a company-scoped model without `with_company()`
  (v14+) or `with_context(force_company=)` (v12).
- Never apply one `currency_id`'s rounding to another company's amount.
- Never declare `company_id` on a new `models.Model` without a matching
  `ir.rule` filtering on `company_ids` (plural).
- Never use a global `UNIQUE(col)` on a model with `company_id` —
  always `UNIQUE(company_id, col)`.
- Never call `send_mail` / `message_post` in a cross-company loop
  without scoping the company context per record.
