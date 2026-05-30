# Odoo 18 — scaffold deltas (cascade from 17)

Load **on top of** `odoo-17-scaffold.md`. Only the deltas below override.

## Manifest

```python
'version': '18.0.1.0.0',
```

Everything else (license, assets dict, data ordering) follows 17.

## Model template — prefer 18 conventions

- New compute methods preferring 18+ idioms (SQL wrapper, declarative
  constraints) — see `odoo-code-patterns/references/odoo-18-patterns.md`.
- `name_get()` deprecated — implement `_compute_display_name()` instead.

## View tag preference

```xml
<list>...</list>   <!-- 18 prefers <list> over <tree>; both legal -->
```

## Verification command

Same as 17.
