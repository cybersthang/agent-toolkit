# Odoo 17 — debug pitfalls (head of 17→18→19→20 cascade)

| Symptom | Root cause | Fix |
|---|---|---|
| `create()` override không fire trên batch insert | Override dùng `@api.model` single-record form | Dùng `@api.model_create_multi(vals_list)` |
| View parse error tại load `attrs=` | Removed in 17 | Replace bằng `invisible="<expr>"` / `readonly="<expr>"` |
| OWL component không mount | Thiếu `/** @odoo-module **/` header | Add header ở line 1 của file `.js` |
| Compute method nhận `self` không phải recordset | `@api.one` legacy → still working but produces fragmented behaviour | Remove `@api.one`, loop `for record in self:` |
| `name_get()` đã override không có tác dụng ở display name | Deprecated path; some views call `_compute_display_name` directly | Override `_compute_display_name` (compatible 17+) |
| `<tree>` view warning về list rendering | Optional rename — both legal in 17 | Keep `<tree>` if extending existing view; `<list>` for new |

## Patterns to expect in v17 traceback

- `odoo.addons.<module>.models.<x>` create/write paths.
- `web.assets_backend` manifest issues nếu OWL component không declare.
- Missing `assets` dict trong `__manifest__.py` cho OWL components.
- `attrs` parse error → migration debt từ v12 chưa clean.
