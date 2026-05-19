---
description: Spec Kit Phase 2 — CLARIFY. Interview the DEV one-question-per-turn to close every GAP in a spec produced by `/plan`. Cross-checks against ADRs + invariants + canonical decisions + constitution. On DEV "done", auto-fires `/tasks <slug>` (which STOPs for DEV review — does NOT trigger implement).
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
argument-hint: "[spec-slug, optional if only one draft exists]"
---

# /clarify — Spec Kit Phase 2: CLARIFY

## Mục tiêu

Đóng từng GAP / Open Question trong spec `/plan` vừa tạo. Mỗi turn 1 câu
hỏi cho DEV. Khi mọi quyết định đã chốt → spec chuyển `status: clarified`
+ `acceptance_evals` được refine + auto-fire `/tasks <slug>` (STOP cho
DEV review trước /implement).

Argument: `$ARGUMENTS` = slug spec (optional — nếu chỉ có 1 spec
`status: draft`, lấy luôn).

## Quy trình

1. **Áp dụng skill `clarify`** (`.cursor/skills/clarify/SKILL.md`).

2. **Locate spec — branch-scoped first**:
   - `Glob: .agent-toolkit/specs/**/<slug>.md` → pick file
     (most-recently-modified nếu nhiều hit).
   - Nếu 0 hit → bảo DEV chạy `/plan <slug>` trước.

3. **Load context — parallel reads with file-exists guard**:
   - Spec file đã locate (BẮT BUỘC; nếu thiếu → STOP).
   - Các file dưới đây là **optional** — `Glob` từng cái trước Read,
     nếu không tồn tại thì skip im lặng + ghi 1 dòng diagnostic
     `[clarify] skipped <file>: not present in this preset`:
     - `.agent-toolkit/constitution.md` (toolkit principles).
     - `.agent-toolkit/decision-log.md` (ADR cache).
     - `.agent-toolkit/invariants.json` (must-keep patterns).
     - `.codex/canonical_decisions.json` (stack convention — preset
       `generic` không ship file này; chỉ Odoo presets có).
     - `CONTEXT.md` ở root + per-module (glossary, thường thiếu).

4. **In dòng mở phiên**:
   ```
   Clarify mode ON — spec: <slug> · ADR: N · invariants: M · sẵn sàng.
   ```

5. **Vòng lặp clarify** — đi từng câu trong mục "Open Questions" của spec.
   Mỗi turn của agent CHỈ 1 câu, format `Q<N>: ... (a)/(b)/(c) Recommended`.

   - Đi sâu nhánh con của câu vừa trả lời TRƯỚC khi sang câu kế.
   - Self-resolve trước khi hỏi: nếu câu có thể trả lời bằng grep/Read/
     ADR/invariant/canonical_decisions → tự verify, in 1 dòng
     `verified qua <Source>: <answer>`, **không hỏi DEV**.
   - Phải đi qua 5-layer self-resolve trước khi emit Q:
     1. `decision-log.md` đã có ADR tương đương → áp dụng.
     2. `canonical_decisions.json` đã có quyết định → áp dụng.
     3. `invariants.json` đã ép pattern → áp dụng.
     4. `constitution.md` principle áp dụng được → áp dụng.
     5. Memory `~/.claude/projects/<encoded>/memory/` có preference → áp dụng.
   - Mục tiêu: 0-2 questions typical, không 5+.

5.5. **Test env URL capture** — trong mỗi DEV reply, parse regex
   `https?://[\w.:/-]+` HOẶC "test env" / "môi trường test". Nếu tìm thấy:
   - Ghi `.agent-toolkit/test_env.json` với `url`, `credentials_ref`,
     `captured_at`, `spec`.
   - In 1 dòng confirm: `✓ Test env URL captured: <URL>`.
   - KHÔNG persist credentials thật.

6. **Update spec inline** mỗi khi DEV chốt:
   - Move câu từ "Open Questions" → "Implementation Decisions".
   - Set frontmatter `last_updated`.
   - Nếu quyết định hard-to-reverse + có trade-off → gợi ý `/adr-add`.
   - Nếu rule must-keep → gợi ý `/inv-add`.

7. **Kết thúc** khi DEV gõ "đủ" / "xong" / "done":

   7a. **In tóm tắt clarify** (xem `clarify` SKILL.md).

   7b. **Refine `acceptance_evals`** — với mỗi entry `grader: TBD` /
       `expected: TBD`:
       - Apply ADR-007 Bước 1.7 (locate observable) → set `layer`.
       - Map Story claim → grader (data | code | shape | regression |
         empirical).
       - Pick MCP tool dựa trên `layer` + `grader`.
       - Set `expected.assertion` thành concrete value.
       - Smoke-test 1 representative probe; FAIL → in lỗi, KHÔNG
         auto-chain `/tasks`, bảo DEV fix probe trước.
       - Set `eval_status: defined`.

   7c. Set spec `status: clarified` + `last_updated: <today>`.

   7d. **Auto-fire `/tasks <slug>`** inline (same turn):
       - Call skill `tasks-breakdown` để emit `tasks.md`.
       - `tasks-breakdown` sẽ STOP và in DEV review prompt.
       - **KHÔNG** auto-trigger `/implement` — đó là DEV gate.

8. **STOP** — đợi DEV review tasks.md rồi gõ `/implement <slug>`.

## Refuse / clarify khi

- Không có spec nào ở `.agent-toolkit/specs/**/*.md` → bảo DEV chạy `/plan` trước.
- Spec status đã là `clarified` hoặc cao hơn → hỏi DEV có muốn re-clarify
  không (mất `tasks.md` cũ nếu có).
- DEV gõ "clarify" trong khi đang code Edit/Write → từ chối, yêu cầu
  commit hoặc stash trước.
- Spec không có mục "Open Questions" → spec viết sai format, bảo DEV chạy
  `/plan` lại.
- Auto refine `acceptance_evals` smoke-test FAIL → KHÔNG auto-chain
  `/tasks`, bảo DEV fix probe trước.

## Không được làm

- KHÔNG gộp 2+ câu hỏi vào 1 turn.
- KHÔNG mở Edit/Write trên file nguồn (chỉ được sửa spec file).
- KHÔNG auto-append ADR/invariant — phải gợi ý DEV chạy `/adr-add` hoặc
  `/inv-add` rồi DEV approve.
- KHÔNG hỏi câu mà 5-layer self-resolve trả lời được.
- KHÔNG persist credentials thật vào `test_env.json`.
- KHÔNG auto-trigger `/implement` — luôn STOP sau `/tasks`.
