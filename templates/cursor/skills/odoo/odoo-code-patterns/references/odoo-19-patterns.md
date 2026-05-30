# Odoo 19 — pattern deltas (cascade from 18 ← 17)

Load this **on top of** `odoo-18-patterns.md` (which cascades onto
`odoo-17-patterns.md`). Only override what differs in 19.

## Controller route type rename

```python
@http.route('/api/my', type='jsonrpc', auth='user')   # 19+
def my_endpoint(self, **kw):
    ...
```

- `type='json'` (used in 12 / 17 / 18) is **renamed** to `type='jsonrpc'`
  in Odoo 19.
- New family `type='json2'` exists in 19 for a different JSON contract.

## `Domain` API + `any!` operator

```python
from odoo import Domain

dom = Domain('partner_id', 'any!', [('country_code', '=', 'VN')])
records = env['sale.order'].search(dom)
```

- `Domain` class formalizes domain construction.
- `'any!'` operator is the strict counterpart to `'any'`.

## Declarative `_constraints` / `_indexes`

```python
class MyModel(models.Model):
    _name = 'my.model'

    _constraints = [
        ('positive_total', 'CHECK(total >= 0)', 'Total must be positive.'),
    ]
    _indexes = [
        ('idx_partner_date', 'partner_id, date'),
    ]
```

- Declarative form on class body, NOT via `_sql_constraints`
  attribute (still supported but legacy).

## AI server actions

Odoo 19 ships first-class AI server actions. Reference Odoo upstream
docs for the exact API surface.

## Python version

- Odoo 19 recommends Python 3.12.

## Hard rules (Odoo 19 deltas)

- Controller routes use `type='jsonrpc'` (not `'json'`).
- Domain construction uses the `Domain` API for non-trivial cases.
- `_constraints` + `_indexes` are declared as class attributes.
