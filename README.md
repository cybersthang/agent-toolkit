# agent-toolkit

> **Spec-Driven AI agent toolkit for Odoo (12-20), in active use on a real Odoo 12 Enterprise workspace. Falsifiability + mechanical enforcement + Spec Kit workflow.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](setup.py)
[![pipeline](https://gitlab.com/nosafarm/agent-toolkit/badges/main/pipeline.svg)](https://gitlab.com/nosafarm/agent-toolkit/-/pipelines)
[![Claude Code](https://img.shields.io/badge/Claude_Code-compatible-7c3aed)](https://docs.claude.com/en/docs/claude-code)
[![Cursor](https://img.shields.io/badge/Cursor-rules%20%2B%20skills-1e40af)](https://cursor.com)
[![Spec Kit](https://img.shields.io/badge/Spec_Kit-aligned-22c55e)](https://github.com/github/spec-kit)
[![Bilingual](https://img.shields.io/badge/docs-EN%20%2B%20VN-orange)](#-tiếng-việt)


AI agents ship buggy code when nothing **mechanically** stops them. This toolkit
makes 6 rules un-skip-able: invariant guard, evidence audit, real-data verify,
git guardrail, kill-switch banner, bypass-rate alert.

## Install

```bash
git clone <toolkit-repo> ~/agent-toolkit
python ~/agent-toolkit/setup.py init /path/to/project --preset odoo-12 --yes
```

Other presets: `odoo-13` / `odoo-14` / `odoo-15` / `odoo-16` / `odoo-17` /
`odoo-18` / `odoo-19` / `odoo-20`, `generic`. Contributing a `django` /
`rails` / `go` preset is a one-PR exercise — see
[PORTING.md](templates/agent_toolkit/PORTING.md).

**For contributors / local hacking on the toolkit itself**:
```bash
cd ~/agent-toolkit
make install   # pytest + pytest-cov + ruff
make rebuild   # full CI-equivalent: lint + test + smoke + dry-run + coverage gate
```

Full release / mirror / tag procedure documented in [REBUILD.md](REBUILD.md).

## Why agent-toolkit?

- 🛡️ **Mechanical enforcement, not honor system.** 30+ hooks DENY at the
  Claude Code harness level — invariant strips, claim-without-proof,
  destructive git (`git_guardrails` blocks commit/push/add until DEV
  explicitly authorizes), hallucinated progress, **unresolved gaps on
  done-claim** (`gap_completeness_gate` v0.19 — chặn drip-feed),
  **partial-done on a multi-item request** (`scope_completeness_gate` v0.23
  — enumerates full scope from tasks.md / acceptance_evals / TodoWrite and
  blocks a done/full claim while any item is still pending), and
  **cross-zone edits between concurrent sub-agents**
  (`parallel_conflict_guard` v0.25 — file-disjoint Wave manifest blocks any
  Edit that targets a file owned by a different sub-agent). Not warnings
  the agent can ignore.
- 🔬 **Real-data verify or it didn't ship.** `/verify` runs MCP probes on
  the live DB; `evidence_audit` Stop hook BLOCKS "tests pass" claims that
  lack an `mcp__realdata_test__*` or `mcp__postgres__*` call in the turn.
- 📐 **5-phase Spec Kit workflow with gate hooks.** `/plan → /clarify →
  /tasks → /analyze → /implement → /verify` — each transition has a
  PreToolUse / Stop hook that refuses to advance if the prior phase
  has gaps.
- 🧭 **Trinity rule system.** Constitution (slow principles) → ADRs (why
  decisions) → invariants.json (mechanical patterns). Cross-linked,
  auditable, append-only. No upstream toolkit has this 3-tier layout.
- 🔌 **Stack-agnostic core + preset overlays.** `<file>.<framework>.json`
  picker installs the right config per preset. Odoo 12-20 (9 versions)
  ship today; Django/Rails/Go is a config addition, not a fork.
- 📡 **Observability built-in.** `emit_fire_event` ring buffer, hook-health
  aggregator, bypass-rate alerts, hook-crash banner. Know which rules are
  being sidestepped before they rot.

## What's new

- **v0.22** (TBD pending merge to master): Community + Enterprise edition
  coverage, MCP security hardening, atomic state writes. 5 new Odoo skills
  (`odoo-community-patterns`, `odoo-enterprise-patterns`, `odoo-multi-company`,
  `odoo-owl-components`, `odoo-performance`) → **14 Odoo skills** total.
  10 cross-version performance recipes shipped. 5 default invariants shipped
  with the preset. 12 outstanding TODO markers resolved. See
  [CHANGELOG.md](CHANGELOG.md) for the full diff.
- **v0.26**: sub-agent-stall-watcher — extend v0.24 `agent_supervisor`
  với multi-transcript mode kích hoạt khi v0.25 `.parallel_wave.json`
  active. Watcher detect bất kỳ sub-agent transcript nào stale (mtime cũ)
  + autonomy active → aggregate notify (kênh v0.24:
  toast/log/SMTP/webhook) với prefix `[sub-agent <wave>]`. Notify-only
  cho sub-agent (Agent tool model-only spawn). Đóng gap "sub-agent treo
  giữa wave" từ v0.24 D11 + v0.25 §7 (xem [docs/parallel.md](docs/parallel.md)
  + [docs/resilience.md](docs/resilience.md)).
- **v0.25**: parallel-subagent-guard — `parallel_conflict_guard.py`
  PreToolUse hook BLOCK cross-zone Edit khi 2 sub-agent song song (Agent
  tool) đụng cùng file. Manifest từ `tools/parallel_wave.py emit` (CLI
  helper) + skill `parallel-batching` (5-step template, dogfood Wave A
  v0.21). Identity từ envelope `agent_id` (docs hooks.md). Bypass:
  `bypass-parallel-guard:` (xem [docs/parallel.md](docs/parallel.md)).
- **v0.24**: agent-resilience — `tools/agent_supervisor.py` stall-watcher
  (read-only detect → notify, cả VSCode-extension lẫn CLI; `--relaunch` cap 10
  cho CLI) + resume-brief trong `session_brief` (tái dùng R9 manifest làm
  checkpoint idempotent). Notify: toast/log/SMTP/webhook. 529: tune
  `CLAUDE_CODE_MAX_RETRIES` (xem [docs/resilience.md](docs/resilience.md)).
- **v0.23**: `scope_completeness_gate` Stop hook — chặn partial-done trên
  multi-item request (R9). Manifest derive từ tasks.md / acceptance_evals /
  TodoWrite≥3, KHÔNG parse DEV prompt keyword.
- **v0.21**: security hardening (Round 3 — H9/H10/H11) + CI fix
  (pytest-cov 7.x regression) + `make rebuild` reproducible bundle.
- **v0.19**: `gap_completeness_gate` Stop hook — chặn drip-feed.
- **v0.18**: AGENT-side disclosure sidecar (HTML + MD) auto-emitted
  after `/implement`.

## Worked example — log + classify user requests / ví dụ thực tế

**DEV's ask** (verbatim, paraphrased):

> "Log toàn bộ request của user được cấu hình. Với mỗi request, đo
>  dung lượng (request size + response size), thời gian phản hồi
>  (server-side processing time), và tốc độ mạng user (network
>  round-trip). Mục tiêu: phân biệt user chậm là do **server-side**
>  (response chậm) hay **client-side network** (latency cao)."
>
> *"Log every request of configured users. For each request, measure
>  payload size, server response time, and user network round-trip. Goal:
>  classify slowness as server-side (slow response) or client-side
>  (slow network)."*

This is a **classifier feature** — emits a tag (`server_slow` /
`network_slow` / `ok`) per request. The full DEV flow:

```
DEV: /plan log user requests + classify slowness as server vs network

    → Agent reads codebase (controllers, HTTP layer), drafts spec at
      .agent-toolkit/specs/<branch>/log-request-slowness/log-request-slowness.md
      with 8 sections + acceptance_evals skeleton, sets
      feature_kind: classification + eval_status: draft. STOPs.
      (Agent đọc codebase, draft spec, dừng — KHÔNG implement.)

DEV: /clarify log-request-slowness

    → Agent asks 1 question per turn (5-layer self-resolve first):
       Q1: Which network metric? options (a) TCP RTT (b) browser
           PerformanceObserver paint timing (c) custom beacon — Recommended (a)
       Q2: Threshold for "network slow" vs "server slow"?
           options (a) RTT > 300ms AND server_time < 100ms → network_slow
                   (b) server_time > 500ms regardless of RTT → server_slow
                   (c) ratio-based — Recommended (a) + (b) compound
       Q3 (only if needed): which users are "configured"? → from ir.config_parameter? per-group?
    → DEV answers each, agent refines spec inline + acceptance_evals get
      concrete probes:
        - us1-payload-recorded: postgres SELECT request_log WHERE user_id IN (...)
        - us2-server-tag-correct: real-data-proof Recipe 1 — inject
          sleep(2s) into handler → server_time should rise by ~2s → tag = server_slow
        - us3-network-tag-correct: real-data-proof Recipe 13 — leave server
          fast, simulate user network via Playwright route().continue_({delay: 500})
          → RTT should rise, server_time unchanged → tag = network_slow
    → Agent smoke-tests 1 probe (postgres connect + sample query) → OK.
    → Agent auto-fires /tasks log-request-slowness, emits tasks.md
      (e.g. T1 add request_log model, T2 hook BaseRequest dispatch,
      T3 compute classification, T4 expose via /web/log_metrics endpoint),
      STOPs for DEV review.
      (Agent test thử 1 probe, sinh tasks.md, dừng cho DEV review.)

DEV: (reads tasks.md, OK) /implement log-request-slowness

    → Agent auto-chains:
        /analyze → 7 checks PASS → READY
        autonomy ON
        T1 (model) → PASS · T2 (hook) → PASS · T3 (classify) → PASS · T4 (endpoint) → PASS
        /verify:
          - us1: 10 000 rows logged for 3 configured users — ✅ PASS
          - us2: sleep(2s) injected into handler, server_time delta = +2.1s,
                 tag flipped baseline=ok → perturbed=server_slow — ✅ CONSISTENT
          - us3: Playwright network delay 500ms, RTT delta = +480ms,
                 server_time unchanged, tag flipped ok → network_slow — ✅ CONSISTENT
          - Real-Data Proof Report attached (Distribution table + Falsification table)
          - verify_lint.py hook ran — all evals covered, Real-Data Proof
            section present → exit 0
        autonomy auto-OFF
        Spec status → verified
    → ✅ Implement done — DEV reads Verify Report, merges.
```

**Why this matters / Tại sao đáng học:**

- The classifier tag (`server_slow` / `network_slow`) is proven on
  REAL data via perturbation — not just "looks right by eyeball".
  Sleep-injection forces server-side latency; Playwright network
  delay forces client-side latency. Tag flip must match the
  perturbation direction — that's falsification, not assertion.
- *Tag (`server_slow` / `network_slow`) được chứng minh trên dữ liệu
  thật bằng perturbation — không phải "nhìn thấy đúng". Inject sleep
  ép server chậm; Playwright delay ép network chậm. Tag phải flip
  theo perturbation — đó là falsification, không phải assertion.*
- See [`real-data-proof/SKILL.md`](templates/cursor/skills/_common/real-data-proof/SKILL.md)
  + [worked example for BLOCK/ASYNC pattern](templates/cursor/skills/_common/real-data-proof/references/block-async-worked-example.md)
  for the canonical 4-step contract.

## Quick comparison

|                                  | agent-toolkit | spec-kit | mattpocock/skills | ECC | Aider |
|---|:---:|:---:|:---:|:---:|:---:|
| Spec-driven 5-phase workflow     | ✅ | ✅ | partial | partial | ❌ |
| Hook-level mechanical enforcement | **✅** | ❌ | partial | partial | ❌ |
| Real-data MCP verify gate        | **✅** | ❌ | ❌ | partial | ❌ |
| Stack-preset overlay system      | **✅** | partial | ❌ | ❌ | ❌ |
| Telemetry + bypass audit         | **✅** | ❌ | ❌ | partial | ❌ |
| Bilingual docs (EN + VN)         | **✅** | ❌ | ❌ | ❌ | ❌ |
| Git-state agent guardrail        | **✅** | ❌ | ✅ | ❌ | ❌ |
| Drip-feed prevention (v0.19)     | **✅** | ❌ | ❌ | ❌ | ❌ |
| AGENT-side disclosure sidecar (HTML+MD, v0.18) | **✅** | ❌ | ❌ | partial | ❌ |

## Production status

Toolkit is in **active use** on a real Odoo 12 Enterprise
workspace since May 2026. As illustrative figures from local dogfooding
(not a benchmark), a typical session shows ~57 hook fire-events, ~26%
block rate, and ~3.5% bypass rate.
**30+ hooks** active, **948 unit tests** (as of v0.30.0) in CI (matrix: Ubuntu / macOS /
Windows × Python 3.8 / 3.10 / 3.12 — all green).
The reported coverage % measures `setup.py` + `lib/` only; the enforcement hooks (`templates/claude/hooks/`, ~11k LOC) are ruff-lint-checked and behavior-tested via subprocess (`tests/test_hooks.py` + per-hook suites) but are not line-coverage-measured because they run as subprocesses.

> 🤖 **AI agents installing into a project**: Read
> [`AI_REBUILD_CHECKLIST.md`](AI_REBUILD_CHECKLIST.md) BEFORE invoking
> `setup.py init` or `setup.py update`. The 4-phase Q&A protocol is
> mandatory — without it the toolkit silently inherits defaults from
> whatever preset and you ship a misconfigured project. Also read
> [`AGENTS.md`](AGENTS.md) for the hard rules.

> 🇻🇳 **Tiếng Việt:** giới thiệu tóm tắt ở
> [§ Tiếng Việt](#-tiếng-việt) cuối README; full guide ở [USAGE.md](USAGE.md).

## Architecture (1 picture)

```
                    ┌─────────────────────────────────────────┐
                    │       DEV (intent owner)                │
                    │  /plan  /clarify  /implement            │
                    └────────────────┬────────────────────────┘
                                     │ slash commands
                                     ▼
              ┌──────────────────────────────────────────────┐
              │           CLAUDE CODE HARNESS                │
              │                                              │
              │  SessionStart ─► [session_brief]             │
              │     │ inject: invariants, ADRs, hook health  │
              │     ▼                                        │
              │  UserPromptSubmit ─► [intent_router]         │
              │     │ suggest skills, write last_intent      │
              │     ▼                                        │
              │  PreToolUse(Bash) ─► [git_guardrails]  ❌DENY │
              │  PreToolUse(Edit) ─► [invariant_guard]  ❌DENY │
              │                  ─► [analyze_halt_gate]      │
              │                  ─► [spec_first_guard]       │
              │     │                                        │
              │     ▼                                        │
              │  PostToolUse(Edit) ─► [tdd_runner]           │
              │                   ─► [verification_loop]     │
              │                   ─► [auto_test_runner]      │
              │                   ─► [auto_run_probes]  ◄─── │
              │     │                                  │     │
              │     ▼                                  │MCP  │
              │  Stop ─► [evidence_audit]   ❌BLOCK ◄──┤probe│
              │       ─► [clarification_gate_enforcer] ❌BLOCK │
              │       ─► [gap_completeness_gate]  ❌BLOCK    │
              │             (chặn drip-feed v0.19)           │
              │       ─► [scope_completeness_gate] ❌BLOCK   │
              │             (chặn partial-done v0.23)        │
              │       ─► [verify_lint]      ❌BLOCK          │
              │       ─► [post_edit_verify_gate] ❌BLOCK     │
              │       ─► [debug_sentry]     ❌BLOCK          │
              │       ─► [implement_notes_gate] ⚠️WARN       │
              │             (md+html sidecar v0.18)          │
              │       ─► [verify_lint_scope]  ❌BLOCK        │
              └──────────────────────────────────────────────┘
                                     │ tool call ▼
              ┌──────────────────────────────────────────────┐
              │             MCP SERVERS (per preset)         │
              │                                              │
              │  codebase ◄─► postgres ◄─► realdata_test     │
              │   (search)    (DB read)    (run module test) │
              │                                              │
              │  + jira (ticket), gitlab (CI), playwright    │
              └──────────────────────────────────────────────┘

   ─────── 3-tier rule (cross-linked, auditable) ───────

         ┌─────────────────────────────────────────┐
         │  1. CONSTITUTION  (slow-changing)        │ ◄─── /constitution
         │     .agent-toolkit/constitution.md       │
         │     project-wide principles              │
         └───────────────┬─────────────────────────┘
                         │ amendments cite
                         ▼
         ┌─────────────────────────────────────────┐
         │  2. ADR LOG  (append-only WHY)          │ ◄─── /adr-add  /decide
         │     .agent-toolkit/decision-log.md      │
         │     one entry per durable decision      │
         └───────────────┬─────────────────────────┘
                         │ enforces via
                         ▼
         ┌─────────────────────────────────────────┐
         │  3. INVARIANTS  (mechanical patterns)   │ ◄─── /inv-add
         │     .agent-toolkit/invariants.json      │     /bug-to-test
         │     regex/AST patterns — hooks DENY     │
         │     edits that strip them               │
         └─────────────────────────────────────────┘
```

[ASCII for browser-friendly inline render; the same diagram in
mermaid/excalidraw form ships in `docs/architecture.md` (planned).]

## How to use — DEV vs AGENT split / DEV làm gì, AGENT làm gì

The toolkit splits responsibility cleanly so DEV stays in control of
**intent** (what to build, what's correct) while AGENT handles
**execution** (implement, run probes, prove on real data).

Toolkit tách rõ trách nhiệm: **DEV** giữ quyền quyết định *muốn build gì,
correct là gì*; **AGENT** lo phần *thực thi — viết code, chạy probe,
chứng minh trên dữ liệu thật*.

### What DEV does — **3 manual steps** / DEV chỉ làm **3 bước**

| Step | Command | Purpose / Mục đích |
|------|---------|--------------------|
| **1** | `/plan <feature description>` | Turn idea into structured spec (8 sections + acceptance_evals skeleton). Spec saved at `.agent-toolkit/specs/<branch>/<slug>.md`. *Biến yêu cầu → spec có cấu trúc.* |
| **2** | `/clarify <slug>` | Answer 0-3 questions per turn until all Open Questions close + every acceptance eval gets a concrete grader + probe. Agent auto-fires `/tasks <slug>` after final "done", then **STOPs**. *Trả lời câu hỏi đến khi mọi GAP đóng; agent tự sinh tasks.md rồi dừng.* |
| **3** | Review `tasks.md` → `/implement <slug>` | Eyeball the task breakdown (≤ 30 LOC per task, each with Touches/Acceptance/Verification/Risk). When happy, type `/implement` to authorize the auto-chain. *Duyệt tasks.md rồi gõ `/implement` để bật autonomy.* |

That's it. DEV does NOT manually run `/analyze`, `/tasks`, or `/verify`
— those fire automatically. *DEV không cần gõ tay `/analyze`, `/tasks`,
`/verify` — agent tự chạy.*

### What AGENT does automatically — **5 auto-chained phases** / AGENT tự làm **5 phase auto-chain**

After DEV types `/implement <slug>`, the agent chains these steps under
autonomy (default 4h, configurable via `--until`). *Sau khi DEV gõ
`/implement`, agent tự chạy chuỗi sau dưới autonomy (mặc định 4h).*

```
DEV: /implement <slug>
        ↓
[agent auto-chain — DEV không cần can thiệp]
        ↓
1. /analyze   →  7 cross-artifact checks (spec ↔ tasks ↔ evals ↔ invariants ↔ constitution ↔ paths ↔ verification concreteness).
              →  Verdict READY / WARN / HALT. HALT blocks Edit/Write
                 via `analyze_halt_gate` PreToolUse hook until DEV fixes.

2. autonomy ON →  `.agent-toolkit/.autonomy_active.json` written with
                  approved scopes + still-blocked actions.

3. Execute tasks T1 → T2 → … sequentially:
   - Read Touches files, Edit them.
   - Run Verification step (MCP / shell command).
   - Record PASS/FAIL per task in tasks.md.
   - On FAIL → 3-option prompt to DEV: (r)etry / (s)kip / (a)bort.

4. /verify    →  Probes real data in parallel (postgres / realdata_test /
                 Playwright MCP). Each User Story → 1 row in
                 PASS/GAP/BLOCKER table. Re-uses `acceptance_evals`
                 from spec frontmatter — does NOT re-design probes.
              →  For classifier features (`feature_kind: classification`):
                 mandatory Real-Data Proof — acquire real data →
                 distribute by tag → perturb-test each tag (sleep-inject /
                 heavy-query / fault inject) → revert.

5. Report back →  ✅ Implement done · Tasks N/N PASS · Verify verdict ·
                  Spec status → verified | gaps-found | blocked.
                  Autonomy auto-OFF if all PASS.
```

> Worked example đã được promote lên top-level section [Worked example](#worked-example--log--classify-user-requests--ví-dụ-thực-tế) (ngay sau What's new) — xem reference ở đó cho DEV flow đầy đủ.

## What you get

For any project where you run `setup.py init`:

- **`.codex/`** — Odoo MCP server implementations (codebase, postgres,
  realdata_test, jira; optional read-only `gitlab` CI server) + canonical
  decisions registry + 120+ hook tests
- **`.cursor/rules/`** — Cursor IDE rules (always-apply) for the chosen
  Odoo version
- **`.cursor/skills/`** — Spec Kit workflow skills (plan-feature,
  clarify, tasks-breakdown, analyze-artifacts, verify-feature) + Odoo
  stack skills (code-patterns, codebase-discovery, data-verification,
  debug-troubleshoot, deterministic-answers, jira-workflow,
  module-scaffold, tdd)
- **`.claude/`** — slash commands (`/plan`, `/clarify`, `/tasks`,
  `/analyze`, `/implement`, `/verify`, etc.) + enforcement hooks
  (invariant_guard, evidence_audit, intent_router, verify_lint…)
- **`.agent-toolkit/`** — per-project state: `constitution.md`,
  `decision-log.md` (ADRs), `invariants.json`, `acceptance-probes.json`,
  spec dir `.agent-toolkit/specs/<branch>/<slug>.md`
- **`.cursor/mcp.json`** + **`.mcp.json`** — auto-generated MCP wiring
  with absolute paths
- **`AGENTS.md`** + **`CLAUDE.md`** — agent entry-points pre-filled with
  project facts
- **`~/.claude/projects/<encoded>/memory/*.md`** — Claude Code memory
  seeded with workspace + Python paths
- **`.codex/mcp.local.env`** — credentials template (you fill the secrets)
- **`.gitignore`** snippets

## Spec-driven workflow (Spec Kit-aligned)

DEV chỉ làm **3 lệnh** trong session Claude Code / Cursor:

```
DEV:    /plan <feature>  →  /clarify <slug>
            ↓                    ↓
        spec.md draft       spec refined + acceptance_evals locked

[agent auto-fires]
        /tasks <slug>   →   STOP (DEV reviews tasks.md)
                                ↓
DEV:    /implement <slug>
                                ↓
[agent auto-chain]
        /analyze  →  execute tasks  →  /verify  →  báo cáo DEV
```

Specs lưu **branch-scoped**: `.agent-toolkit/specs/<branch>/<slug>.md`.
Mỗi phase có skill + slash command riêng. Xem
[USAGE.md §5](USAGE.md) cho ví dụ end-to-end.

## Quick start

```bash
# Clone toolkit once on any machine
git clone <toolkit-repo> ~/agent-toolkit

# Install into an Odoo project (pick the preset matching the Odoo major version)
python ~/agent-toolkit/setup.py init /path/to/your/project \
    --preset odoo-12 --yes

# Edit credentials
$EDITOR /path/to/your/project/.codex/mcp.local.env

# Restart Cursor / Claude Code → MCP servers load automatically
# In Claude Code, start a feature with:  /plan <feature description>
```

## Available presets

```bash
python setup.py list-presets
```

**10 presets** ship out of the box (9 Odoo versions + 1 generic fallback):

| Preset | Stack | Python | Frontend | Rules / Memory |
|--------|-------|--------|----------|----------------|
| `odoo-12` | Odoo 12, `@api.multi` era | 3.8 | QWeb + jQuery | _common + odoo-12 |
| `odoo-13` | Odoo 13, `@api.multi` era | 3.6+ | QWeb + jQuery | _common + odoo-12 (legacy shared) |
| `odoo-14` | Odoo 14, `@api.multi` era | 3.7+ | QWeb + jQuery | _common + odoo-12 (legacy shared) |
| `odoo-15` | Odoo 15, transitional | 3.8+ | QWeb + OWL 1.x | _common + odoo-12 (legacy shared) |
| `odoo-16` | Odoo 16, modern ORM | 3.10+ | OWL 2.x | _common + odoo-17 (modern shared) |
| `odoo-17` | Odoo 17, modern ORM, `@api.model_create_multi` | 3.10+ | OWL framework | _common + odoo-17 |
| `odoo-18` | Odoo 18, modern ORM | 3.10+ | OWL framework | _common + odoo-17 (modern shared) |
| `odoo-19` | Odoo 19, modern ORM | 3.11+ | OWL framework | _common + odoo-17 (modern shared) |
| `odoo-20` | Odoo 20 (expected GA late 2026) | 3.11+ | OWL framework | _common + odoo-17 (modern shared) |
| `generic` | Plain Python — fallback for stack-agnostic experiments only. **Not** the recommended preset for Odoo work. | — | — | _common |

Default `addon_roots` for Odoo presets: `addons` / `custom_addons` /
`enterprise`. MCP servers: `codebase` + `postgres` + `realdata_test`.
The Odoo 13-20 presets (besides 12 and 17) are **stub-extends** that
share rules/memory packs with their nearest neighbor — fork the preset
file to capture version-specific deltas.

> **Project-specific overlays**: real projects almost always have extra
> addon roots, a custom `odoo-bin` path, internal JIRA endpoints,
> Enterprise-only modules, etc. Keep those in a **private preset** that
> `extends` one of the public presets — see
> [`templates/agent_toolkit/PORTING.md`](templates/agent_toolkit/PORTING.md)
> for the recipe. Don't fork the toolkit just to bake in your defaults.

The toolkit's *design* is stack-agnostic — you can drop a new preset
JSON into `presets/` (e.g. for Django, Rails) and matching
`templates/cursor/rules/<name>/` + `templates/memory/<name>/`. **In
practice the shipped presets target Odoo**; the rules, skills,
canonical decisions, and MCP servers are tuned for Odoo conventions.

### Shipped skills

**Spec Kit workflow skills** (`_common`, every preset):

| Skill | Phase | What it does |
|-------|-------|--------------|
| `plan-feature` | 1 — SPECIFY | Turn a feature request into an 8-section spec at `.agent-toolkit/specs/<branch>/<slug>.md` + emit `acceptance_evals` skeleton. |
| `clarify` | 2 — CLARIFY | One Q per turn until every Open Question closes; refine `acceptance_evals` (set grader/layer/expected, smoke-test); auto-fire `/tasks`. |
| `tasks-breakdown` | 3 — TASKS | Emit `tasks.md` next to spec — Touches / Acceptance / Verification / Risk per task. STOPs for DEV review. |
| `analyze-artifacts` | 3.5 — ANALYZE | 7 cross-artifact checks (story / eval coverage + invariant + constitution + path realism + verification concreteness) before implement. |
| `verify-feature` | 5 — VERIFY | Real-data probes via realdata_test/postgres/Playwright MCP in parallel; emit Verify Report (PASS/GAP/BLOCKER per User Story). |

**Guardrails** (`_common`, every preset):

| Skill | What it does |
|-------|--------------|
| `clarification-gate` | Pre-flight 3-block (UNDERSTANDING / ASSUMPTIONS / QUESTIONS) before any action verb. |
| `code-review` | Exhaustive single-pass review — surfaces ALL Blocker + Medium + Low findings in one session, with a reproducible PROOF line. |
| `doubt-driven-review` | CLAIM → EXTRACT → DOUBT → RECONCILE overlay before reporting non-trivial findings. |
| `claim-falsification` | 15-recipe catalog for perturb-test (BLOCK/ASYNC, caching, idempotency, atomicity, …). |
| `classifier-output-audit` | Long-tail audit for classification features (sample K rows, re-derive expected tag, find mismatch groups). |
| `karpathy-guidelines` | Operating-principle skill (think before coding, simplicity, surgical changes, MCP-before-files). |

**Odoo skills** (auto-included by every Odoo preset — **14 skills**, all **version-aware**):

Each skill's Step 0 reads `__manifest__.py` from the target module, then
loads the matching `references/odoo-<N>-*.md`. One skill folder covers
Odoo 12 → 20 (and future 21+ — just add a reference file).

*Core workflow* (Spec Kit + day-to-day):

| Skill | What it does |
|-------|--------------|
| `odoo-code-review` | Exhaustive review. Cascade: 12 standalone, 17→18→19→20. |
| `odoo-code-patterns` | Canonical patterns (model / wizard / view / OWL). Version-specific `references/odoo-<N>-patterns.md`. |
| `odoo-codebase-discovery` | MCP discovery (`discover_modules`, `read_manifest`, …). Version-agnostic. |
| `odoo-debug-troubleshoot` | Quick-fix tables. Version-specific `references/odoo-<N>-pitfalls.md`. |
| `odoo-tdd` | Red-Green-Refactor + perturb-test routing. Version-specific `references/odoo-<N>-tdd-pitfalls.md`. |

*Multi-edition* (v0.22 — Community / Enterprise / multi-company):

| Skill | What it does |
|-------|--------------|
| `odoo-community-patterns` | Community-edition-only conventions; flag Enterprise-only modules/fields. Version-aware. |
| `odoo-enterprise-patterns` | Enterprise-only conventions (studio, marketing automation, accounting full). Version-aware. |
| `odoo-multi-company` | Multi-company / multi-currency record rules + `company_dependent` fields. Version-aware. |

*Frontend* (OWL):

| Skill | What it does |
|-------|--------------|
| `odoo-owl-components` | OWL component patterns (12 jQuery fallback, 15+ OWL 1.x, 17+ OWL framework). Version-specific. |

*Performance*:

| Skill | What it does |
|-------|--------------|
| `odoo-performance` | N+1, slow computed fields, prefetch, `read_group` tuning. 10 cross-version recipes (12 / 17 / 18 references). |

*Operations*:

| Skill | What it does |
|-------|--------------|
| `odoo-jira-workflow` | JIRA MCP tools. Version-agnostic. |
| `odoo-module-scaffold` | New module scaffold. Version-specific `references/odoo-<N>-scaffold.md`. |

*Discovery*:

| Skill | What it does |
|-------|--------------|
| `odoo-data-verification` | Real-DB ORM probes via `realdata_test` MCP. Version-agnostic. |
| `odoo-deterministic-answers` | `canonical_decisions.json` registry workflow. Version-agnostic. |

**Adding support for a new Odoo major** (e.g. 21): drop 5 reference
files (one per version-specific skill), optionally add `presets/odoo-21.json`
extending `odoo-17`. No skill body edits, no preset edits in shipped skills.
Full recipe: see [Khi Odoo 21+ ra mắt — chỉ cần thêm files](#khi-odoo-21-ra-mắt--chỉ-cần-thêm-files) below.

## CLI

```bash
# List presets
python setup.py list-presets

# Interactive install (prompts for paths + preset)
python setup.py init /path/to/project

# Non-interactive
python setup.py init /path/to/project \
    --preset odoo-12 \
    --python /path/to/venv/bin/python \
    --psql /usr/bin/psql \
    --project-name "My Project" \
    --yes

# Dry-run
python setup.py init /path/to/project --preset odoo-17 --dry-run

# Refresh templates in an installed project (preserves mcp.local.env)
python setup.py update /path/to/project
```

## Layout

```
agent-toolkit/
├── setup.py                  # CLI entry (init / update / list-presets)
├── lib/
│   └── installer.py          # preset loader + templating + detect helpers (__version__)
├── presets/
│   ├── odoo-12.json          # generic Odoo 12
│   ├── odoo-17.json          # generic Odoo 17
│   └── generic.json          # plain-Python fallback (not recommended for Odoo)
├── templates/
│   ├── codex/
│   │   ├── mcp_servers/                      # 5 MCP impls (codebase, postgres, realdata_test, jira, common)
│   │   ├── start_*_mcp.py                    # stdio launcher wrappers per server
│   │   ├── canonical_decisions.json          # default seed (Odoo 12)
│   │   ├── canonical_decisions.generic.json
│   │   ├── canonical_decisions.odoo-17.json
│   │   ├── precommit_hooks/                  # invariant_guard, credential_guard, probe_coverage, auto_falsify
│   │   ├── tools/                            # falsify.py CLI, agent_toolkit_init.py
│   │   ├── lint_verify_report.py             # /verify Step 8 coverage check
│   │   ├── config.toml.example
│   │   ├── mcp.local.env.example
│   │   └── tests/                            # 120+ hook unit tests
│   ├── claude/
│   │   ├── settings.json                     # permissions + hooks + env wiring
│   │   ├── hooks/                            # session_brief, intent_router, invariant_guard, evidence_audit,
│   │   │                                     #  verify_lint, verify_nudge, post_edit_verify_gate, tdd_runner,
│   │   │                                     #  verification_loop, probe_autostub, debug_sentry, _audit/ pkg
│   │   └── commands/                         # slash commands: /plan /clarify /tasks /analyze /implement
│   │                                         #  /verify /adr-add /inv-add /inv-list /probe-add /probe-coverage
│   │                                         #  /run-probes /eval-define /eval-backfill /bug-to-test /tdd
│   │                                         #  /recall /review /test-env /stop-autonomy
│   ├── cursor/
│   │   ├── rules/
│   │   │   ├── _common/      # karpathy, decision-consistency, mcp-routing, audit-methodology
│   │   │   ├── odoo-12/      # backend, generic, project-context
│   │   │   └── odoo-17/      # backend, generic, project-context, data-verification
│   │   └── skills/
│   │       ├── _common/      # Spec Kit chain (plan-feature, clarify, tasks-breakdown,
│   │       │                 #  analyze-artifacts, verify-feature) + guardrails
│   │       │                 #  (clarification-gate, code-review, doubt-driven-review,
│   │       │                 #  claim-falsification, classifier-output-audit, karpathy-guidelines)
│   │       ├── odoo/         # odoo-code-review (version-aware 12/17/18/19/20)
│   │       ├── odoo-12/      # 8 stack skills (code-patterns, codebase-discovery, data-verification,
│   │       │                 #  debug-troubleshoot, deterministic-answers, jira-workflow,
│   │       │                 #  module-scaffold, tdd)
│   │       └── odoo-17/      # 4 stack skills (codebase-discovery, code-patterns,
│   │                         #  data-verification, module-scaffold)
│   ├── memory/
│   │   ├── _common/          # user_profile, feedback_*, reference_karpathy, MEMORY.md
│   │   ├── odoo-12/          # project_workspace, project_mcp_routing
│   │   └── odoo-17/          # project_workspace, project_mcp_routing
│   ├── agent_toolkit/        # files installed to project's .agent-toolkit/
│   │   ├── constitution.md   # toolkit principles + project hard rules
│   │   ├── decision-log.md   # ADR template
│   │   ├── invariants.json
│   │   ├── acceptance-probes.json
│   │   ├── intent_map.json
│   │   ├── coverage_config.json
│   │   ├── tdd.json, verification.json, debug.json
│   │   ├── README.md, QUICKSTART.md, PORTING.md
│   ├── pre-commit-config.yaml.tmpl
│   ├── AGENTS.md             # template with {{PLACEHOLDERS}}
│   └── CLAUDE.md
├── tests/                    # toolkit-level pytest suite (installer, e2e, hooks, snapshot)
├── docs/
│   ├── AUDIT_HISTORY.md      # 60+ findings across 3 audit rounds + reviewer + Round 4 (v0.21/v0.22)
│   ├── precommit-setup.md
│   └── troubleshooting.md
├── .github/workflows/test.yml # GitHub Actions matrix CI + lint + coverage
├── .gitlab-ci.yml            # GitLab CI mirror (test + lint + coverage stages)
├── Makefile                  # one-command targets: install / test / coverage / rebuild
├── requirements-dev.txt      # dev deps (pytest, pytest-cov, ruff) — no version pins required
├── REBUILD.md                # maintainer guide: clone → verify → push → tag → release
├── AGENTS.md                 # toolkit's own AI agent rules
├── AI_REBUILD_CHECKLIST.md   # 4-phase Q&A protocol for init/update (consumer side)
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE                   # MIT
├── NOTICE                    # upstream attribution
├── SECURITY.md
├── README.md                 # this file
└── USAGE.md                  # detailed VN user guide
```

## Placeholders (filled by setup.py)

Templates use `{{KEY}}` substitution. Available keys:

| Placeholder | Source |
|-------------|--------|
| `{{WORKSPACE_ROOT}}` | target install path |
| `{{PROJECT_NAME}}` | `--project-name` flag (defaults to dir name) |
| `{{PYTHON_BIN}}` | detected or `--python` flag |
| `{{PSQL_BIN}}` | detected or `--psql` flag |
| `{{STACK_LABEL}}`, `{{STACK_LANGUAGE}}`, `{{STACK_FRAMEWORK}}`, `{{STACK_LANGUAGE_VERSION}}`, `{{STACK_FRAMEWORK_VERSION}}` | from preset |
| `{{ADDON_ROOTS}}` | preset list (rendered as `- item` bullets in Markdown) |
| `{{ADDON_ROOTS_CSV}}` | preset list joined with `, ` (for inline strings) |
| `{{MCP_SERVERS}}` | preset list |
| `{{MCP_SERVERS_CSV}}` | preset list joined with `, ` |
| `{{DEFAULT_DB}}`, `{{DEFAULT_PG_PORT}}` | preset |
| `{{RESPONSE_LANGUAGE}}` | preset |
| `{{PRESET_NAME}}` | the preset chosen |

## Khi Odoo 21+ ra mắt — chỉ cần thêm files

Toolkit hiện đã ship **14 Odoo skills version-aware** (Odoo 12 → 20). Khi
Odoo 21 (hoặc 22, 23…) ra mắt, **không cần sửa skill body, không cần
sửa preset gốc, không cần sửa intent_router**. Chỉ cần drop 5 file
reference vào đúng chỗ — Step 0 của mỗi skill tự đọc `__manifest__.py`
của module rồi load reference tương ứng.

### Bước 1 — Drop 5 reference files (BẮT BUỘC)

Đây là phần duy nhất *bắt buộc*. Toolkit tự cascade `17 → 18 → 19 → 20`,
nên nếu Odoo 21 gần giống 20 anh có thể copy nội dung `odoo-20-*.md`
sang làm baseline rồi chỉnh delta.

```
templates/cursor/skills/odoo/
├── odoo-code-patterns/references/odoo-21-patterns.md
├── odoo-code-review/references/odoo-21-rules.md
├── odoo-debug-troubleshoot/references/odoo-21-pitfalls.md
├── odoo-module-scaffold/references/odoo-21-scaffold.md
└── odoo-tdd/references/odoo-21-tdd-pitfalls.md
```

> 4 skills còn lại (`odoo-codebase-discovery`, `odoo-data-verification`,
> `odoo-deterministic-answers`, `odoo-jira-workflow`) là 100% version-agnostic
> — không có folder `references/`, không cần đụng đến.

### Bước 2 — Optional: thêm preset `odoo-21` (chỉ nếu muốn `--preset odoo-21`)

```json
// presets/odoo-21.json
{
  "description": "Odoo 21 stack — Python 3.12+, OWL, recordset-by-default",
  "extends": "odoo-17",
  "stack_label": "Odoo 21",
  "stack": {
    "language_version": "3.12",
    "framework_version": "21"
  }
}
```

Nếu bỏ qua bước này — toolkit vẫn chạy đúng với preset `odoo-17` (hoặc
`odoo-12`); Step 0 của skill đọc `__manifest__.py` thấy `'version':
'21.0.x.x.x'` rồi load `odoo-21-*.md` reference. **Preset chỉ phục vụ
mục đích default config (Python version, MCP servers), không quyết định
skill nào được dùng.**

### Bước 3 — Optional: rules + memory + canonical_decisions

Hoàn toàn optional (giống Bước 2 — bỏ qua được, fallback về `odoo-17`):

```
templates/cursor/rules/odoo-21/         # nếu Cursor IDE cần rules riêng cho v21
templates/memory/odoo-21/               # nếu cần memory pack stack-specific
templates/codex/canonical_decisions.odoo-21.json
```

### Bước 4 — Bump toolkit version

```python
# lib/installer.py
__version__ = '0.6.0'  # bump khi schema_version đổi hoặc CLI flags break compat
```

Plus `CHANGELOG.md` entry.

### Tóm tắt — "Odoo 21 support trong 30 phút"

| File | Bắt buộc? | Effort |
|------|----------|--------|
| 5 × `references/odoo-21-*.md` | ✅ YES | 20 phút (copy `odoo-20-*.md` + chỉnh delta) |
| `presets/odoo-21.json` | ⚠️ Optional | 2 phút |
| `templates/cursor/rules/odoo-21/*.mdc` | ⚠️ Optional | tùy delta |
| `templates/memory/odoo-21/*.md` | ⚠️ Optional | tùy delta |
| `templates/codex/canonical_decisions.odoo-21.json` | ⚠️ Optional | tùy delta |
| Skill body / intent_router / preset cũ | ❌ NO TOUCH | 0 phút |

**Verify:**

```bash
# Vẫn pass đầy đủ test sau khi thêm Odoo 21
python -m pytest tests/ -v   # 72+ pass

# Install thử vào project Odoo 21
python setup.py init /path/to/odoo21-proj --preset odoo-21 --yes
# (hoặc --preset odoo-17 nếu chưa tạo odoo-21.json — vẫn chạy đúng)
```

> **Non-Odoo stacks (Django, Rails, FastAPI…)**: technically supported
> via the same preset mechanism, but you'll need to author the
> stack-specific rules, skills, MCP servers, and canonical decisions
> yourself. See `templates/agent_toolkit/PORTING.md` for the porting
> guide. The shipped Odoo MCP servers (`realdata_test`, `jira`) are
> Odoo-specific and won't transfer.

## Re-seeding memory after edits

When the agent saves new memory in your live install
(`~/.claude/projects/<encoded>/memory/*.md`), to make it portable for
the next install:

1. Copy generic learnings (cross-project) into
   `templates/memory/_common/` with `{{WORKSPACE_ROOT}}` placeholders
   replacing absolute paths.
2. Copy stack-specific learnings into `templates/memory/<stack>/`.
3. Commit toolkit. Next `setup.py init` will seed the new memory.

## Per-preset canonical decisions registry

`canonical_decisions.json` is the single source of truth for recurring "how do we
do X" answers. The toolkit ships per-preset starter registries:

- `templates/codex/canonical_decisions.json` — default seed (Odoo 12).
- `templates/codex/canonical_decisions.<preset>.json` — preset-specific seed
  (e.g. `canonical_decisions.odoo-17.json`).

Install behaviour:

- On **fresh install**, the preset-specific seed is rendered with placeholders
  filled and copied as `.codex/canonical_decisions.json`.
- On **update** or any subsequent install, an existing
  `.codex/canonical_decisions.json` is **never overwritten** (mode
  `SKIP_EXISTS`) — the project owner curates entries locally.

To add a new preset's registry, drop `canonical_decisions.<preset>.json` next
to the default file and the installer will pick it up automatically.

## Verifying an install

Lightweight wrapper tests (offline):

```bash
python /path/to/project/.codex/tests/test_mcp_wrappers.py
# Odoo 12:                  Ran 27 tests — OK
# Odoo 17:                   Ran 27 tests — OK (skipped=6, JIRA tests skipped)
```

Full hook suite (run from the project after install):

```bash
python -m pytest /path/to/project/.codex/tests/hooks/ -v
# Expected: 120+ tests pass
```

Toolkit-level pytest (run from the toolkit repo):

```bash
python -m pytest /path/to/agent-toolkit/tests/ -v
# Expected: 72+ tests pass (installer / e2e / snapshot / hooks)
```

## Why JSON presets (not YAML)

Stays dependency-free — no `pip install pyyaml` needed. JSON is verbose
but unambiguous, and the toolkit installer is < 300 lines. If you prefer
YAML, install pyyaml and drop a `.yaml` file into `presets/`; the loader
prefers JSON when both exist.

## What's NOT in the toolkit

- Per-project ad-hoc probes / dev scripts (those belong in your project)
- `.codex/audit_findings_locked.md` (project-specific)
- Real credentials (always machine-local in `.codex/mcp.local.env`)
- Python venv binary (project-specific install)
- Postgres data (project-specific)

## Credits & References

This toolkit is original work but stands on the shoulders of several
upstream projects + academic ideas. Adopting / extending any of these
in your own toolkit is encouraged — check each license.

### Upstream skill repos

- **[github/spec-kit](https://github.com/github/spec-kit)** — the
  5-phase Spec Kit workflow (`SPECIFY → CLARIFY → TASKS → ANALYZE →
  IMPLEMENT → VERIFY`) that this toolkit's slash-command surface mirrors.
  We added a 6th phase (`/verify` real-data probes via MCP) and renamed
  the entry point from `/specify` → `/plan` to match the DEV mental model.

- **[mattpocock/skills](https://github.com/mattpocock/skills) (MIT)** —
  Matt Pocock's open skill library. We adopted the structural ideas
  from these specific skills (cite paths kept in each SKILL.md
  "Reference" section):
  - [`engineering/to-prd`](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-prd/SKILL.md)
    — basis for `plan-feature/SKILL.md`.
  - [`engineering/zoom-out`](https://github.com/mattpocock/skills/tree/main/skills/engineering/zoom-out)
    — feeds the `plan-feature` discovery loop.
  - [`productivity/grill-me`](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me)
    + [`engineering/grill-with-docs`](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs)
    — basis for `clarify/SKILL.md` (1-Q-per-turn interview loop).

- **[forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)**
  — local mirror of Andrej Karpathy's behavioural guidelines (think
  before coding, smallest change, surgical edits, goal-driven
  verification). Sourced verbatim into `karpathy-guidelines/SKILL.md`
  and `templates/memory/_common/reference_karpathy.md`.

### Academic / methodology references

- **[Karl Popper](https://en.wikipedia.org/wiki/Falsifiability)
  *Logic of Scientific Discovery* (1959)** — "a claim that cannot be
  shown false also cannot be shown true". Backbone of
  `claim-falsification/SKILL.md` and `real-data-proof/SKILL.md` —
  every property claim must come with a perturbation that *could*
  refute it on real data.

- **Property-based testing tradition** —
  [Hypothesis](https://hypothesis.readthedocs.io/) (Python) +
  [QuickCheck](https://hackage.haskell.org/package/QuickCheck) (Haskell).
  The "perturb input → invariant must hold" frame in
  `claim-falsification` is the runtime analogue.

- **[Andrej Karpathy](https://karpathy.ai/)** — the
  *Think Before Coding / Simplicity / Surgical Changes / Goal-Driven*
  formulation that the toolkit treats as a hard invariant for every
  skill body and every agent turn.

### Runtime platforms the toolkit installs into

- **[Claude Code](https://docs.claude.com/en/docs/claude-code)** (Anthropic)
  — primary target; hooks (`templates/claude/hooks/*.py`), slash commands
  (`templates/claude/commands/*.md`), and `settings.json` are all Claude
  Code-shaped.

- **[Cursor IDE](https://cursor.com/)** — secondary target; the
  toolkit ships always-apply rules under `.cursor/rules/` and on-demand
  skills under `.cursor/skills/`.

- **[Codex CLI](https://github.com/openai/codex)** — supported via the
  same MCP servers (codebase, postgres, realdata_test, jira) +
  `.codex/` directory layout.

- **[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)**
  (Anthropic) — the protocol every shipped MCP server speaks
  (`codebase_server.py`, `postgres_server.py`, `jira_server.py`,
  `realdata_test_server.py`).

### Author + maintenance

- **Author / maintainer**: **Thang Vo** — Senior Developer (Odoo & Agent AI)
  - Contact: [ducthangict.dhtn@gmail.com](mailto:ducthangict.dhtn@gmail.com)
  - Zalo: [0989 464 344](tel:+84989464344) (`ictlucky.dhtn`)
  - Original work; toolkit is in active use on production Odoo 12 + 17
    Enterprise workspaces.
- **Issues / contributions**: open an issue on the toolkit repo or
  reach out via the maintainer contact above.
- **License**: toolkit is **MIT** — see [`LICENSE`](LICENSE) at root.
  Third-party MIT attribution (mattpocock/skills, github/spec-kit,
  affaan-m/everything-claude-code, andrej-karpathy-skills) is
  consolidated in [`NOTICE`](NOTICE). Original Python code in `lib/`,
  `setup.py` carries `# SPDX-License-Identifier: MIT` at file top;
  skills/hooks/templates inherit the toolkit LICENSE unless an in-file
  `license:` frontmatter states otherwise.

---

## 🇻🇳 Tiếng Việt

**Hạ tầng AI agent (Claude Code / Cursor / Codex) cho spec-driven dev — cài 1 lần, chạy mọi project.**

Agent AI hay ship code lỗi khi không có gì **ép cơ học**. Toolkit này biến
6 rule thành un-skip-able: chặn xóa invariant, audit claim không có proof,
verify trên data thật, chặn agent commit/push, banner cảnh báo kill-switch,
alert khi bypass quá nhiều.

### Cài đặt

```bash
git clone <toolkit-repo> ~/agent-toolkit
python ~/agent-toolkit/setup.py init /đường-dẫn-tới-project --preset odoo-12 --yes
```

Preset khác: `odoo-17`, `generic`. Thêm preset mới (Django/Rails/Go) chỉ là 1 PR — xem [PORTING.md](templates/agent_toolkit/PORTING.md).

### Tại sao dùng agent-toolkit?

- 🛡️ **Enforce cơ học, không phải honor-system.** 30+ hook DENY ở
  Claude Code harness — strip invariant, claim không proof, git
  destructive, fake progress đều bị chặn.
- 🔬 **Verify trên data thật hoặc không ship.** `/verify` chạy MCP probe
  lên DB live; `evidence_audit` Stop hook BLOCK "test pass" claim nếu
  turn không có `mcp__realdata_test__*` / `mcp__postgres__*` call.
- 📐 **5-phase Spec Kit workflow với hook gate.** `/plan → /clarify →
  /tasks → /analyze → /implement → /verify` — mỗi transition có hook
  từ chối tiến nếu phase trước có GAP.
- 🧭 **Hệ thống rule 3 tầng.** Constitution (nguyên tắc) → ADR (lý do
  decision) → invariants.json (pattern cơ học). Cross-link, auditable,
  append-only. Không upstream toolkit nào có layout này.
- 🔌 **Core stack-agnostic + preset overlay.** Picker
  `<file>.<framework>.json` install config đúng theo preset. Odoo 12/17
  ship sẵn; Django/Rails/Go chỉ thêm config, không fork.
- 📡 **Observability built-in.** `emit_fire_event` ring buffer, hook-health
  aggregator, bypass-rate alert, hook-crash banner — biết rule nào đang
  bị sidestep TRƯỚC khi nó rot.

### Workflow cho DEV

DEV chỉ làm **3 bước manual** — agent tự lo 5 phase còn lại dưới autonomy:

```
DEV gõ:  /plan <ý tưởng>      →  spec.md có cấu trúc
         /clarify <slug>       →  đóng GAP, agent tự /tasks rồi STOP
         /implement <slug>     →  bật autonomy 4h
         
AGENT tự: /analyze → execute tasks → /verify → report PASS/GAP
```

Mỗi feature xong → sidecar `<slug>.implement-noted.md` capture scope
deviation + trade-off + follow-up + confidence để DEV review trước merge.

### Hướng dẫn chi tiết tiếng Việt

Đọc [USAGE.md](USAGE.md) — full guide 861 dòng, có Mục lục 4 nhóm:
- **A. Cài đặt** (§1-4): clone, install vào project, config trung tâm
- **B. Workflow** (§5-6): spec-driven workflow theo từng preset
- **C. Bảo trì** (§7-9): cấu trúc cài, update toolkit, thêm preset mới
- **D. Khi có vấn đề** (§10-12): verify install, troubleshooting, FAQ

### Trạng thái sản xuất

Toolkit đang **dùng thực tế** trên một Odoo 12
Enterprise workspace thật từ tháng 5/2026. Các con số minh hoạ từ dogfooding cục bộ
(không phải benchmark): mỗi session điển hình ~57 hook fire-event, ~26% block,
~3.5% bypass. **30+ hook** active, **948 unit test** (tính đến v0.30.0) trên CI
(matrix: Ubuntu / macOS / Windows × Python 3.8 / 3.10 / 3.12 — all green).
Con số coverage % chỉ đo `setup.py` + `lib/`; các enforcement hook (`templates/claude/hooks/`, ~11k LOC) được ruff-lint check và behavior-test qua subprocess (`tests/test_hooks.py` + các suite per-hook) nhưng không được đo line-coverage vì chúng chạy dưới dạng subprocess.

### Liên hệ tác giả

- Email: [ducthangict.dhtn@gmail.com](mailto:ducthangict.dhtn@gmail.com)
- Zalo: [0989 464 344](tel:+84989464344)
- Mở issue trên repo hoặc liên hệ qua email/Zalo.

License **MIT** — xem [LICENSE](LICENSE) và [NOTICE](NOTICE) cho attribution upstream.
