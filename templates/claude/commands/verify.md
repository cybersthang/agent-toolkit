---
description: Vibe-flow Phase 5 — run MCP probes to verify the coded feature matches the original spec. Output a Gap/Blocker/Pass table per User Story. Manual via `/verify [slug]` or auto-triggered when the agent self-detects all tasks PASS.
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
argument-hint: "[spec-slug]"
---

# /verify — Vibe-flow Phase 5: VERIFY against real data

## Mục tiêu

Sau IMPLEMENT, đối chiếu thực trạng feature với spec gốc dùng dữ liệu thật.
Mục đích: bắt Gap / Blocker trước khi commit. Đây là gatekeeper cuối của
Vibe-flow.

## Quy trình

1. **Áp dụng skill `verify-feature`** (`.cursor/skills/verify-feature/SKILL.md`).

2. **Resolve slug** từ `$ARGUMENTS`:
   - Nếu có → dùng.
   - Nếu rỗng → đọc `.agent-toolkit/.autonomy_active.json`, dùng `spec` ở đó.
   - Nếu cả 2 đều không → list `.agent-toolkit/specs/*.md` status=implementing
     và hỏi DEV chọn.

3. **Load spec** + extract:
   - User Stories (mỗi story = 1 acceptance criterion).
   - Implementation Decisions (xác định ORM model / table / endpoint).
   - Testing Strategy (probe nào đã design sẵn).

4. **Design probe** cho từng User Story:
   - **ORM probe** (default): `mcp__realdata_test__run_python_tests` với
     expression `self.env['<model>'].search([...])` + assertion.
   - **Postgres probe**: `mcp__realdata_test__postgres_read_query` với COUNT /
     JOIN / EXPLAIN tùy story.
   - **HTTP probe**: nếu story liên quan controller → `Bash curl` hoặc
     `python -c "import requests; ..."`.

5. **Chạy probe PARALLEL** (gọi nhiều MCP tool trong 1 message).

6. **Diff actual vs expected**, classify:
   - `✅ PASS` — actual = expected.
   - `🟡 GAP` — actual ≠ expected nhưng không phá flow (ví dụ: cron chưa active
     trong test DB nhưng logic đúng).
   - `🔴 BLOCKER` — feature không hoạt động (return rỗng / exception / sai data).

7. **In Verify Report**:

```markdown
## Verify Report — <slug> · 2026-05-16 14:32
Spec: .agent-toolkit/specs/<slug>.md · status before: implementing

| # | User Story (rút gọn) | Probe | Expected | Actual | Status |
|---|---|---|---|---|---|
| 1 | export CSV theo ngày | env['<your.model>'].export() | size > 0 | 0 bytes | 🔴 BLOCKER |
| 2 | menu chỉ nhóm X thấy | postgres ir_ui_menu | 1 row | 1 row | ✅ PASS |
| 3 | cron 02:00 auto-run | ir.cron active=True | True | False | 🟡 GAP |

### Gaps / Blockers
🔴 #1 BLOCKER: export() trả file rỗng
  Root cause [assumption]: domain filter `[('date','=', today)]` không match
  định dạng date của `<your.model>.create_date` (datetime, không phải date).
  Đề xuất fix: domain → `[('create_date', '>=', today_start), ('create_date', '<', tomorrow_start)]`

🟡 #3 GAP: ir.cron chưa active sau install
  Nguyên nhân: data XML thiếu `noupdate="0"` hoặc record `active` default False.
  Đề xuất: bổ sung `<field name="active">True</field>` trong data XML.

### Summary
- Tổng story: 3
- ✅ PASS: 1 (33%)
- 🟡 GAP: 1 (33%)
- 🔴 BLOCKER: 1 (33%)
- **Verdict: NOT READY** (≥1 BLOCKER)

→ Spec status: gaps-found
→ Tiếp:
   - Fix BLOCKER #1 + GAP #3, sau đó /verify lại.
   - Hoặc /grill nếu thấy GAP là decision cần DEV chốt thay vì fix code.
```

8. **Update spec frontmatter**:
   - All PASS → `status: verified`.
   - Có GAP/BLOCKER → `status: gaps-found`.
   - Set `last_updated`, append `verify_history` block với count.

9. **Update autonomy** nếu đang ON:
   - All PASS → autonomy auto-OFF, status spec=done.
   - Có Blocker → giữ autonomy ON, agent có quyền fix tự do.

## Refuse / clarify khi

- Spec không tồn tại.
- Spec ở `status: draft` (chưa code) → từ chối, gợi /grill + /go trước.
- Không có MCP realdata_test active → in lỗi rõ.
- User Stories rỗng trong spec (spec viết kém) → từ chối, gợi /plan lại.

## Không được làm

- KHÔNG mutate dữ liệu prod trong probe (chỉ read-only postgres + ORM search).
- KHÔNG tự fix code trong cùng turn /verify (giai đoạn này chỉ report).
  Trừ khi autonomy đang ON VÀ DEV gõ "verify rồi fix luôn".
- KHÔNG skip story vì "không design được probe" — phải in 🟡 GAP: probe chưa
  thiết kế, KHÔNG ẩn.
