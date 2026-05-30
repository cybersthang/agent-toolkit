# Usage reference (EN)

Consolidated reference for day-to-day use, install layout, CLI, and
maintenance. For the full Vietnamese end-to-end guide see
[USAGE.vn.md](USAGE.vn.md).

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

### What AGENT does automatically — **6-8 auto-chained phases** / AGENT tự làm **6-8 phase auto-chain**

After DEV types `/implement <slug>`, the agent chains these steps under
autonomy (default +1h, configurable via `--until`). *Sau khi DEV gõ
`/implement`, agent tự chạy chuỗi sau dưới autonomy (mặc định +1h).*

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

> Full DEV flow: see the [Worked example](WORKED-EXAMPLE.md).

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
[USAGE.vn.md](USAGE.vn.md) cho ví dụ end-to-end.

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
├── README.md                 # landing page
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
