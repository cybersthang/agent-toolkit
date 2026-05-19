# Odoo 18 — debug pitfalls (cascade from 17)

| Symptom | Root cause | Fix |
|---|---|---|
| `TypeError: search() got unexpected keyword 'args'` | API rename | Use `search(domain=...)` |
| `read_group` field aggregator silent default | `group_operator` renamed `aggregator` on field declaration | Declare `aggregator='sum'` on the field, not at read_group call |
| `check_access_rights` deprecation warning | Unified into `check_access(operation)` | Replace both `check_access_rights` + `check_access_rule` |
| `name_get` warning at runtime | Deprecated | Override `_compute_display_name` |
