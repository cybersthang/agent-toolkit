# Odoo 19 — scaffold deltas (cascade from 18 ← 17)

Load **on top of** `odoo-18-scaffold.md`.

## Manifest

```python
'version': '19.0.1.0.0',
```

## Controller routes (if scaffolding controllers)

```python
@http.route('/api/my', type='jsonrpc', auth='user')
def my_endpoint(self, **kw):
    ...
```

`type='jsonrpc'` (renamed from 18's `'json'`).

## Declarative model attributes

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

## Python version

Recommend Python 3.12 in the manifest's runtime expectations.

## Verification command

Same as 17/18.
