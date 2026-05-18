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
   - **Self-resolve mandate (Change 2)**: trước khi emit Q, phải đi qua
     5-layer self-resolve. Chỉ emit Q nếu CẢ 5 layer im lặng:
     1. ADR cache (`.agent-toolkit/decision-log.md`) đã có quyết định tương
        đương? → áp dụng, không hỏi.
     2. Claim-falsification recipe catalog có default? (Recipe 1-15) → áp
        dụng default.
     3. Anti-hardcode ladder L1→L4 (ADR-005) đã chốt L1 introspection? → áp
        dụng L1.
     4. Active invariants (`.agent-toolkit/invariants.json`) đã ép pattern?
        → áp dụng pattern.
     5. Memory feedback (`~/.claude/projects/<encoded>/memory/`) đã ghi
        preference? → áp dụng.
     Mỗi self-resolve in 1 dòng `verified qua <Source>: <answer>` rồi move
     on. Mục tiêu: 0-2 questions typical, không phải 5+.

4.5. **Test env URL capture (Change 2)** — trong mỗi DEV reply, parse text bằng
   regex `https?://[\w.:/-]+` HOẶC chuỗi "test env"/"môi trường test" +
   credentials. Nếu phát hiện:
   - Ghi `.agent-toolkit/test_env.json`:
     ```json
     {
       "url": "<URL>",
       "credentials_ref": "<paste prefix or 'inline'>",
       "captured_at": "<ISO local now>",
       "spec": "<slug>"
     }
     ```
   - In 1 dòng confirm: `✓ Test env URL captured: <URL> — auto /go sẽ enable sau khi grill done.`
   - **KHÔNG persist credentials vào file** — chỉ giữ `credentials_ref` (e.g. "inline"); credentials thật vẫn ở session memory.

5. **Update spec inline** mỗi khi DEV chốt:
   - Di chuyển câu từ "Open Questions" → "Implementation Decisions".
   - Set frontmatter `last_updated`.
   - Nếu quyết định hard-to-reverse + có trade-off → gợi ý `/adr-add`.
   - Nếu rule must-keep → gợi ý `/inv-add`.

6. **Kết thúc** khi DEV gõ "đủ" / "xong" / "done":
   - In báo cáo tổng kết (xem `grill` SKILL.md).
   - Set spec `status: grilled` trong frontmatter.

   **Auto-chain (Change 2 — compress phases)**:

   6a. **Auto /eval-define** (always run after grill done):
       - Đọc `acceptance_evals:` skeleton từ frontmatter (do /plan emit).
       - Với mỗi entry `grader: TBD` / `layer: TBD` / `probe.tool: TBD`:
         - Apply ADR-007 Bước 1.7 (locate observable) → set `layer`.
         - Map từ User Story claim → grader (data | code | shape |
           regression | empirical) theo bảng ở /eval-define SKILL.
         - Pick MCP tool dựa trên `layer` + `grader` (postgres_read_query
           cho data+rawDB, run_python_tests cho code, Bash curl+jq cho
           shape+endpoint, browser_evaluate cho DOM, Recipe perturb-test
           cho empirical).
         - Set `expected.assertion` thành concrete value (extract từ
           Implementation Decisions hoặc User Story acceptance).
       - **Smoke-test 1 representative probe**. Nếu fail → in lỗi, KHÔNG
         auto-chain /go, bảo DEV fix probe trước.
       - Set `eval_status: defined`.
       - In summary: `✓ N evals refined: us1-<...> (data), us2-<...> (empirical), ...`

   6b. **Auto /go** (only if test env URL captured AND eval-define succeeded):
       - Check `.agent-toolkit/test_env.json` exists.
       - Nếu YES → call /go logic inline:
         - Compute `expires_at` = `+4h` (default).
         - Write `.agent-toolkit/.autonomy_active.json` per /go Step 5.
         - Set spec `status: implementing`, `last_updated: <today>`.
         - In banner `🚀 AUTONOMY ON` (5-7 dòng per /go Step 7).
       - Nếu NO → in 1 dòng: `⏸ Test env chưa provide — gõ /test-env <url> hoặc paste URL trong reply tiếp theo để auto-/go. Hoặc /go <slug> manual.`

   6c. **STOP** — không tự bắt đầu IMPLEMENT trong cùng turn. DEV gõ prompt
       kế tiếp ("implement đi" / "bắt đầu" / ...) để khởi động. Hook
       `post_edit_verify_gate.py` sẽ ép `/verify` chạy khi implementation
       claim done.

   - **Override** — nếu DEV muốn skip auto-chain (rare: spike, không cần
     evals): gõ `/grill done --no-auto-chain` hoặc kết thúc bằng "xong, không auto".
     Khi đó in dòng cũ: `→ /eval-define để chốt evals, rồi /go bật autonomy.`

## Refuse / clarify khi

- Không có spec nào ở `.agent-toolkit/specs/` → bảo DEV chạy `/plan` trước.
- DEV gõ "grill" trong khi đang code Edit/Write → từ chối, yêu cầu commit
  hoặc stash trước.
- Spec không có mục "Open Questions" → spec viết sai format, bảo DEV chạy
  `/plan` lại.
- Auto /eval-define smoke-test FAIL → KHÔNG auto-chain /go, bảo DEV fix
  probe trước khi grill done lại.

## Không được làm

- KHÔNG gộp 2+ câu hỏi vào 1 turn.
- KHÔNG mở Edit/Write trên file nguồn (chỉ được sửa spec file).
- KHÔNG auto-append ADR/invariant — phải gợi ý DEV chạy `/adr-add` hoặc
  `/inv-add` rồi DEV approve.
- KHÔNG hỏi câu mà grep/Read trả lời được.
- KHÔNG hỏi câu mà 5-layer self-resolve trả lời được (Step 4 mandate).
- KHÔNG persist credentials thật vào `.agent-toolkit/test_env.json` — chỉ
  giữ URL + `credentials_ref`.
- KHÔNG auto-chain /go khi spec `status: draft` (chỉ chain khi `grilled`).
