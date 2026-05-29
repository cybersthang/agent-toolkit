# Odoo 16 — debug pitfalls (neighbour = v17)

> odoo-16 reference (drafted v0.29). Deltas vs v17 web-verified where cited; <!-- VERIFY --> items need DEV confirmation.

Load when Step 0 detected major = **16**. Structural model is
`odoo-17-pitfalls.md`; this file records only the 16-specific divergences.

| Symptom | Root cause | Fix |
|---|---|---|
| `create()` override không fire trên batch insert | Override dùng `@api.model` single-record form | Dùng `@api.model_create_multi(vals_list)` (same as v17) |
| Inline `invisible="state == 'done'"` không có tác dụng (field luôn hiện) | Inline Python-expr trên `<field>` chỉ hoạt động từ **17**; code này viết cho 17 chạy trên 16 | Dùng `attrs="{'invisible': [('state','=','done')]}"` trong 16 (verified: inline syntax là "since 17.0") |
| View parse error / unknown tag `<list>` | `<list>` là rename của 17; 16 dùng `<tree>` | Dùng `<tree>` trong 16 |
| `name_get()` override không có tác dụng (display name sai) trên 16.0 | Nhầm: code override `_compute_display_name` (16.4+/17 form) thay vì `name_get` | Trên 16.0 override `name_get(self)` trả list `(id, label)`. `name_get` deprecated từ saas-16.4 → `_compute_display_name`, removed 17.0 (PR #122085) |
| `AttributeError: flush` / DeprecationWarning trên `recordset.flush()` | `flush()`/`recompute()` deprecated trong 16 | Dùng `flush_model()` / `flush_recordset(fnames=None)` / `env.flush_all()` theo granularity (verified: OCA v16 migration + ORM API) |
| `invalidate_cache()` / `refresh()` deprecated warning | Renamed trong 16 | Dùng `invalidate_model()` / `invalidate_recordset(fnames=None, flush=True)` / `env.invalidate_all()` |
| `fields_view_get()` override không được gọi | Renamed `get_view()` trong 16 | Override `get_view()`; `fields_view_get` deprecated (verified: OCA v16 migration) |
| `get_xml_id()` deprecated | Renamed | Dùng `get_external_id()` |
| Field translation đọc từ `ir.translation` trả rỗng | Translated fields → JSONB trong 16, `ir.translation` không còn giữ field translations | Đọc qua field bình thường với context lang; code translations lấy từ PO files (verified: odoo/odoo #97692/#101115) |
| OWL component không mount | Thiếu `/** @odoo-module **/` header | Add header line 1 (same as v17) |
| Bootstrap classes (col-*, ml-/mr-) render sai trong report/website | Odoo 16 chuyển Bootstrap 4 → 5 | Migrate sang BS5 classes (`ms-`/`me-`, `col-*` đổi gutters) (verified: OCA v16 migration, `convert_string_bootstrap_4to5`) |

## Patterns to expect in v16 traceback

- `odoo.addons.<module>.models.<x>` create/write paths — same shape as v17.
- `web.assets_backend` manifest issues nếu OWL component không declare
  trong `'assets'` dict.
- DeprecationWarning cho `flush`/`recompute`/`invalidate_cache`/`refresh`
  — đặc trưng 16; trong v17 các call này thường đã được dọn sạch.
- View load ValidationError vì `<list>` hoặc inline `invisible="<expr>"`
  → dấu hiệu code viết cho 17 chạy nhầm trên 16 (ngược với v17, nơi
  `attrs=` là migration debt từ 12).
- `name_get` không gọi: kiểm tra xem có nhầm `_compute_display_name`
  (17 form) không.
