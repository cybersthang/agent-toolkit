# Odoo 19 — debug pitfalls (cascade from 18 ← 17)

| Symptom | Root cause | Fix |
|---|---|---|
| Controller route 404 mới migrate | `type='json'` renamed `'jsonrpc'` | Update `@http.route` |
| Domain construction TypeError với `'any!'` | New strict-any operator in 19 | Use `Domain('field', 'any!', sub_domain)` |
| `_sql_constraints` attribute warning | Legacy form — prefer declarative `_constraints` | Move to class-level `_constraints` list |
