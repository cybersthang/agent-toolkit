# Odoo 19 — TDD pitfalls (cascade from 18 ← 17)

| Pitfall | Detection | Fix |
|---|---|---|
| Controller test gets 404 | Route declared `type='json'` (18 form), but 19 expects `type='jsonrpc'` | Update `@http.route(type='jsonrpc')` |
| Domain test fails with `any!` operator | New strict-any operator in 19; test was built for 18 `any` | Use `Domain('field', 'any!', sub_domain)` and assert strict-membership |
| `_sql_constraints` test assertion misses 19 declarative form | Constraint declared via `_constraints` class attribute | Test reads `model._constraints` list (not `_sql_constraints`) |
