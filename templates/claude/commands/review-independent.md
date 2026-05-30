---
description: Run a FRESH-CONTEXT independent review — spawns a reviewer sub-agent that sees ONLY a code-assembled context packet (diff + spec + acceptance_evals + invariants), never the implementer's reasoning, and is prompted to refute each diff hunk. Catches blockers the same-context /review misses. MANUAL on-demand (early review / re-review / a PR); the done-boundary auto-runs this via independent_review_gate without a command.
allowed-tools: Read, Glob, Grep, Bash, Task
argument-hint: "[scope: spec-slug | PR | file path | empty=current branch diff]"
---

# /review-independent — fresh-context reviewer sub-agent

> **Manual path.** Trong flow thường DEV KHÔNG cần gõ lệnh này — gate
> `independent_review_gate` tự kích hoạt review độc lập ở done-boundary
> (ID-13). Dùng lệnh này khi muốn review SỚM, re-review, hoặc review một PR.

## Khác gì `/review`?
`/review` chạy trong CÙNG context của agent đã viết code → nhiễm ngữ cảnh,
sót blocker. `/review-independent` spawn một sub-agent **context-sạch** chỉ
thấy artifact → bắt được cái same-context bỏ sót (đó là cả lý do feature này
tồn tại).

## Step-by-step
1. **Áp dụng skill `independent-review`** (`.cursor/skills/_common/independent-review/SKILL.md`)
   — đọc contract đầy đủ ở đó. Tóm tắt các bước:
2. **Build packet:** `python3 tools/independent_review.py emit-context $ARGUMENTS`
   → `packet_sha` + `packet_path`. (Nếu `$ARGUMENTS` rỗng → slug spec
   `status: implementing`/`verified` gần nhất.)
3. **Spawn reviewer (Task tool), prompt = CHỈ packet path + lệnh đối kháng**
   ("review only from packet; default-skeptic, refute each hunk; echo packet_sha").
   KHÔNG đưa reasoning của bạn vào prompt.
4. **Nhận findings** theo schema (BLOCKER/MEDIUM/LOW + Proof + Doubt-pass).
5. **Verify mỗi BLOCKER reproduce được** trước khi ép fix (ID-21); không chứng
   minh → hạ MEDIUM.
6. **Confirmed BLOCKER → `.open_gaps.json`** → `gap_completeness_gate` ép fix.
7. **Fix → re-review incremental** tới khi 0-BLOCKER hoặc escalate (cap 3/5).

## Refuse / clarify khi
- `emit-context` báo "spec not found" → cần `/plan` + slug đúng.
- Không có thay đổi feature-scope nào (diff rỗng) → in "không có gì để review độc lập", STOP.

## Không được làm
- KHÔNG nhét reasoning/implementation-chat vào prompt reviewer (mất tính độc lập).
- KHÔNG tự gõ artifact thay reviewer — gate verify sub-agent transcript có thật.
- KHÔNG ép fix một BLOCKER chưa chứng minh được (ID-21).

## Sibling
- `/review` — review cùng-context (lock-file, 18-chiều).
- `/verify` — real-data probe.
- `independent_review_gate` — Stop hook tự kích hoạt review độc lập ở done-boundary.
