---
description: Cut AUTONOMY mode immediately. Deletes `.agent-toolkit/.autonomy_active.json`. The agent returns to normal mode (clarification-gate runs again). Use when the user sees the agent going off-track or wants to pause for review.
allowed-tools: Read, Bash
---

# /stop-autonomy — Cắt autonomy ngay

## Mục tiêu

Tắt autonomy mode tức thì. Không cần argument.

## Quy trình

1. **Read `.agent-toolkit/.autonomy_active.json`**:
   - Nếu file không tồn tại → in "Autonomy đã OFF từ trước. Không cần làm gì."
   - Nếu tồn tại → tiếp tục.

2. **Capture state để in báo cáo**:
   - `spec`, `approved_at`, `expires_at`, time remaining.

3. **Xóa file** (rm hoặc rename `.autonomy_active.json.stopped-YYYYMMDD-HHMMSS` để có audit trail).

4. **In xác nhận**:

```
🛑 AUTONOMY OFF
  · spec đã pause: <slug>
  · đã chạy: <Xh Ym> trên tổng <Xh> approved
  · time còn lại bỏ qua: <Xh Ym>

→ Agent quay về normal mode (clarification-gate active).
→ Bật lại: /implement <slug> [--until X].
```

5. **Không** update spec status — spec vẫn ở `implementing` cho đến khi DEV gõ `/implement` lại
   hoặc manually đổi qua `/clarify` / `/plan`.

## Refuse / clarify khi

- (Không có case refuse — slash này luôn safe.)

## Không được làm

- KHÔNG xóa file spec.
- KHÔNG roll back code đã viết — DEV tự quyết undo bằng git.
- KHÔNG chạy verify tự động — DEV gõ `/verify` nếu muốn.
