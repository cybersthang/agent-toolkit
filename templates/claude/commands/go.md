---
description: Enable AUTONOMY mode for a spec after grill is done — the agent has free rein over process_control / test_db_destructive / migration_dev / pytest / shell in the workspace, without asking the user. Default 4h, override with `--until`. Phase 3 of the Vibe-flow 5-phase (ADR-002).
allowed-tools: Read, Write, Edit, Bash
argument-hint: "<spec-slug> [--until +Xh|+Xd|eod|tomorrow|YYYY-MM-DD HH:MM]"
---

# /go — Vibe-flow Phase 3: AUTONOMY ON

## Mục tiêu

Cấp authorization cho agent thực hiện các hành động routine-but-dangerous mà
không cần DEV approve từng phát. Authorization được persist trong
`.agent-toolkit/.autonomy_active.json`, đọc bởi `session_brief.py` (banner)
+ `intent_router.py` (suppress clarification-gate).

## Quy trình

1. **Parse `$ARGUMENTS`**:
   - Token 1 = `<spec-slug>` (bắt buộc, trừ khi đã có autonomy đang ON → giữ slug cũ).
   - Token `--until <value>` (optional). Value:
     - Relative: `+4h`, `+30m`, `+1d`, `+2h30m`.
     - Named: `eod` = 23:59 hôm nay, `tomorrow` = +24h, `eow` = Chủ nhật 23:59.
     - ISO: `2026-05-17 18:00`.
     - Mặc định: `+4h`.

2. **Validate spec tồn tại**:
   - Read `.agent-toolkit/specs/<slug>.md`.
   - Nếu file không tồn tại → in lỗi, gợi `/plan <slug>` trước.
   - Nếu `status: draft` → cảnh báo "spec chưa qua grill, autonomy với spec yếu nguy hiểm — confirm bằng cách gõ lại lệnh kèm `--force`".
   - Nếu `status: grilled` hoặc cao hơn → OK.

2.5. **Pre-flight check — `acceptance_evals` exists** (added 2026-05-17, Vibe-flow 3-command):
   - Read frontmatter `acceptance_evals:` key.
   - Nếu block tồn tại → OK, proceed.
   - Nếu MISSING + `eval_status` ≠ `skipped-by-user`:
     - In warning: "Spec không có acceptance_evals. /grill thông thường auto-emit ở Step A end-of-grill — nếu skip → /verify về sau sẽ ad-hoc, có thể MISS bug."
     - Đề xuất 2 path:
       - `/eval-define <slug>` trước rồi gõ lại `/go` (Recommended)
       - `/go <slug> --no-evals` để xác nhận DEV cố ý skip (rare case: spike, no testable claims)
     - REFUSE start autonomy đến khi DEV quyết.
   - Nếu `eval_status: skipped-by-user` → proceed với warning banner trong autonomy state.

3. **Compute `expires_at`** từ `--until`. Format ISO local timezone.

4. **Check autonomy đang ON**:
   - Read `.agent-toolkit/.autonomy_active.json`.
   - Nếu đang ON cho spec khác → in cảnh báo "Đổi autonomy từ <old> → <new>".
   - Nếu đang ON cho cùng spec → in "Extend autonomy: <old expires_at> → <new>".

5. **Ghi `.autonomy_active.json`**:

```json
{
  "spec": "<slug>",
  "approved_at": "<ISO local now>",
  "expires_at": "<ISO local>",
  "approved_by": "/go slash command",
  "scopes": [
    "process_control",
    "test_db_destructive",
    "migration_dev",
    "pytest_arbitrary",
    "shell_within_workspace"
  ],
  "still_blocked": [
    "prod_db_write",
    "git_push_force",
    "credentials_write",
    "git_push_main_branch"
  ]
}
```

6. **Update spec frontmatter**: set `status: implementing`, `last_updated: <today>`.

7. **In banner xác nhận** (5-7 dòng):

```
🚀 AUTONOMY ON
  · spec: <slug>
  · approved: <HH:MM>
  · expires: <HH:MM> (sau <Xh Ym>)
  · scopes: process_control, test_db_destructive, migration_dev, pytest_arbitrary, shell_within_workspace
  · still_blocked: prod_db_write, git_push_force, credentials_write

→ Agent giờ được tự do trong scopes. Tắt sớm: /stop-autonomy.
→ Sau khi tasks PASS, auto /verify sẽ chạy.
```

8. **STOP** — không tự bắt đầu IMPLEMENT trong cùng turn. DEV gõ prompt kế tiếp để khởi động.

## Refuse / clarify khi

- Spec chưa tồn tại (chưa chạy `/plan`).
- Spec `status: draft` mà không có `--force`.
- `--until` parse thất bại → in format hợp lệ + gợi ý lại.
- `--until` resolve ra thời điểm quá khứ hoặc > +7 ngày → từ chối.
- `$ARGUMENTS` rỗng VÀ chưa có autonomy đang ON → từ chối.

## Không được làm

- KHÔNG bypass `invariant_guard` / `evidence_audit` / `debug_sentry` — 3 hook này vẫn chạy bất chấp autonomy.
- KHÔNG mở rộng `scopes` ngoài 5 cái default. Mở thêm scope = sửa ADR-002.
- KHÔNG cộng dồn timer (gõ /go lúc còn 30m + `--until +4h` ⇒ mới = +4h, không phải +4h30m).
- KHÔNG bật autonomy cho spec không có file ở `.agent-toolkit/specs/`.

## Sibling

- `/grill` — phase trước, sinh spec ở status `grilled`.
- `/stop-autonomy` — cắt sớm.
- `/verify` — phase sau, chạy auto khi tasks PASS hoặc DEV gõ manual.
- ADR-002 — quyết định chi tiết về scope + lifecycle.
