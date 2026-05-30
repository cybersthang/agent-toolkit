---
description: Spec Kit Phase 1 — SPECIFY. Generate a PRD/spec for a new feature. Use when you are about to write more than 30 lines of code. Does NOT implement; only writes the spec to `.agent-toolkit/specs/<branch>/<slug>.md`.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "<feature description>"
---

# /plan — Spec Kit Phase 1: SPECIFY

## Mục tiêu

Biến yêu cầu feature thành 1 spec có cấu trúc trong
`.agent-toolkit/specs/<branch>/<slug>.md` trước khi viết bất kỳ dòng code
nào. Spec là input của Phase 2 (`/clarify`).

Argument: `$ARGUMENTS` (mô tả feature). Nếu rỗng, hỏi DEV.

## Quy trình

1. **Áp dụng skill `plan-feature`** (đọc kỹ `.cursor/skills/plan-feature/SKILL.md`).

2. **Bước 0 — Discover codebase tối thiểu**:
   - Pick 1-2 keyword chính từ `$ARGUMENTS`.
   - Gọi MCP `<stack>-<version>__odoo_code_search` (hoặc `Grep`) để xác định
     module / file có thể ảnh hưởng.
   - Ghi nhận `path:line` quan trọng để cite trong spec.

3. **Tạo slug feature** từ argument: lowercase, kebab-case, < 40 chars. Ví dụ:
   "Thêm export nhật ký theo ngày" → `export-log-daily`.

4. **Compute branch-scoped path** (Bash + PowerShell — same result):
   ```bash
   # POSIX / Git Bash
   branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr '/' '_' | sed 's/^\.//')
   branch=${branch:-_default}
   ```
   ```powershell
   # PowerShell (Windows native)
   $branch = (git rev-parse --abbrev-ref HEAD 2>$null) -replace '/','_' -replace '^\.',''
   if (-not $branch) { $branch = '_default' }
   ```
   Spec lives at `.agent-toolkit/specs/<branch>/<slug>.md`. **Print the
   resolved branch + path explicitly on the 1-line summary** so DEV knows
   exactly where the spec landed (no silent `_default` fallback).

5. **Kiểm tra trùng**: `Glob: .agent-toolkit/specs/**/<slug>.md`. Nếu match
   ≥1 → hỏi DEV có muốn update file cũ (cùng branch hay branch khác?) hay
   tạo `<slug>-v2.md` mới. KHÔNG ghi đè silently.

6. **Tạo dir nếu thiếu**: `mkdir -p .agent-toolkit/specs/<branch>`.

7. **Ghi spec** theo template 8 mục (Problem / Solution / Affected Modules /
   User Stories / Implementation Decisions / Testing / Out-of-scope / Open
   Questions) — xem `plan-feature` SKILL.md cho chi tiết template.

7.2. **Auto-detect `feature_kind`** (REQUIRED — drives Step 1.8 of /verify):

   Scan `$ARGUMENTS` + the User Stories you just drafted for the
   keywords below. Match a row → set `feature_kind: <value>` in spec
   frontmatter. Match nothing → omit the field (default = generic).

   | Keyword pattern (case-insensitive, EN + VN) | `feature_kind` |
   |---|---|
   | `\bclassify\|classification\|phân\s*loại\|gán\s*nhãn\|tag\s*each\|tag\s*every\|từng\s*request\|từng\s*record\|block\s*(vs\|hay)\s*async\|sync\s*(vs\|hay)\s*async\|severity\s*(low\|med\|high)` | `classification` |
   | `\bcount\|đếm\|distribution\|phân\s*bố\|aggregate\|aggregation\|gom\s*nhóm` | `aggregation` |
   | `\b(atomic\|idempotent\|cached\|deterministic\|retri(es\|able))\b.*\b(guarantee\|contract\|invariant)\b` | `contract` |

   **Why this matters**: when `feature_kind: classification`, the
   `verify-feature` Step 1.8 auto-invokes `real-data-proof` mandatorily
   (4-step workflow: acquire real data → distribute → falsify each
   tag → revert). The `verify_lint.py` Stop hook returns exit code 4
   (BLOCK) if the Verify Report is missing a `## Real-Data Proof`
   section. Without this auto-detection DEV must remember to set it
   manually — easy to miss, expensive when missed.

   Echo the decision in the summary line: `feature_kind: <value>
   (matched keyword: "<which-token>")` or `feature_kind: <none> — no
   classifier/aggregate/contract pattern detected`.

7.5. **Emit draft `acceptance_evals` skeleton**:

   Mục tiêu: DEV không phải gõ `/eval-define` riêng. /plan tự sinh khung
   acceptance_evals dựa trên User Stories; /clarify sẽ refine `grader` +
   `expected` ở phase sau.

   - Với MỖI User Story (N stories → N entries), append `acceptance_evals:`
     vào frontmatter:

     ```yaml
     acceptance_evals:
       - id: us<N>-<short-claim-slug>
         story: "Story N — <copy story summary>"
         grader: TBD              # data | code | shape | regression — chốt ở /clarify
         layer: TBD               # raw DB | endpoint | DOM | log | empirical — chốt ở /clarify (ADR-007 Bước 1.7)
         probe:
           tool: TBD              # smoke-tested ở /clarify, không guess MCP tool ở phase này
           args: {}
         expected:
           assertion: TBD         # concrete value | regex | "PASS" — chốt ở /clarify
         target_pass_rate: 1.0
         rationale: "Drafted by /plan from Story N — refine ở /clarify (ADR-007)."
     eval_status: draft
     ```

   - **KHÔNG smoke-test probe ở phase này** — chỉ là skeleton để /clarify
     biết có bao nhiêu eval cần chốt. Smoke-test bắt buộc khi /clarify
     hoàn thành (auto-refine inline).

   - **Trường hợp đặc biệt** — nếu User Stories quá mơ hồ (không paraphrase
     được thành claim_text rõ) → KHÔNG emit skeleton, set
     `eval_status: needs-clarify-first` + log "evals deferred, stories vague"
     trong summary.

8. **In tóm tắt** 5-10 dòng cho DEV:
   - Đường dẫn spec (`.agent-toolkit/specs/<branch>/<slug>.md`) — **bao
     gồm branch name** (hoặc literal `_default` nếu không detect được).
   - Số module phát hiện.
   - Số Open Questions.
   - Số `acceptance_evals` skeleton emitted (hoặc lý do skip).
   - 1 dòng cuối: `→ Tiếp: /clarify <slug> — refine evals + auto-fire /tasks.`

9. **STOP** — không gọi Edit/Write trên file nguồn. Đợi DEV bước tiếp.

## Refuse / clarify khi

- `$ARGUMENTS` < 8 ký tự (quá mơ hồ) → hỏi DEV mô tả rõ hơn.
- Feature thực ra là bug fix nhỏ < 30 dòng → gợi ý dùng `/clarify` thẳng hoặc
  `<stack>-<version>-debug-troubleshoot`.
- Đã có spec mà DEV không muốn update → từ chối tạo bản v2 nếu DEV chưa
  giải thích vì sao 2 spec.

## Không được làm

- KHÔNG implement (Edit/Write trên file nguồn).
- KHÔNG copy verbatim `$ARGUMENTS` vào spec — phải paraphrase + cite code.
- KHÔNG hardcode tên module — discover qua MCP.
- KHÔNG bỏ mục "Open Questions" — đó là input cho phase GRILL.
