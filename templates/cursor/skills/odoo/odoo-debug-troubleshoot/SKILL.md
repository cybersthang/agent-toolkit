---
name: odoo-debug-troubleshoot
description: Debug Odoo: traceback, AccessError, view, JS, SQL chậm, cron. Tìm lỗi → fix → nói file. Step 0 detects the addon's Odoo version from `__manifest__.py` and loads `references/odoo-<N>-pitfalls.md` for version-specific debugging quirks. Không giải thích quá trình phân tích.
---

# Odoo — Debug (version-aware)

## 0. Version detection (MANDATORY first step)

Use the same protocol as `odoo-code-review`:

1. **`__manifest__.py` `version` field** — read via `codebase.read_manifest`.
2. **Fallback signals** if manifest missing (see `odoo-code-review` for full table).
3. **Ask user** only if inconclusive.

Load `references/odoo-<detected>-pitfalls.md` for version-specific
debugging quirks:

| Detected major | Reference |
|---|---|
| 12 | `references/odoo-12-pitfalls.md` (standalone) |
| 13 | load `references/odoo-13-pitfalls.md` |
| 14 | load `references/odoo-14-pitfalls.md` |
| 15 | load `references/odoo-15-pitfalls.md` |
| 16 | load `references/odoo-16-pitfalls.md` (+ note: backports some v17 conventions) |
| 17 | `references/odoo-17-pitfalls.md` |
| 18 | `references/odoo-18-pitfalls.md` ← 17 |
| 19 | `references/odoo-19-pitfalls.md` ← 18 ← 17 |
| 20 | `references/odoo-20-pitfalls.md` ← 19 ← 18 ← 17 (pre-GA stub) |
| 21+ | fall back to 20 stub + flag MEDIUM |

## 1. Luồng: Xác định lỗi thực sự → Fix → Nói kết quả

1. Tìm root cause — **KHÔNG viết ra** quá trình suy luận, chỉ fix.
2. Output: tối đa 1 dòng tóm tắt + tên file. KHÔNG giải thích gì thêm.
3. Sửa nhiều chỗ 1 file → gom **1 edit cuối duy nhất**.
4. **NGHIÊM CẤM**: "Giờ rõ rồi", "Root cause là", "Vấn đề thực", "Cần kiểm tra", "Nhìn kỹ thì", "Tuy nhiên", liệt kê bước debug, mô tả flow code.

## 2. Tra cứu nhanh (version-agnostic)

Những lỗi này có cùng root cause + fix recipe across mọi Odoo version:

| Lỗi | Fix |
|-----|-----|
| NoneType / singleton | `ensure_one()` / check rỗng |
| IntegrityError | `_sql_constraints` / data |
| AccessError | `ir.model.access` + `ir.rule` |
| View invalid | XML syntax / field thiếu / `-u module` |
| read_group KeyError | field sai / compute cần `store=True` |

Cho lỗi đặc thù version (e.g. v12 vs v17 constraint timing, v18 SQL
wrapper, v19 controller route rename) → đọc reference đã load ở Step 0.

## 3. Perf (version-agnostic)

`--log-level=debug_sql`; đếm query; N+1 → batch/domain.

## 4. Cron (version-agnostic)

`ir.cron` active + `nextcall` + `max_cron_threads` + log.

## Sibling skills

- `odoo-code-review` — audit-style review (uses same version detection).
- `odoo-data-verification` — probe real DB for "is this stored value right?".
- `claim-falsification` — perturb-test pattern for "X is BLOCKING/ASYNC".
