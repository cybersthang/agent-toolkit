---
description: Spec Kit Phase 3 — TASKS. Take a clarified spec and emit `tasks.md` next to it — a discrete, verifiable task list. Auto-fired by `/clarify` on completion; can also be re-emitted manually. STOPS after emit (DEV review gate before /implement).
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
argument-hint: "<spec-slug> [--regenerate]"
---

# /tasks — Spec Kit Phase 3: TASKS

## Mục tiêu

Biến spec đã `status: clarified` thành tasks.md — danh sách task có
Acceptance + Verification cho mỗi item. DEV review tasks.md, edit nếu
cần, rồi gõ `/implement <slug>` để bắt đầu auto-chain.

Argument: `$ARGUMENTS` = `<spec-slug>` (bắt buộc). Flag `--regenerate`
ép overwrite tasks.md cũ nếu đang `status: approved`.

## Quy trình

1. **Áp dụng skill `tasks-breakdown`** (`.cursor/skills/tasks-breakdown/SKILL.md`).

2. **Locate spec — branch-scoped**:
   - `Glob: .agent-toolkit/specs/**/<slug>.md`.
   - Nếu 0 hit → bảo DEV chạy `/plan <slug>` trước.

3. **Validate spec status**:
   - `status: draft` → từ chối, bảo DEV chạy `/clarify <slug>` trước.
   - `status: clarified` / `grilled` → OK.
   - `status: implementing` / `verified` → cảnh báo "spec đã xong, chắc
     muốn tạo tasks.md mới?".

4. **Validate `acceptance_evals` defined**:
   - `eval_status: defined` → OK.
   - `eval_status: draft` → từ chối, bảo DEV chạy `/clarify` trước.
   - Missing → từ chối, bảo DEV chạy `/plan` lại (skeleton emit ở Phase 1).

5. **Check tasks.md cũ**:
   - Tìm `Glob: .agent-toolkit/specs/**/<slug>/tasks.md` HOẶC
     `.agent-toolkit/specs/**/<slug>.tasks.md` (legacy flat).
   - Nếu có với `status: approved` → refuse trừ khi `--regenerate`.
   - Nếu có với `status: draft` → overwrite (tasks chưa được DEV approve).

6. **Emit tasks.md** theo template trong `tasks-breakdown` SKILL.md:
   - Path: `.agent-toolkit/specs/<branch>/<slug>/tasks.md` (cùng dir với spec
     mới) HOẶC `.agent-toolkit/specs/<slug>.tasks.md` (nếu spec ở legacy
     flat path).
   - Mỗi User Story → ≥1 task.
   - Mỗi `acceptance_evals` entry → đúng 1 task cite nó.
   - Acceptance + Verification line bắt buộc.

7. **In summary** 5-10 dòng:
   ```
   Tasks ready — <branch>/<slug> · <N> tasks · <M> LOC budget
   - T1: <one-line goal>
   - …
   Coverage: stories <covered>/<total>, evals <cited>/<total>

   → DEV review tasks.md, gõ `/implement <slug>` để auto-chain
     (analyze → implement → verify). Edit → `/tasks <slug> --regenerate`.
   ```

8. **STOP** — KHÔNG auto-trigger `/analyze` hay `/implement`. DEV review
   gate là điểm pause bắt buộc.

## Refuse / clarify khi

- Spec không tồn tại (chưa chạy `/plan`).
- Spec `status: draft` (chưa chạy `/clarify`).
- `acceptance_evals` chưa `defined` (chưa chạy `/clarify`).
- tasks.md cũ `status: approved` mà không có `--regenerate`.

## Không được làm

- KHÔNG mở Edit/Write trên file nguồn (tasks là plan, không phải code).
- KHÔNG auto-fire `/implement` — DEV review gate là điểm STOP bắt buộc.
- KHÔNG tạo task cho story không có trong spec — fabrication.
- KHÔNG tạo task touching file ngoài spec §3 Affected Modules.

## Sibling

- `/plan` — Phase 1, tạo spec.
- `/clarify` — Phase 2, refine spec + acceptance_evals (auto-fire `/tasks`).
- `/implement` — Phase 4 (đọc tasks.md, auto-chain analyze + verify).
- `/verify` — Phase 5 (real-data probe sau implement).
