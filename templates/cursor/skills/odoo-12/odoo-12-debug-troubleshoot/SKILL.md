---
name: odoo-12-debug-troubleshoot
description: >-
  Debug Odoo 12: traceback, AccessError, view, JS, SQL chậm, cron. Tìm lỗi →
  fix → nói file. Không giải thích quá trình phân tích.
---

# Odoo 12 — Debug

## Luồng: Xác định lỗi thực sự → Fix → Nói kết quả
1. Tìm root cause — **KHÔNG viết ra** quá trình suy luận, chỉ fix.
2. Output: tối đa 1 dòng tóm tắt + tên file. KHÔNG giải thích gì thêm.
3. Sửa nhiều chỗ 1 file → gom **1 edit cuối duy nhất**.
4. **NGHIÊM CẤM**: "Giờ rõ rồi", "Root cause là", "Vấn đề thực", "Cần kiểm tra", "Nhìn kỹ thì", "Tuy nhiên", liệt kê bước debug, mô tả flow code.

## Tra cứu nhanh
| Lỗi | Fix |
|-----|-----|
| NoneType / singleton | `ensure_one()` / check rỗng |
| IntegrityError | `_sql_constraints` / data |
| AccessError | `ir.model.access` + `ir.rule` |
| View invalid | XML syntax / field thiếu / `-u module` |
| read_group KeyError | field sai / compute cần `store=True` |

## Perf
`--log-level=debug_sql`; đếm query; N+1 → batch/domain.

## Cron
`ir.cron` active + `nextcall` + `max_cron_threads` + log.
