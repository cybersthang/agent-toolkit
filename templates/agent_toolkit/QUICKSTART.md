# Agent-Toolkit — 5-minute Quickstart

For a dev who just inherited a project using agent-toolkit, or for
installing the toolkit into a fresh workspace. **English** version;
Vietnamese guide is at the toolkit repo root (`USAGE.md`).

## What the toolkit gives you (90 seconds)

The toolkit is **stack-agnostic at the core** — it bundles a Claude
Code / Cursor / Codex agent harness with mechanical enforcement that
works for any project type. **Presets** then layer on stack-specific
defaults: which MCP servers to spin up, which exception namespaces to
watch, which feature-glob shape to gate at commit.

Today three presets ship:

| Preset | Stack-specific overlays |
|---|---|
| `odoo-12` | Odoo 12 / Python 3.8 / QWeb + jQuery / `@api.multi`. See [QUICKSTART.odoo.md](QUICKSTART.odoo.md). |
| `odoo-17` | Odoo 17 / Python 3.10+ / OWL / new ORM. See [QUICKSTART.odoo.md](QUICKSTART.odoo.md). |
| `generic` | No stack-specific overlay — pure agnostic core. Build your own preset overlay on top. |

The toolkit gives every preset, regardless of stack:

- A **Spec Kit-aligned spec-driven workflow** — DEV runs `/plan` +
  `/clarify`, agent auto-chains `/tasks` → `/analyze` → `/implement` →
  `/verify` under autonomy.
- **MCP servers**: codebase + postgres + a stack-specific
  `realdata_test` (Odoo today; Django / Rails / Go contributions welcome).
- **Mechanical enforcement** that catches "agent reports tests pass,
  but real-data reveals bugs" failures via 5 layers:
  1. **Invariant guard** (PreToolUse): blocks Edits that remove
     declared `must_keep_regex` patterns.
  2. **PASS-claim contract** (Stop): blocks `tests pass / verified /
     done` claims without an MCP real-data call in the same turn.
  3. **Hallucinated-progress checks** (Stop): blocks past-tense action
     claims without matching tool_use, success claims contradicted by
     error tool_results, completion claims while TodoWrite has open
     items, and aggregate over-counts.
  4. **Generic claim audit** (Stop): blocks `X is slow / missing / root
     cause` claims without any tool call in the turn.
  5. **Pre-commit mirror** (git): same enforcement at commit time so
     dev edits in IDE don't bypass.
  6. **Git guardrails** (PreToolUse Bash): blocks the agent from
     running destructive git ops (`commit`/`push`/`add`/`--no-verify`/
     `reset --hard`/etc.) — DEV-only gate.

## Install in a new project

The main install path is `setup.py init` at the toolkit root.

```bash
# Clone toolkit (once per machine)
git clone <toolkit-repo> ~/agent-toolkit

# Install into a project — choose your preset
python ~/agent-toolkit/setup.py init /path/to/your/project \
    --preset <preset-name> \            # odoo-12 / odoo-17 / generic
    --python /path/to/venv/bin/python \
    --yes
```

Output: copies hooks + commands + tests + tools + Spec Kit skills,
seeds `.agent-toolkit/constitution.md` + canonical_decisions registry
+ stack-specific config overlays (debug.json / coverage_config.json /
intent_map.json / verification.json) chosen by the preset's
`stack.framework` field.

## First 3 things to do after install

1. **Read the constitution** — `.agent-toolkit/constitution.md`. ONE
   file holding all project-wide principles. Slow-changing; updated
   only via `/constitution` slash command.
2. **Skim the canonical decisions** — `.codex/canonical_decisions.json`.
   "How do we do X in this project?" lives here. Answer recurring
   questions by reading, not re-deriving.
3. **Run `/inv-list`** in Claude Code — see what mechanical rules are
   active. These BLOCK Edits at the harness level, not just warn.

## Pick your preset's guide

- **Odoo (12 or 17)** → [QUICKSTART.odoo.md](QUICKSTART.odoo.md) —
  Odoo-specific MCP server bootstrap, addon root configuration,
  realdata_test wiring.
- **Generic** → no extra setup; just start with `/plan <first-feature>`.
- **Adding a new preset (Django / Rails / Go / etc.)** → see
  [PORTING.md](PORTING.md) and `presets/_example_private_overlay.json.template`.

## Hard rules every preset enforces

- The agent **cannot** run `git commit / push / add` — DEV is the sole
  git gatekeeper. Bypass once via `.agent-toolkit/.skip_git_guard_next.json`.
- The agent **cannot** Edit files that strip a `must_keep_regex`
  invariant marked `severity: blocker`. Bypass once with
  `bypass-invariant: <id>` in the next prompt.
- The agent **cannot** claim `tests pass / done / verified` without a
  real-data MCP call (`mcp__realdata_test__*` or `mcp__postgres__*`)
  in the same turn — `evidence_audit` Stop hook BLOCKs.
- The agent **cannot** stop with a Verify Report missing required
  sections — `verify_lint` Stop hook BLOCKs.

## Troubleshooting

- **Hook is misfiring**: edit `.agent-toolkit/enforce_mode.json`'s
  `per_hook` entry to `warn` or `off` for the offending hook.
- **Entire toolkit needs disabling for a moment**: set
  `AGENT_TOOLKIT_DISABLE=1` in the shell. Every hook becomes a no-op.
- **Hook crashed**: `.agent-toolkit/.hook_crash_log.json` ring buffer
  has the last 1000 crashes. `python .codex/tools/hook_health.py` for
  aggregated stats.

## Where to go next

- Full guide (EN + VN): `USAGE.md` at the toolkit repo root.
- Contribute a preset: `CONTRIBUTING.md`.
- Adopt a new pattern from upstream (mattpocock / spec-kit / ECC):
  see `NOTICE` for attribution model + the existing `verification_loop`
  / `/eval-define` / `/bug-to-test` adoptions as templates.

---

## 🇻🇳 Quickstart 5-phút (Tiếng Việt)

Cho dev vừa được giao project có agent-toolkit, hoặc cài toolkit vào
workspace mới.

### Toolkit này cho cái gì (90 giây)

Toolkit **stack-agnostic ở core** — Claude Code / Cursor / Codex agent
harness với enforcement cơ học cho mọi loại project. **Preset** chọn
default stack-specific: MCP server nào, namespace exception nào watch,
feature-glob shape nào gate ở commit.

Hôm nay 3 preset ship:

| Preset | Overlay stack-specific |
|---|---|
| `odoo-12` | Odoo 12 / Python 3.8 / QWeb + jQuery / `@api.multi` |
| `odoo-17` | Odoo 17 / Python 3.10+ / OWL / ORM mới |
| `generic` | Không overlay — core agnostic thuần. Tự build preset overlay lên. |

Mọi preset đều có:

- **Spec-driven workflow theo Spec Kit** — DEV gõ `/plan` + `/clarify`,
  agent tự `/tasks → /analyze → /implement → /verify` dưới autonomy.
- **MCP server**: codebase + postgres + `realdata_test` stack-specific
  (Odoo hôm nay; Django/Rails/Go contribution welcome).
- **6 lớp enforcement cơ học** chống pattern "agent báo test pass, prod
  data lộ bug":
  1. **Invariant guard** (PreToolUse): chặn Edit xóa pattern `must_keep_regex`
  2. **PASS-claim contract** (Stop): chặn claim "test pass / done" không
     kèm MCP real-data call cùng turn
  3. **Hallucinated-progress check** (Stop): chặn past-tense action mà
     không có tool_use, claim done khi TodoWrite còn open, over-count
  4. **Generic claim audit** (Stop): chặn "X is slow / missing / root
     cause" không có tool call trong turn
  5. **Pre-commit mirror** (git): enforce cùng rule ở commit time để
     edit IDE không bypass
  6. **Git guardrail** (PreToolUse Bash): chặn agent chạy git destructive
     (`commit`/`push`/`add`/`--no-verify`/`reset --hard`/...) — DEV-only gate

### Cài vào project mới

Đường vào chính: `setup.py init` ở root toolkit.

```bash
# Clone toolkit (1 lần / 1 máy)
git clone <toolkit-repo> ~/agent-toolkit

# Cài vào project — chọn preset
python ~/agent-toolkit/setup.py init /đường-dẫn-project \
    --preset <tên-preset> \              # odoo-12 / odoo-17 / generic
    --python /đường-dẫn-venv/bin/python \
    --yes
```

Output: copy hook + command + test + tool + Spec Kit skill, seed
`.agent-toolkit/constitution.md` + canonical_decisions registry +
stack-specific overlay (debug.json / coverage_config.json /
intent_map.json / verification.json) — chọn theo field
`stack.framework` của preset.

### 3 việc làm ngay sau khi cài

1. **Đọc constitution** — `.agent-toolkit/constitution.md`. 1 file chứa
   mọi nguyên tắc project-wide. Slow-changing; chỉ update qua slash
   command `/constitution`.
2. **Skim canonical decisions** — `.codex/canonical_decisions.json`. "Làm
   X trong project này thế nào?" sống ở đây. Trả lời câu hỏi tái lặp
   bằng cách ĐỌC, không re-derive.
3. **Chạy `/inv-list`** trong Claude Code — xem rule cơ học nào đang
   active. Rule này CHẶN Edit ở harness, không chỉ warn.

### Chọn guide theo preset

- **Odoo (12 hoặc 17)** → [QUICKSTART.odoo.md](QUICKSTART.odoo.md) —
  Odoo-specific MCP bootstrap, cấu hình addon root, realdata_test wiring.
- **Generic** → không setup thêm; bắt đầu với `/plan <feature-đầu-tiên>`.
- **Thêm preset mới (Django/Rails/Go/v.v.)** → xem [PORTING.md](PORTING.md)
  và `presets/_example_private_overlay.json.template`.

### Hard rule mọi preset enforce

- Agent **KHÔNG** chạy được `git commit / push / add` — DEV là gatekeeper
  duy nhất cho git state. Bypass 1 lần qua
  `.agent-toolkit/.skip_git_guard_next.json`.
- Agent **KHÔNG** Edit được file strip invariant `must_keep_regex`
  severity `blocker`. Bypass 1 lần với `bypass-invariant: <id>` ở prompt
  tiếp theo.
- Agent **KHÔNG** claim được "test pass / done / verified" mà thiếu
  MCP real-data call (`mcp__realdata_test__*` hoặc `mcp__postgres__*`)
  cùng turn — `evidence_audit` Stop hook BLOCK.
- Agent **KHÔNG** stop được với Verify Report thiếu section bắt buộc
  — `verify_lint` Stop hook BLOCK.

### Troubleshooting

- **Hook fire sai**: sửa `.agent-toolkit/enforce_mode.json` entry
  `per_hook` thành `warn` hoặc `off` cho hook đó.
- **Cần tắt toàn bộ toolkit tạm**: set `AGENT_TOOLKIT_DISABLE=1` trong
  shell. Mọi hook thành no-op. `session_brief` sẽ inject banner đỏ mỗi
  turn cảnh báo enforcement đang OFF.
- **Hook crashed**: `.agent-toolkit/.hook_crash_log.json` ring buffer
  giữ 1000 crash gần nhất. Chạy
  `python .codex/tools/hook_health.py` để xem stats tổng hợp.

### Đi tiếp đâu

- Full guide (EN + VN): `USAGE.md` ở root toolkit (861 dòng).
- Contribute preset: `CONTRIBUTING.md`.
- Adopt pattern mới từ upstream (mattpocock / spec-kit / ECC): xem
  `NOTICE` cho model attribution + 3 adoption hiện có
  (`verification_loop` / `/eval-define` / `/bug-to-test`) làm template.
