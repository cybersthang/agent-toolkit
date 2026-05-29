---
description: Spec Kit Phase 4 — IMPLEMENT. DEV authorizes the agent to execute tasks.md autonomously. Auto-chain: /analyze (HALT on BLOCK) → autonomy ON → execute tasks one-by-one → /verify (real-data probes) → report back to DEV. Replaces the old `/go` command. Default autonomy `+1h` (v0.21 E5 — narrower risk window; DEV opt-in cho longer runs via `--until`).
allowed-tools: Read, Write, Edit, Bash
argument-hint: "<spec-slug> [--until +Xh|+Xd|eod|tomorrow|YYYY-MM-DD HH:MM] [--no-evals] [--force]"
---

# /implement — Spec Kit Phase 4: IMPLEMENT (auto-chain)

## Mục tiêu

DEV authorize agent thực hiện tasks.md tự động. Sau khi DEV gõ
`/implement <slug>`, agent tự chạy chuỗi:

```
/analyze <slug>   → if HALT, in report + STOP, đợi DEV fix
       ↓
   autonomy ON  (.agent-toolkit/.autonomy_active.json)
       ↓
   execute T1, T2, … (mỗi task: edit → run verification step → record)
       ↓
   /verify <slug>   → emit Verify Report (PASS/GAP/BLOCKER)
       ↓
   báo cáo DEV: implementation done + verify verdict
```

Tất cả trong cùng phiên autonomy. DEV không phải confirm giữa các bước.

## Quy trình

1. **Parse `$ARGUMENTS`**:
   - Token 1 = `<spec-slug>` (bắt buộc).
   - `--until <value>`: `+1h`, `+30m`, `+4h`, `+1d`, `+2h30m`, `eod`,
     `tomorrow`, `eow`, ISO `2026-05-17 18:00`. Default `+1h` (v0.21 E5 —
     reduced from `+4h` to narrow the risk window; DEV must opt-in via
     `--until +4h` (hoặc lớn hơn) cho long-running implement sessions.
     Rationale: hầu hết feature implement < 1h; autonomy expired chỉ buộc
     DEV ấn lại `/implement <slug>` — không mất tiến độ.).
   - `--no-evals`: skip acceptance_evals requirement (rare).
   - `--force`: bypass status checks (rare).

2. **Locate spec + tasks — branch-scoped**:
   - `Glob: .agent-toolkit/specs/**/<slug>.md`.
   - `Glob: .agent-toolkit/specs/**/<slug>/tasks.md` (canonical layout).
   - Legacy `.agent-toolkit/specs/**/<slug>.tasks.md` still readable by
     hooks but new emissions use canonical only — see
     `tasks-breakdown/SKILL.md` Step 2 migration note.

3. **Validate**:
   - Spec status: `clarified` / `grilled` → OK; `draft` → refuse (chưa qua /clarify); `implementing`/`verified` → confirm DEV muốn re-implement.
   - tasks.md exists → bắt buộc.
   - `acceptance_evals` `eval_status: defined` (trừ khi `--no-evals`).

4. **Inline-call `/analyze <slug>`** (skill `analyze-artifacts`):
   - Nếu verdict `HALT` → in analyze-report.md, KHÔNG bật autonomy,
     KHÔNG implement, STOP. DEV fix BLOCKER rồi gõ lại `/implement`.
   - Nếu verdict `READY` hoặc `READY-with-warnings` → tiếp tục.

5. **Compute `expires_at`** từ `--until`. Format ISO local timezone.

6. **Ghi `.agent-toolkit/.autonomy_active.json`**:

   ```json
   {
     "spec": "<slug>",
     "approved_at": "<ISO local now>",
     "expires_at": "<ISO local>",
     "approved_by": "/implement slash command",
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

7. **Update spec frontmatter**: `status: implementing`, `last_updated`.
   Update tasks.md frontmatter: `status: approved`.

8. **In banner 🚀 IMPLEMENT** (5-7 dòng):
   ```
   🚀 IMPLEMENT — auto-chain ON
     · spec: <slug>
     · tasks: <N> tasks pending
     · expires: <HH:MM> (sau <Xh Ym>)
     · scopes: process_control, test_db_destructive, migration_dev,
                pytest_arbitrary, shell_within_workspace
     · still_blocked: prod_db_write, git_push_force, credentials_write

   → Agent đi T1 → … → T<N> → /verify → báo cáo.
   ```

9. **Execute tasks** — wave-parallel where provably safe, else sequential:
   - **Plan waves first**: `python tools/wave_planner.py plan <path/to/tasks.md>`.
     The planner groups tasks into ordered waves — tasks in the same wave have
     all deps satisfied by an earlier wave AND touch DISJOINT files. It is
     CONSERVATIVE: empty / glob / overlapping `Touches`, or a dependency cycle,
     are never parallelized (own wave / full sequential fallback).
   - **If `sequential_fallback: true` OR `parallel_waves: 0`** → run the
     per-task loop below strictly T1 → T2 → … → T<N> (unchanged behavior).
   - **Else, for each wave in order:**
     - **1-task wave** → run it via the per-task procedure below (inline).
     - **≥2-task wave** (provably file-disjoint):
       1. `python tools/wave_planner.py emit <tasks.md> --wave <i>` — writes
          `.agent-toolkit/.parallel_wave.json`; `parallel_conflict_guard` now
          DENIES any sub-agent Edit outside its own task's `Touches` (its zone).
       2. Spawn **one sub-agent per task in the wave, in a SINGLE message**
          (Agent tool). Give each: its task block + its `Touches` (its zone) +
          "Edit ONLY files in your zone; run your Verification; report PASS/FAIL
          + evidence." Sub-agents do NOT commit.
       3. **Wait for all**, then `python tools/parallel_wave.py declare-done`
          (release the zone lock before the next wave).
       4. Record each task's PASS/FAIL; any FAIL → the per-task 3-option prompt
          below. Do NOT start the next wave until the current one resolves.
   - **Per-task procedure** (used inline AND inside each spawned sub-agent):
   - For each task T<i>:
     - Read task's Touches files (Edit them).
     - Run task's Verification step (MCP tool / shell).
     - Record PASS/FAIL ngắn dưới task trong tasks.md (status:
       `passed | failed | skipped` + timestamp).
     - Nếu FAIL → STOP execute, in failed task + last 20 lines of error,
       in **3-option prompt** cho DEV, đợi reply:

       ```
       ❗ T<i> FAILED — <one-line cause>
       Choose: (r) retry — same task, after DEV fixes
               (s) skip   — mark T<i> as skipped, continue T<i+1>
               (a) abort  — stop chain, drop autonomy
       (You may also Edit files first then reply with the letter.)
       ```

     - **Parse DEV reply** with these exact prefixes (case-insensitive,
       trim whitespace): `r`, `retry`, `s`, `skip`, `a`, `abort`. Any
       other reply → re-print the prompt once; if still ambiguous after
       2 rounds → default to `abort` (safe).
     - **retry**: re-run T<i> Verification step. If FAIL again → re-prompt.
     - **skip**: write `skipped` + DEV's typed reason (if any text follows
       the verb) under T<i> in tasks.md; continue T<i+1>. Skipped tasks
       count as GAP in the final /verify report row.
     - **abort**: write `aborted` under T<i>, drop autonomy, STOP. Verify
       does NOT run.

10. **Inline-call `/verify <slug>`** sau khi tất cả task PASS:
    - Skill `verify-feature` chạy probe trên real data.
    - Emit Verify Report (PASS / GAP / BLOCKER table per User Story).
    - Update spec `status` theo verdict: `verified` / `gaps-found` / `blocked`.
    - Update autonomy: all PASS → auto-OFF; còn issue → giữ ON.

10b. **Inline-call `/implement-notes <slug>`** sau khi `/verify` xong, TRƯỚC step 11 báo cáo (v0.18+):
    - Read project config `.agent-toolkit/implement_notes.json`:
      - If `auto_emit: false` → SKIP step 10b (DEV opt-out).
      - Else honor `output_format` (default `both`).
    - Walk current session transcript → extract:
      §1 Scope deviations (Edit ngoài `acceptance_eval.probe.args.target`)
      §2 In-transcript trade-offs (cite turn id, STRICT)
      §3 Open follow-ups (TODO/FIXME/spec-candidate flag)
      §4 Confidence summary (H/M/L per decision; LOW items DEV verify trước)
    - Emit `<slug>.implement-noted.md` (machine-parseable, validator-friendly)
      AND/OR `<slug>.implement-noted.html` (DEV browser review,
      self-contained CSS) per `output_format`.
    - On failure to emit (transcript walk error / template render fail):
      WARN but don't block step 11 — DEV can retroactively run
      `/implement-notes <slug>` to fill the gap.

11. **Báo cáo DEV** — 1 message tổng kết:
    ```
    ✅ Implement done — <slug>
      · Tasks: <N>/<N> PASS
      · Verify: <verified | gaps-found | blocked>
      · Spec status: <new status>
      · Autonomy: <off | extended until HH:MM>

    Verify Report: <path>
    Implement Notes: <path-to-html> (open in browser to review)
    <key findings if GAP/BLOCKER>

    → <next step depending on outcome>
    ```

## Refuse / clarify khi

- Spec không tồn tại (chưa /plan).
- tasks.md không tồn tại (chưa /tasks).
- Spec `status: draft` mà không có `--force`.
- `acceptance_evals` chưa `defined` mà không có `--no-evals`.
- `/analyze` returned HALT → STOP, in report, đợi DEV fix.
- `--until` parse fail hoặc > +7 ngày → từ chối.

## Không được làm

- KHÔNG bypass `invariant_guard` / `evidence_audit` / `debug_sentry` —
  3 hook này vẫn chạy bất chấp autonomy.
- KHÔNG mở rộng `scopes` ngoài 5 mục default. Mở thêm = sửa ADR-002.
- KHÔNG cộng dồn timer.
- KHÔNG skip `/analyze` step — drift gate là load-bearing.
- KHÔNG skip `/verify` step — real-data gate là load-bearing.
- KHÔNG báo "done" khi `/verify` chưa chạy hoặc trả BLOCKER.

## Sibling

- `/plan` — Phase 1, tạo spec.
- `/clarify` — Phase 2, refine spec + auto `/tasks`.
- `/tasks` — Phase 3, emit tasks.md (DEV gate).
- `/analyze` — Phase 3.5, gate trước implement.
- `/verify` — Phase 5, real-data check sau implement.
- `/stop-autonomy` — cắt sớm autonomy nếu cần.
- ADR-002 — quyết định chi tiết về scope + lifecycle autonomy.
