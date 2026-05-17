---
description: Generate a PRD/spec for a new feature — entry-point of Vibe-flow Phase 1. Use when you are about to write more than 50 lines of code. Does NOT implement; only writes the spec to `.agent-toolkit/specs/`.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "<feature description>"
---

# /plan — Vibe-flow Phase 1: PLAN

## Mục tiêu

Biến yêu cầu feature thành 1 spec có cấu trúc trong `.agent-toolkit/specs/`
trước khi viết bất kỳ dòng code nào. Spec là input của Phase 2 (`/grill`).

Argument: `$ARGUMENTS` (mô tả feature). Nếu rỗng, hỏi DEV.

## Quy trình

1. **Áp dụng skill `plan-feature`** (đọc kỹ `.cursor/skills/plan-feature/SKILL.md`).

2. **Bước 0 — Discover codebase tối thiểu**:
   - Pick 1-2 keyword chính từ `$ARGUMENTS`.
   - Gọi MCP `<stack>-<version>__odoo_code_search` (hoặc `Grep`) để xác định
     module / file có thể ảnh hưởng.
   - Ghi nhận `path:line` quan trọng để cite trong spec.

3. **Tạo slug feature** từ argument: lowercase, kebab-case, < 40 chars. Ví dụ:
   "Thêm export nhật ký NAKIVO theo ngày" → `export-nakivo-log-daily`.

4. **Kiểm tra trùng**: nếu `.agent-toolkit/specs/<slug>.md` đã tồn tại → hỏi
   DEV có muốn update file đó hay tạo file `<slug>-v2.md` mới. KHÔNG ghi đè
   silently.

5. **Tạo dir nếu thiếu**: `mkdir -p .agent-toolkit/specs`.

6. **Ghi spec** theo template 8 mục (Problem / Solution / Affected Modules /
   User Stories / Implementation Decisions / Testing / Out-of-scope / Open
   Questions) — xem `plan-feature` SKILL.md cho chi tiết template.

7. **In tóm tắt** 5-10 dòng cho DEV:
   - Đường dẫn spec.
   - Số module phát hiện.
   - Số Open Questions.
   - 1 dòng cuối: `→ Tiếp: /grill để stress-test plan.`

8. **STOP** — không gọi Edit/Write trên file nguồn. Đợi DEV bước tiếp.

## Refuse / clarify khi

- `$ARGUMENTS` < 8 ký tự (quá mơ hồ) → hỏi DEV mô tả rõ hơn.
- Feature thực ra là bug fix nhỏ < 30 dòng → gợi ý dùng `/grill` thẳng hoặc
  `<stack>-<version>-debug-troubleshoot`.
- Đã có spec mà DEV không muốn update → từ chối tạo bản v2 nếu DEV chưa
  giải thích vì sao 2 spec.

## Không được làm

- KHÔNG implement (Edit/Write trên file nguồn).
- KHÔNG copy verbatim `$ARGUMENTS` vào spec — phải paraphrase + cite code.
- KHÔNG hardcode tên module — discover qua MCP.
- KHÔNG bỏ mục "Open Questions" — đó là input cho phase GRILL.
