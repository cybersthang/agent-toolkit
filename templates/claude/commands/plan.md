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

6.5. **Emit draft `acceptance_evals` skeleton (Change 2 — compress phases)**:

   Mục tiêu: DEV không phải gõ `/eval-define` riêng. /plan tự sinh khung
   acceptance_evals dựa trên User Stories; /grill sẽ refine `grader` +
   `expected` ở phase sau.

   - Với MỖI User Story (N stories → N entries), append `acceptance_evals:`
     vào frontmatter:

     ```yaml
     acceptance_evals:
       - id: us<N>-<short-claim-slug>
         story: "Story N — <copy story summary>"
         grader: TBD              # data | code | shape | regression — chốt ở /grill
         layer: TBD               # raw DB | endpoint | DOM | log | empirical — chốt ở /grill (ADR-007 Bước 1.7)
         probe:
           tool: TBD              # smoke-tested ở /grill, không guess MCP tool ở phase này
           args: {}
         expected:
           assertion: TBD         # concrete value | regex | "PASS" — chốt ở /grill
         target_pass_rate: 1.0
         rationale: "Drafted by /plan from Story N — refine ở /grill (ADR-007)."
     eval_status: draft
     ```

   - **KHÔNG smoke-test probe ở phase này** — chỉ là skeleton để /grill biết
     có bao nhiêu eval cần chốt. Smoke-test bắt buộc ở /eval-define (auto-chained sau /grill).

   - **Trường hợp đặc biệt** — nếu User Stories quá mơ hồ (không paraphrase
     được thành claim_text rõ) → KHÔNG emit skeleton, set
     `eval_status: needs-grill-first` + log "evals deferred, stories vague"
     trong summary.

7. **In tóm tắt** 5-10 dòng cho DEV:
   - Đường dẫn spec.
   - Số module phát hiện.
   - Số Open Questions.
   - Số `acceptance_evals` skeleton emitted (hoặc lý do skip).
   - 1 dòng cuối: `→ Tiếp: /grill <slug> — auto-refine evals + chuẩn bị autonomy.`

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
