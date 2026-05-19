# Odoo 12 — debug pitfalls (standalone)

| Symptom | Root cause | Fix |
|---|---|---|
| `AttributeError: 'NoneType' has no attribute 'X'` on compute | `@api.multi` thiếu → method nhận empty recordset | Thêm `@api.multi` + loop `for r in self` |
| Compute không re-run khi field con thay đổi | `@api.depends` cite sai path (e.g. `line_ids.amount` mà field tên `subtotal`) | Sửa depends string đúng theo field name |
| `_constraints` chỉ fire khi `write`, không fire khi `create` từ wizard | 12 default: `@api.constrains` fire trên create+write nhưng wizard có thể `create()` rồi `_compute` mới chạy → constraint dùng compute chưa kịp populate | Force `record.write({...})` sau create trong wizard để re-trigger |
| Cron `_method_direct_trigger()` không có | Method name nhập sai | Method đúng là `method_direct_trigger()` (không dash) trên `ir.cron` record |
| Mock partner `email` bị reject | Default email validator strict | Dùng `<prefix>.test@example.com` style không phải `mock` |
| `web.AbstractWebClient` import lỗi | Khi sửa qua phiên bản 14+ | Đó là pattern v12 only — code đã upgrade rồi |
| `attrs="{...}"` không parse | View XML có lỗi syntax (thiếu quote) | `attrs="{'invisible': [('state','=','done')]}"` — quote string-domain values |

## Patterns to expect in v12 traceback

- `odoo.fields.Many2one._inherits_check` (delegation issue).
- `odoo.api.depends` warning về stored compute thiếu `store=True`.
- `web.AbstractWebClient` imports (frontend).
- `@api.one` deprecated warnings — replace với `@api.multi` + loop.
