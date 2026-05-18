---
name: clarification-gate
description: BEFORE any non-trivial action (implement, fix, refactor, audit, scaffold, modify), emit a 3-block confirmation — UNDERSTANDING + ASSUMPTIONS + QUESTIONS — and STOP. The user must reply "go" / "yes" / answer the questions before any tool call that mutates state. Open this skill on every prompt that contains an action verb ("làm", "tạo", "sửa", "fix", "implement", "refactor", "thêm", "add", "update"…) AND that has any ambiguity in scope, target, or success criteria.
---

# Clarification Gate — Confirm Understanding Before Acting

> Default failure mode: AI reads a one-line action request, fills in the
> blanks silently, and produces an artifact that solves a *different*
> problem than the user had in mind. This skill is the universal
> guardrail: every non-trivial action goes through a 3-block check
> first, regardless of which other skill is active.

This skill is **lighter than `spec-driven-feature`** — it does not produce
a 6-field spec or a task list. It is a pre-flight check that runs on
every action prompt to decide:

- **No ambiguity** → declare so explicitly, then proceed with the
  appropriate skill workflow.
- **Has ambiguity** → list 1-3 surgical questions, STOP, wait for reply.

## When to apply

- Any prompt containing an action verb that mutates state: *implement,
  fix, refactor, scaffold, modify, add, remove, update, deploy, viết,
  tạo, sửa, thêm, xóa, build, làm, đổi…*
- Any prompt that uses the imperative mood without a clear target
  ("clean this up", "tối ưu lại", "làm gọn module này").
- Any prompt whose success criteria are not measurable from the wording
  alone ("faster", "cleaner", "đẹp hơn", "tốt hơn").
- Whenever opening another skill (code-review, spec-driven-feature, etc.)
  — run this gate FIRST, then the skill's own STOP checkpoints take over.

## When to SKIP (let the prompt through)

- Pure read-only questions: *"What does X do?", "Where is Y defined?",
  "Liệt kê A", "Show me B"* — no state change, no gate needed.
- Trivial one-liner edits the user has spelled out: *"Đổi `foo` thành
  `bar` ở file X line 42"*. The spelling-out IS the spec.
- The user has explicitly opted out: *"just do it", "implement luôn
  không cần hỏi", "go ahead"*, OR a system-reminder in this session
  says *"work without stopping for clarifying questions"*.
- Reply to your own previous QUESTIONS block (the user already answered).
- Prompts < 12 characters (the intent-router hook already filters these,
  but double-check).

## The 3-block output (mandatory shape)

```
### UNDERSTANDING

**Literal phrases from the user's prompt** (quote VERBATIM, 1-3 short
phrases that carry the load-bearing intent — file names, action verbs,
target objects, success criteria. DO NOT paraphrase here. If the prompt
is in Vietnamese, keep Vietnamese; do NOT translate):
- "..."
- "..."

**Paraphrase** (2-4 sentences, your own words, naming the artifact, the
change, and the observable success condition. This block proves you
understood — copying the prompt back verbatim here is a red flag.

CRITICAL: every ambiguous noun/pronoun/quantifier from Traps 1-5 MUST
remain VISIBLY UNRESOLVED in the paraphrase. Mark with
`[?<original-word> — chưa rõ X/Y/Z]` and carry that marker into
QUESTIONS. NEVER fill in a candidate noun in the paraphrase even when
you are 90% sure from context — the 10% case is where the user is
testing whether you'll ask.

Examples of correct vs incorrect paraphrase fill-in:

- Prompt: *"werkzeug chỉ chạy 6 cái"*
  - ❌ Wrong: "Werkzeug chỉ chạy 6 worker thread cùng lúc..."
  - ✅ Right: "Werkzeug chỉ chạy 6 [?cái — chưa rõ request/thread/worker] cùng lúc, anh muốn dashboard chỉ ra cụ thể 6 [?] nào đang chiếm slot."
- Prompt: *"2 cái này khác nhau"*
  - ❌ Wrong: "Hai widget khác nhau..."
  - ✅ Right: "[?2 cái này — chưa xác định là 2 widget / 2 view / 2 record] hiển thị khác nhau..."):
<...>

### ASSUMPTIONS
- <assumption 1: a fact you are about to act on that the prompt did not state explicitly>
- <assumption 2: …>
- <assumption 3: …>
(2-5 items; if you list zero, you are almost certainly wrong — re-read.)

### QUESTIONS
- **Q1**: <one specific question — clear, single-axis>
  - **(a) Recommended** — <option text + one-line rationale why it's the safe default>
  - (b) <alternative option text + when it's preferable>
  - (c) <optional third option, or "I don't know — please advise">
- **Q2**: <…same shape…>
- **Q3**: <…optional…>
(Maximum 3 questions. Every question MUST offer 2-3 labelled options
with exactly ONE marked **Recommended**. If you would list 4+ questions,
you have not understood enough — go back to UNDERSTANDING.)

### PROBE_READINESS (conditional — only for feature-scope tasks)

Emit THIS block when the task will produce an edit/write that matches
`.agent-toolkit/coverage_config.json` `feature_globs` (new controller,
new model method, new endpoint, new cron, new wizard). The whole point
is to extract probe parameters during grill, so the agent can register
a FULL probe entry post-implementation — no `_stub: true`, no TODO
placeholders, no DEV manual fill afterward.

Required sub-questions (ask whichever are not already implied by the task):

- **Verifiable behavior**: ONE empirical claim DEV will accept as "works".
  Examples: "route returns ≤500 rows for partner=42", "request BLOCKs UI
  until response arrives", "cron is idempotent (2 runs = same state)".
  → maps to probe `description`.

- **Empirical endpoint** (for HTTP routes / RPC): exact URL + method +
  auth context that hits the new code path. *"Just `/api/v1/foo`"* is
  insufficient — need full base URL (`http://localhost:8069`...) and
  any required headers/cookies.
  → maps to probe `falsification.runner.measurement_command`.

- **Falsification recipe**: what physical perturbation would flip the
  ACTUAL if the claim is wrong? Pick ONE of the 4 supported types:
  - `timing_perturb` — inject `time.sleep(N)`, expect downstream delta
    N±tolerance. Use for BLOCK / async / sync-vs-async claims.
  - `playwright` — spawn `npx playwright test <spec>`, parse JSON
    reporter. Use for browser-level claims (page render, UI flow,
    click-then-assert). Requires Playwright installed in project.
  - `log_assertion` — run command, grep stdout/stderr for
    required/forbidden patterns. Use when output text is signal.
  - `side_effect_inject` — declare a marker file; assert created/
    absent after measurement_command. Use for "was function called?".
  → maps to probe `falsification.type` + corresponding `runner.*`
  fields (`sleep_seconds`, `spec_file`, `required_patterns`,
  `marker_path`).

- **MCP evidence tool**: which MCP server tool proves the contract on
  real data? `mcp__realdata_test__run_module_test`,
  `eval_orm_expression`, `consistency_check_eval`, etc.
  → maps to probe `evidence.required_tools`.

Output PROBE_READINESS as a 4-row checklist:

```
### PROBE_READINESS
| Field | Captured from grill | Status |
|-------|--------------------|--------|
| description | <one-line semantic claim DEV gave> | ✓ / NEED ASK |
| measurement_command | <full curl/CLI command> | ✓ / NEED ASK |
| falsification recipe | <perturb type + expected delta> | ✓ / NEED ASK |
| MCP evidence tool | <mcp__...__name> | ✓ / NEED ASK |
```

If ANY status is `NEED ASK`, add the missing-info questions to the
QUESTIONS block above. DO NOT proceed with implementation until all 4
rows are `✓`. After grill answers received, all 4 fields populated →
agent writes FULL probe entry to `acceptance-probes.json` immediately
after Edit/Write (no `_stub`, no TODO).

This block exists because hooks (`probe_autostub`) can't infer
semantic intent or DEV-specific URLs/auth — those are decision-level
facts that must come from DEV during grill, not be stubbed
mechanically afterward.
```

OR, if every block can be filled with no ambiguity:

```
### UNDERSTANDING
**Literal phrases** (as above)
**Paraphrase** (as above)

### ASSUMPTIONS
- <as above>

### QUESTIONS
- None. Proceeding with <next skill / action>.
```

### Why the literal-phrases sub-block

Without quoting verbatim, the Paraphrase drifts toward whatever the
agent expected to see — Vietnamese keywords get silently translated
into English assumptions, action verbs get softened, target objects
get generalized. The literal sub-block is the anchor that keeps the
agent honest. If the Paraphrase later contradicts the quoted phrases,
the contradiction is visible to the user immediately.

## STOP rule

After printing the 3 blocks, **STOP**. Do not call any tool that mutates
state (Edit, Write, Bash with destructive flags, gh commands, etc.).
Read-only tools (Read, Glob, Grep, search MCP tools) are allowed before
the gate if needed to populate UNDERSTANDING — but the gate itself must
appear BEFORE any state-changing call.

The user's next reply is the signal:

- `"go"` / `"yes"` / `"approved"` / answering the questions → proceed.
- Any other content (corrections, new context, "wait") → update the gate,
  re-emit, and STOP again.

## Question quality bar

A good question has:

1. **A specific subject** (a file, a value, a behavior).
2. **2-3 labelled options** (a)/(b)/(c) — single-axis, mutually
   exclusive.
3. **One option marked Recommended** with a one-line rationale —
   *why* it is the safe default. The user can reply `"go"` and the
   Recommended option is taken; or pick (b)/(c) explicitly.
4. **Rationale, not just verdict**: the Recommended label is useless
   if the user can't tell why. Always add the "because…" clause.

**Bad question** *(no options, no rationale)*: "Threshold = 30 minutes?"

**Good question** *(options + Recommended + rationale)*:
```
Q1: Threshold value lấy từ đâu?
  (a) Recommended — runtime config parameter, fallback N. Lý do: ops
      tune được mà không redeploy code.
  (b) Hard-coded constant N. Lý do: đơn giản nếu không cần tune theo
      môi trường.
```

## Anti-rationalizations

| Rationalization | Counter-argument |
|---|---|
| "The prompt is clear, I don't need to confirm" | Then writing 3 blocks costs ~30 seconds and confirms it explicitly. The cost of wrong implementation is hours. The line where this skips makes sense is much closer to "trivial one-liner" than agents think. |
| "I'll ask one question inline while I work" | Inline questions in the middle of a tool-call streak get lost. The gate exists so questions arrive BEFORE the user has to read a diff to find them. |
| "User said earlier 'just do it', so this skip applies forever" | "Just do it" applies to ONE prompt scope. New prompt = re-evaluate. Long sessions drift; the gate re-anchors. |
| "It's just a small refactor" | Small refactors are where assumption errors hide best — large changes get scrutinized, small ones get rubber-stamped. The gate is especially worth running on small actions. |
| "The user will get annoyed by being asked" | Users complain about wrong code more than about good questions. A 30-second gate beats a 30-minute revert. |
| "I'll write the code first and check after" | Code-first reverses the loop. The 3 blocks must come BEFORE Write/Edit, not as a commit-message style after-thought. |
| "The user used phrase X but I know they really mean Y (a more meaningful alternative)" | **Anti-swap rule**: keep X in literal-phrases, raise Y as Q1 with default. The user may not know Y exists; let them choose. Never swap silently. Recovering from a silently-swapped concept after the code is written costs 10× the cost of asking. |
| "The user said 'this' / '2 cái này' / 'cái kia' — I can guess from context" | Demonstratives without explicit antecedents are ALWAYS questions. Context from earlier in the conversation may itself be wrong, or the user may have switched topics. Quote the demonstrative literally + ask. |
| "Technically X doesn't make sense — they must mean Z" | Technical impracticality is a REASON to ask, not a license to redefine. Phrase the technical concern as the question body, propose Z as default, let the user decide if Z is what they want. |
| "The technical context (Werkzeug / OWL / Postgres) tells me 'cái' = thread / record" | Technical context is a **hint**, not a definition. Generic counter-nouns ("cái", "thằng", "item") are MISSING NOUNS regardless of surrounding context. Quote literal, propose the context-derived guess as **(a) Recommended** in Q, but ALWAYS ask. The cost of one extra question is far less than the cost of building 6-worker dashboards when the user meant 6-request. |
| "I scanned the conversation and found the antecedent — I'm sure now" | High confidence still requires confirmation. Quote the prior turn that supplied the antecedent, mark it Recommended, ask. The user may have changed topic between turns; a one-line "yes/go" reply costs nothing. |

## Red flags — the gate is failing if any are true

- A state-changing tool was called before the 3 blocks were emitted.
- ASSUMPTIONS block has zero items (claim: nothing was assumed) — almost always wrong.
- QUESTIONS block has 4+ items — break into a SPECIFY phase (open `spec-driven-feature` instead).
- A question lacks a default — it forces the user to spell out an answer they could have said "go" to.
- The gate was emitted, the user said "wait, also do X" — but the next turn started implementing without re-emitting the gate.
- The gate's UNDERSTANDING block is a verbatim copy of the user's prompt (paraphrase failure — re-write in your own words to prove comprehension).
- The literal-phrases sub-block is missing or empty (gate is running without an anchor — Paraphrase will silently drift).
- A Vietnamese literal phrase was "auto-translated" into English in the Paraphrase block (translation introduces interpretation — keep both, quote literal, paraphrase in any language).
- The agent opened ≥3 SKILL.md files in the same turn as emitting the gate (likely caused by a hook that suggested multiple skills without prioritizing the gate — fix the hook, not the symptom).
- A question lacks 2-3 labelled options OR has no option marked **Recommended** — user is forced to spell out an answer they could have said "go" to.
- The Recommended option lacks a one-line *rationale* (just "Recommended" without "because…") — the label is unhelpful when the user can't tell why it's safe.
- An ambiguous noun/quantifier from the prompt (Trap 5: "6 cái", "N thằng", "có 5 items") appears FILLED-IN in the Paraphrase block (e.g. "6 thread", "5 record") instead of carrying its `[?<word> — chưa rõ X/Y/Z]` marker.
- The agent did not scan the last ~10 user turns for an antecedent before raising an ambiguous-quantifier Q. (Without scanning, the Q's Recommended option is uninformed and the user has to repeat themselves.)
- A Q for ambiguous quantifier was skipped because the agent felt "sure from context". Sure ≠ correct; the gate exists to catch the surprise case.

## Anti-swap rule (load-bearing — read carefully)

When the user names a concept and the agent finds a more "meaningful"
alternative, the agent MUST NOT silently swap. Two real cases this rule
exists to prevent:

**Case A — concept substitution**:
- User said: *"thêm 2 cột: tốc độ server trả về và tốc độ user gửi lên"*
- Agent found that "tốc độ user gửi lên" for XHR is technically <1ms
  (small POST body) and decided to swap in TTFB (server compute time)
  as "more meaningful".
- Result: user got TTFB columns when they asked for upload-speed columns.
  Code shipped solving a different problem.

The agent's correct move is to QUOTE the user's literal concept, raise
the technical concern as **Q1 with a default**, and let the user pick.
Default may favor the agent's recommendation — but the user must see
the choice and reply "go".

**Case B — vague reference resolved silently**:
- User said: *"2 cái này khác nhau, action load kanban nhưng trên 1 kiểu
  dưới 1 kiểu"*
- Agent assumed: "2 cái này" = 2 dashboard tabs, "trên/dưới" = scroll
  position, "kiểu" = format. None of these were stated.
- Result: agent edited the wrong views.

The agent's correct move is to flag EVERY ambiguous reference in
ASSUMPTIONS (or escalate to QUESTIONS), not resolve it from prior
context that may be wrong.

### Mandatory check before emitting UNDERSTANDING

For every literal phrase you quote, scan for these traps:

1. **Demonstrative without antecedent** ("cái này", "2 cái", "chỗ kia",
   "this", "the other one"): if the prompt does not name what the
   demonstrative refers to → QUESTION, not assumption.
2. **Spatial words without anchor** ("trên", "dưới", "bên trái",
   "above", "below"): if no view/widget/file is named → QUESTION.
3. **Vague qualitative words** ("kiểu", "đẹp", "tốt hơn", "weird",
   "wrong", "broken"): if not measurable from the prompt → QUESTION
   asking for the observable.
4. **Technical-sounding concept the user is unlikely to mean
   literally** ("tốc độ user gửi lên" cho 100-byte POST): keep the
   user's wording in literal-phrases, raise the technical issue as
   QUESTION — do NOT swap.
5. **Numeric quantifier without explicit noun** ("6 cái", "2 cái này",
   "3 thằng", "N items", "có 5 cái"): bare-number plus generic
   counter-noun is a MISSING NOUN, even when the surrounding technical
   context (Werkzeug, OWL, Postgres) suggests a likely candidate.
   QUESTION the noun. DO NOT silently infer "thread" / "worker" /
   "record" / "row" from the technical context — that context is a
   hint to propose as Recommended, not a license to fill in.

If you cannot quote the user's phrase AND restate it without violating
any of the five traps above, the prompt is ambiguous — questions are
mandatory.

### Before raising as QUESTION — scan prior conversation

For each ambiguous reference (Traps 1-5), BEFORE listing it as Q:

1. Scan the **last ~10 user turns** in this conversation for a
   previously-stated antecedent. The same phrasing typically returns
   when the user is still on the same topic.
2. If you find a turn that **explicitly named** the noun (e.g. earlier
   the user said *"với werkzeug thì chạy 1 lúc đc 6 request"*, and now
   says *"werkzeug chỉ chạy 6 cái"* → `6 cái = 6 request` with high
   confidence):
   - Quote the prior turn verbatim in your Q text.
   - Propose that interpretation as **(a) Recommended** with rationale
     "anh đã chốt ở turn trước".
   - List 1-2 plausible alternatives as (b)/(c).
   - **Still ASK** — do NOT silently apply, even with high confidence.
     The user may have changed topic, or the prior phrasing may itself
     have been ambiguous.
3. If you find NO prior turn with the antecedent:
   - Q with no Recommended-from-history; offer the 2-3 most plausible
     options based on the technical context, marking the most
     defensible one as Recommended.

This rule is what separates "polite ask" from "stubborn ask". Use
context — but use it to **inform a question**, never to **replace one**.

## Worked micro-examples

These examples use generic module/view names (`<module>`, `<view_a>`)
on purpose — the gate is module-agnostic. Discover real names at
runtime via the codebase MCP after the user approves the gate.

### Example 1 — concept-substitution trap

User prompt: *"thêm 2 cột: tốc độ server trả về và tốc độ user gửi lên"*

```
### UNDERSTANDING

**Literal phrases from prompt**:
- "thêm 2 cột"
- "tốc độ server trả về"
- "tốc độ user gửi lên"

**Paraphrase**: Anh muốn em thêm 2 cột vào bảng <view-em-sẽ-discover>:
một cột đo download speed (server → user) và một cột đo upload speed
(user → server) — đo theo bytes/time mỗi chiều — để dev nhìn cùng 1 row
là biết bottleneck chiều nào.

### ASSUMPTIONS
- "Bảng" có sẵn cột Time / Speed / Size — 2 cột mới chèn cùng nhóm.
- Đơn vị hiển thị theo cột hiện có (Mbps hay KB/s — em sẽ giữ nguyên convention).
- Không thay đổi business logic backend, chỉ thêm display column.

### QUESTIONS
- Q1: "Tốc độ user gửi lên" cho XHR/JSON-RPC trong app này thường là 1
  POST body rất nhỏ (~100 bytes) gửi trong <1ms — đo bytes/time sẽ ra
  con số không có ý nghĩa thực tế. Anh muốn em (a) vẫn show literal
  upload speed như anh nói (bytes-out / time-out, kể cả khi gần như 0),
  hay (b) thay cột này bằng TTFB (server compute time) — tách bạch
  "server lag" vs "network lag" rõ hơn? (default: (a) — giữ literal,
  thêm tooltip giải thích upload <1ms; (b) là kỹ thuật-recommended
  nhưng đổi nghĩa cột — không tự đổi mà không hỏi.)
- Q2: Discover view nào để thêm? Em sẽ dùng codebase MCP scan view có
  cột "Time" / "Speed" matching context. Anh có thể paste tên view nếu
  biết để skip discovery.
```

→ STOP. Đợi anh chọn Q1(a)/Q1(b) + Q2.

### Example 2 — numeric-quantifier-without-noun trap (Trap 5)

Conversation context (last 10 user turns include):
- Earlier user turn: *"với werkzeug thì chạy 1 lúc đc 6 request"*
- This turn (current prompt): *"werkzeug chỉ chạy 6 cái, xác định được trên dashboard 6 cái nào không"*

❌ **WRONG paraphrase** (silently fills "cái" = thread/worker):
```
Paraphrase: Werkzeug chỉ chạy 6 worker thread cùng lúc; anh muốn
dashboard chỉ ra cụ thể 6 thread nào đang chiếm slot...
```

✅ **CORRECT gate**:
```
### UNDERSTANDING

**Literal phrases from prompt**:
- "werkzeug chỉ chạy 6 cái"
- "xác định được trên dashboard 6 cái nào"

**Paraphrase**: Werkzeug chỉ chạy được 6 [?cái — chưa rõ
request/thread/worker] cùng lúc; anh muốn dashboard chỉ ra cụ thể
6 [?] nào đang chiếm slot, đang chạy gì, đã chiếm bao lâu — để dev
nhìn ra thủ phạm khi nghẽn.

### ASSUMPTIONS
- "Dashboard" = trang profiler hiện có (không tạo trang mới).
- Mục tiêu là *diagnostic visibility*, không phải auto-kill 6 [?] đó.

### QUESTIONS
- **Q1**: "6 cái" cụ thể là gì?
  - **(a) Recommended** — 6 **request** đồng thời. Lý do: ở turn
    trước anh đã chốt *"với werkzeug thì chạy 1 lúc đc 6 request"*
    — cùng topic, "cái" likely refer back to "request".
  - (b) 6 **thread** Werkzeug pool (`werkzeug.serving.ThreadedWSGI`
    có thread pool — nếu anh đang nói về thread workers).
  - (c) 6 **worker process** (Odoo `--workers=N`, không phải Werkzeug
    threaded mode — nếu deployment dùng prefork).
- **Q2**: Dashboard hiện đang track gì cho mỗi request/thread/worker?
  Anh có cell sẵn cho URL + duration không, hay phải thêm cột mới?
  - (a) Recommended — Em discover trước qua codebase MCP, báo cáo,
    rồi propose cột thiếu. Lý do: tránh duplicate cột đã có.
  - (b) Anh paste tên view/template em edit thẳng.
```

→ STOP. Đây là pattern đúng: high confidence (90% từ context trước)
nhưng vẫn ASK. Nếu anh reply "go" thì Recommended (a) applied.

→ Đây là evidence-based example: AI trong một chat khác đã vi phạm
chính trap này khi paraphrase "6 cái" thành "6 worker thread" mà
không hỏi, dẫn tới build dashboard chỉ N worker thay vì N request.

## Sibling skills

- `spec-driven-feature` — promotes a passed clarification gate into a full 6-field spec when the feature is large.
- `doubt-driven-review` — runs AFTER implementation to verify the gate's UNDERSTANDING actually matched reality.
- `<stack>-<version>-codebase-discovery` — read-only discovery you may run BEFORE emitting the gate to populate UNDERSTANDING accurately.
- `<stack>-<version>-deterministic-answers` — settled conventions you do NOT need to put as questions (they're already canonical).
