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
enforces 6 rules at the Claude Code harness level — invariant guard, evidence
audit, real-data verify, git guardrail, kill-switch banner, bypass-rate alert.
Most DENY outright; where a bypass exists it is single-use and logged, never silent.

## Why agent-toolkit?

- 🛡️ **Mechanical enforcement, not honor system.** 30+ hooks DENY at the
  Claude Code harness level — invariant strips, claim-without-proof,
  destructive git (`git_guardrails` blocks commit/push/add until DEV
  authorizes), hallucinated progress, **unresolved gaps on done-claim**
  (`gap_completeness_gate` — chặn drip-feed), **partial-done on a
  multi-item request** (`scope_completeness_gate` — enumerates scope from
  tasks.md / acceptance_evals / TodoWrite), and **cross-zone edits between
  concurrent sub-agents** (`parallel_conflict_guard`). Not warnings the
  agent can ignore.
- 🔬 **Real-data verify or it didn't ship.** `/verify` runs MCP probes on
  the live DB; `evidence_audit` Stop hook BLOCKS "tests pass" claims that
  lack an `mcp__realdata_test__*` or `mcp__postgres__*` call in the turn.
- 📐 **6-8 phase Spec Kit workflow with gate hooks.** `/plan → /clarify →
  /tasks → /analyze → /implement → /verify` — each transition has a
  PreToolUse / Stop hook that refuses to advance if the prior phase has gaps.
- 🧭 **Trinity rule system.** Constitution (slow principles) → ADRs (why
  decisions) → invariants.json (mechanical patterns). Cross-linked,
  auditable, append-only. No upstream toolkit has this 3-tier layout.
- 🔌 **Stack-agnostic core + preset overlays.** `<file>.<framework>.json`
  picker installs the right config per preset. Odoo 12-20 (9 versions)
  ship today; Django/Rails/Go is a config addition, not a fork.
- 📡 **Observability built-in.** `emit_fire_event` ring buffer, hook-health
  aggregator, bypass-rate alerts, hook-crash banner. Know which rules are
  being sidestepped before they rot.

## Install

```bash
git clone <toolkit-repo> ~/agent-toolkit
python ~/agent-toolkit/setup.py init /path/to/project --preset odoo-12 --yes
```

Other presets: `odoo-13` … `odoo-20`, `generic`. Contributing a `django` /
`rails` / `go` preset is a one-PR exercise — see
[PORTING.md](templates/agent_toolkit/PORTING.md). Full preset table +
shipped skills → [docs/PRESETS.md](docs/PRESETS.md).

**For contributors / local hacking on the toolkit itself**:
```bash
cd ~/agent-toolkit
make install   # pytest + pytest-cov + ruff
make rebuild   # full CI-equivalent: lint + test + smoke + dry-run + coverage gate
```

Full release / mirror / tag procedure documented in [REBUILD.md](REBUILD.md).

> 🤖 **AI agents installing into a project**: Read
> [`AI_REBUILD_CHECKLIST.md`](AI_REBUILD_CHECKLIST.md) BEFORE invoking
> `setup.py init` or `setup.py update` — the 4-phase Q&A protocol is
> mandatory. Also read [`AGENTS.md`](AGENTS.md) for the hard rules.

## What's new

- **v0.30.0** — enforcement resilience + Odoo version-fact accuracy + release hygiene:
  - **Enforcement resilience**: `gap_completeness_gate` + `scope_completeness_gate`
    now read the assistant done-claim from the **transcript** (they were
    previously **inert in production**, always allowing); `agent_supervisor`
    stall watcher gains an idle-vs-hung guard (a clean end-of-turn waiting on
    the user is no longer treated as a stall) + transient auto-expiring toast;
    `evidence_audit` phantom-citation fixes (no longer false-flags paths the
    turn wrote or echoed, or absence-reports).
  - **Odoo 12-20 version-fact accuracy**: source-verified corrections vs
    `odoo/odoo` + OCA/OpenUpgrade (e.g. `@api.model_create_multi` since v12,
    `account.invoice`→`account.move` at v13, `payment.provider` at v16) +
    21 web-verified references + OpenUpgrade apriori wiring.
  - **Release hygiene**: lint now covers the `templates/claude/hooks/` tree;
    docs corrected to honest counts.

Full history → [CHANGELOG.md](CHANGELOG.md).

## Quick comparison

|                                  | agent-toolkit | spec-kit | mattpocock/skills | ECC | Aider |
|---|:---:|:---:|:---:|:---:|:---:|
| Spec-driven 6-8 phase workflow   | ✅ | ✅ | partial | partial | ❌ |
| Hook-level mechanical enforcement | **✅** | ❌ | partial | partial | ❌ |
| Real-data MCP verify gate        | **✅** | ❌ | ❌ | partial | ❌ |
| Stack-preset overlay system      | **✅** | partial | ❌ | ❌ | ❌ |
| Telemetry + bypass audit         | **✅** | ❌ | ❌ | partial | ❌ |
| Bilingual docs (EN + VN)         | **✅** | ❌ | ❌ | ❌ | ❌ |
| Git-state agent guardrail        | **✅** | ❌ | ✅ | ❌ | ❌ |
| Drip-feed prevention             | **✅** | ❌ | ❌ | ❌ | ❌ |
| AGENT-side disclosure sidecar (HTML+MD) | **✅** | ❌ | ❌ | partial | ❌ |

## Quick start

DEV does **3 manual steps**; the agent auto-chains the rest under autonomy.

```bash
# 1. Install into an Odoo project, then edit credentials
python ~/agent-toolkit/setup.py init /path/to/project --preset odoo-12 --yes
$EDITOR /path/to/project/.codex/mcp.local.env   # restart Cursor / Claude Code

# 2. In Claude Code, drive a feature with 3 commands:
DEV: /plan <feature>          # → spec.md draft (8 sections + acceptance_evals)
DEV: /clarify <slug>          # → close gaps; agent auto-fires /tasks then STOPs
DEV: /implement <slug>        # → auto-chain: /analyze → tasks → /verify → report
```

`/implement` runs `/analyze` first (HALT blocks Edit/Write on a BLOCK
verdict), executes tasks, then `/verify` proves each User Story on real
data. Full DEV-vs-AGENT split → [docs/USAGE.md](docs/USAGE.md);
end-to-end worked example → [docs/WORKED-EXAMPLE.md](docs/WORKED-EXAMPLE.md);
architecture diagram → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Production status

Toolkit is in **active use** on a real Odoo 12 Enterprise workspace since
May 2026. Illustrative figures from local dogfooding (not a benchmark): a
typical session shows ~57 hook fire-events, ~26% block rate, ~3.5% bypass
rate. **30+ hooks** active, **1018 unit tests** (as of v0.32.0) green in CI
(matrix: Ubuntu / macOS / Windows × Python 3.8 / 3.10 / 3.12). The reported
coverage % measures `setup.py` + `lib/` only; the enforcement hooks
(`templates/claude/hooks/`, ~11k LOC) are ruff-lint-checked and
behavior-tested via subprocess (`tests/test_hooks.py` + per-hook suites)
but are not line-coverage-measured because they run as subprocesses.

## 🇻🇳 Tiếng Việt

**Hạ tầng AI agent (Claude Code / Cursor / Codex) cho spec-driven dev — cài 1 lần, chạy mọi project.**

Agent AI hay ship code lỗi khi không có gì **ép cơ học**. Toolkit này biến
6 rule thành un-skip-able: chặn xóa invariant, audit claim không proof,
verify trên data thật, chặn agent commit/push, banner kill-switch, alert
bypass. DEV chỉ làm **3 bước** (`/plan` → `/clarify` → `/implement`); agent
tự chạy `/analyze` → execute tasks → `/verify` → report dưới autonomy (+1h
mặc định).

Full guide tiếng Việt: [docs/USAGE.vn.md](docs/USAGE.vn.md) (tóm tắt) +
[USAGE.md](USAGE.md) (chi tiết ~860 dòng — cài đặt, workflow, bảo trì, troubleshooting).

## Credits

Original work, standing on [github/spec-kit](https://github.com/github/spec-kit),
[mattpocock/skills](https://github.com/mattpocock/skills) (MIT), Andrej
Karpathy's guidelines, and Karl Popper's falsifiability. Author / maintainer:
**Thang Vo** ([ducthangict.dhtn@gmail.com](mailto:ducthangict.dhtn@gmail.com)).
Full attribution table → [docs/CREDITS.md](docs/CREDITS.md). License **MIT**
— see [LICENSE](LICENSE) + [NOTICE](NOTICE).
