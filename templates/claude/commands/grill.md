---
description: Interview the user one-question-per-turn to stress-test a spec before implementing. Phase 2 of the Vibe-flow. Cross-checks against ADRs + invariants + the in-code glossary. Runs only after a spec exists at `.agent-toolkit/specs/`.
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
argument-hint: "[spec-slug, optional]"
---

# /grill — Vibe-flow Phase 2: GRILL

## Mục tiêu

Quay DEV 1-câu-1-turn cho đến khi mọi quyết định trong spec đủ rõ để
implement. Cập nhật spec inline khi DEV chốt câu trả lời. Promote quyết định
quan trọng thành ADR / invariant.

Argument: `$ARGUMENTS` = slug spec cần grill (optional — nếu chỉ có 1 spec
ở `.agent-toolkit/specs/`, lấy luôn).

## Quy trình

1. **Áp dụng skill `grill`** (`.cursor/skills/grill/SKILL.md`).

2. **Load context** — chạy SONG SONG (parallel reads):
   - `.agent-toolkit/specs/<slug>.md` (nếu nhiều spec → hỏi DEV chọn).
   - `.agent-toolkit/decision-log.md` (toàn bộ ADR).
   - `.agent-toolkit/invariants.json` (toàn bộ invariant).
   - `CONTEXT.md` ở root + per-module nếu có (glossary).

3. **In dòng mở phiên**:
   ```
   Grill mode ON — spec: <slug> · ADR: N · invariants: M · sẵn sàng.
   ```

4. **Vòng lặp grill** — đi từng câu trong mục "Open Questions" của spec.
   Mỗi turn của agent CHỈ 1 câu, format `Q<N>: ... (a)/(b)/(c) Recommended`.
   - Đi sâu nhánh con của câu vừa trả lời TRƯỚC khi sang câu kế.
   - Nếu câu có thể trả lời bằng grep/read code → tự verify, in 1 dòng
     "verified qua <Read/Grep>", rồi đi tiếp. KHÔNG hỏi DEV.

5. **Update spec inline** mỗi khi DEV chốt:
   - Di chuyển câu từ "Open Questions" → "Implementation Decisions".
   - Set frontmatter `last_updated`.
   - Nếu quyết định hard-to-reverse + có trade-off → gợi ý `/adr-add`.
   - Nếu rule must-keep → gợi ý `/inv-add`.

6. **Kết thúc** khi DEV gõ "đủ" / "xong" / "done":
   - In báo cáo tổng kết (xem `grill` SKILL.md).
   - Set spec `status: grilled` trong frontmatter.
   - In dòng cuối: `→ /eval-define để chốt acceptance evals trước implement, rồi /go để bật autonomy. (ADR-002 Vibe-flow Phase 2 → Phase 3).`

## Refuse / clarify khi

- Không có spec nào ở `.agent-toolkit/specs/` → bảo DEV chạy `/plan` trước.
- DEV gõ "grill" trong khi đang code Edit/Write → từ chối, yêu cầu commit
  hoặc stash trước.
- Spec không có mục "Open Questions" → spec viết sai format, bảo DEV chạy
  `/plan` lại.

## Không được làm

- KHÔNG gộp 2+ câu hỏi vào 1 turn.
- KHÔNG mở Edit/Write trên file nguồn (chỉ được sửa spec file).
- KHÔNG auto-append ADR/invariant — phải gợi ý DEV chạy `/adr-add` hoặc
  `/inv-add` rồi DEV approve.
- KHÔNG hỏi câu mà grep/Read trả lời được.
