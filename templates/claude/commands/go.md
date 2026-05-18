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
   - Read frontmatter `acceptance_evals:` + `eval_status` key.
   - Acceptable states để proceed:
     - `eval_status: defined` (refined bởi /grill auto-chain hoặc /eval-define manual) → OK.
     - `eval_status: skipped-by-user` → proceed với warning banner.
     - `acceptance_evals` block tồn tại + có ít nhất 1 entry với `grader` ≠ `TBD` → OK (legacy specs).
   - REFUSE states (in warning + đề xuất path, KHÔNG start autonomy):
     - `eval_status: draft` (skeleton từ /plan, chưa refine) → bảo DEV chạy `/grill <slug>` để refine, hoặc `/eval-define <slug>` manual.
     - `eval_status: needs-grill-first` → bảo DEV chạy `/grill <slug>`.
     - `acceptance_evals` MISSING hoàn toàn → bảo DEV chạy `/plan <slug>` lại (Change 2: /plan luôn emit skeleton).
   - **Inline-call mode (Change 2)** — nếu /go được call inline từ /grill
     auto-chain (Step 6b), skip block warning vì /eval-define vừa run trong
     cùng turn. Detection: `eval_status: defined` + `last_updated` = hôm nay.
   - Override 1 lần: `/go <slug> --no-evals` để cố tình skip eval requirement.

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
  · test_env: <URL từ .agent-toolkit/test_env.json, hoặc "(none — verify sẽ ad-hoc)">

→ Agent giờ được tự do trong scopes. Tắt sớm: /stop-autonomy.
→ Sau khi tasks PASS + claim done, `post_edit_verify_gate` ép auto /verify.
```

8. **STOP** — không tự bắt đầu IMPLEMENT trong cùng turn. DEV gõ prompt kế tiếp để khởi động.

   **Lưu ý Change 2 (compress phases)**: nếu /go được call inline từ /grill
   Step 6b, thì /grill skill cũng STOP cùng turn — DEV chỉ cần gõ prompt
   "implement" / "bắt đầu" để agent đi. Không tự chain qua phase Implement.

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
