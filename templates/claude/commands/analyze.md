---
description: Spec Kit Phase 3.5 — ANALYZE. Cross-artifact consistency check between spec ↔ tasks ↔ acceptance_evals ↔ constitution BEFORE implement. Auto-fired as the first step of `/implement`; invokable manually. Returns READY / READY-with-warnings / HALT. On HALT the auto-chain stops.
allowed-tools: Read, Write, Grep, Glob, Bash
argument-hint: "<spec-slug>"
---

# /analyze — Spec Kit Phase 3.5: ANALYZE

## Mục tiêu

Pre-flight lint so sánh spec.md ↔ tasks.md ↔ acceptance_evals ↔
constitution ↔ invariants TRƯỚC khi implement. Bắt drift sớm, tiết kiệm
token implement.

Argument: `$ARGUMENTS` = `<spec-slug>`.

## Quy trình

1. **Áp dụng skill `analyze-artifacts`**
   (`.cursor/skills/analyze-artifacts/SKILL.md`).

2. **Locate artifacts — parallel globs**:
   - Spec: `Glob: .agent-toolkit/specs/**/<slug>.md`.
   - Tasks: `Glob: .agent-toolkit/specs/**/<slug>/tasks.md` HOẶC
     `.agent-toolkit/specs/**/<slug>.tasks.md`.

   Nếu thiếu spec hoặc tasks → BLOCK + exit.

3. **Load context — parallel reads**:
   - Spec + tasks file vừa locate.
   - `.agent-toolkit/constitution.md`.
   - `.agent-toolkit/decision-log.md`.
   - `.agent-toolkit/invariants.json`.
   - `.codex/canonical_decisions.json`.

4. **Run 7 checks** (C1-C7 trong `analyze-artifacts` SKILL.md):

   | # | Check | Mục đích |
   |---|---|---|
   | C1 | Story coverage | Mỗi User Story có ≥1 task |
   | C2 | Eval coverage | Mỗi acceptance_eval được cite |
   | C3 | Out-of-scope guard | Task không động vào file spec §7 cấm |
   | C4 | Invariant compat | Task không strip must_keep blocker |
   | C5 | Constitution compat | Task không vi phạm principle |
   | C6 | Path realism | Path tồn tại hoặc có marker `(new)` |
   | C7 | Verification concreteness | Verification line là mechanical |

   Mỗi check → ✅ PASS / 🟡 WARN / 🔴 BLOCK.

5. **Emit `analyze-report.md`** cùng dir với tasks.md.

6. **Decide verdict + return**:
   - All PASS → `READY` (auto-chain continues if invoked from `/implement`).
   - PASS + WARN → `READY-with-warnings` (continue, surface warnings).
   - Bất kỳ BLOCK → `HALT` (auto-chain stops; in report + đợi DEV fix).

7. **In summary** 3-5 dòng:
   ```
   Analyze — <slug> · <ISO datetime>
   ✅ PASS: <n>  🟡 WARN: <m>  🔴 BLOCK: <k>
   Verdict: READY | READY-with-warnings | HALT
   Report: <path-to-analyze-report.md>

   → <next step depending on verdict>
   ```

## Refuse / clarify khi

- Spec không tồn tại → BLOCK, bảo DEV chạy `/plan`.
- Tasks không tồn tại → BLOCK, bảo DEV chạy `/tasks <slug>`.
- Tasks `status: done` → no-op (đã pass lint trước implement).

## Không được làm

- KHÔNG mở Edit/Write trên file nguồn (analyze chỉ đọc).
- KHÔNG demote 🔴 BLOCK xuống 🟡 WARN để chain tiếp.
- KHÔNG return READY khi có ít nhất 1 BLOCK.

## Sibling

- `/tasks` — Phase 3, tạo tasks.md mà skill này lint.
- `/implement` — Phase 4, gọi `/analyze` là bước đầu inline.
- `/clarify` — quay về Phase 2 nếu BLOCK là spec-level (story thiếu, eval TBD).
