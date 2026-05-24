# agent-toolkit — Hướng Dẫn Sử Dụng

Toolkit này đóng gói toàn bộ hạ tầng AI agent (Claude Code / Cursor / Codex)
— **core stack-agnostic, presets opinionated**. Clone về một lần, chạy
`setup.py init --preset <name>` cho từng project. Hôm nay 3 preset ship
sẵn (`generic`, `odoo-12`, `odoo-17`); thêm Django/Rails/Go là việc
"contribution-not-fork" — xem [PORTING.md](templates/agent_toolkit/PORTING.md).

Toolkit bundle một quy trình **spec-driven theo chuẩn GitHub Spec Kit**
(`/plan` → `/clarify` → `/tasks` → `/analyze` → `/implement` → `/verify`)
trên nền MCP server (codebase + postgres + một `realdata_test`
stack-specific + JIRA), Cursor rules + Claude Code hooks + skills.

> Doc dài 850+ dòng — dùng **Mục lục dưới** để jump đến section cần
> đọc. **Đọc nhanh tối thiểu**: §1 + §2 + §3 + §5 + §11 (skim §11
> trước khi gặp lỗi đầu tiên).

## Mục lục

### Nhóm A — Cài đặt (đọc lần đầu)
- [1. Cài đặt toolkit lên máy](#1-cài-đặt-toolkit-lên-máy) — clone repo, setup venv.
- [2. Cài hạ tầng vào một project](#2-cài-hạ-tầng-vào-một-project) — `setup.py init` + chọn preset.
- [3. Sau khi install lần đầu](#3-sau-khi-install-lần-đầu) — 3 việc cần làm ngay.
- [4. `agent-toolkit.config.json` — config trung tâm](#4-agent-toolkitconfigjson--config-trung-tâm) — override preset defaults.

### Nhóm B — Workflow hằng ngày
- [5. Spec-driven workflow — DEV chỉ làm Plan + Clarify](#5-spec-driven-workflow--dev-chỉ-làm-plan--clarify) — 3 bước manual, 5 phase auto.
- [6. Workflow theo từng preset](#6-workflow-theo-từng-preset) — odoo-12 vs odoo-17 vs generic vs tương lai.

### Nhóm C — Bảo trì + nâng cấp
- [7. Cấu trúc được cài vào project](#7-cấu-trúc-được-cài-vào-project) — `.codex/`, `.claude/`, `.cursor/`, `.agent-toolkit/`.
- [8. Cập nhật toolkit cho project đã cài](#8-cập-nhật-toolkit-cho-project-đã-cài) — `setup.py update`.
- [9. Khi Odoo 21+ ra mắt — chỉ cần thêm files](#9-khi-odoo-21-ra-mắt--chỉ-cần-thêm-files) — pattern thêm preset mới.

### Nhóm D — Khi có vấn đề
- [10. Verify install](#10-verify-install) — checklist 11 dòng confirm install OK.
- [11. Troubleshooting](#11-troubleshooting) — lỗi hay gặp + cách fix.
- [12. FAQ](#12-faq) — câu hỏi thường gặp.

---

## 1. Cài đặt toolkit lên máy

Clone toolkit **một lần duy nhất** ở vị trí cố định trên máy:

```bash
# Linux / macOS
git clone <toolkit-repo-url> ~/agent-toolkit

# Windows (PowerShell)
git clone <toolkit-repo-url> $HOME\agent-toolkit
```

Toolkit là **standalone** — không phụ thuộc bất kỳ project nào. Bạn có thể đặt nó cạnh các project, hoặc trong `~/tools/`, hoặc bất kỳ đâu.

**Yêu cầu:** Python 3.8+. Toolkit zero-deps (chỉ dùng stdlib).

---

## 2. Cài hạ tầng vào một project

### 2.1. Liệt kê các preset có sẵn

```bash
python ~/agent-toolkit/setup.py list-presets
```

Output (3 preset):
```
Available presets:
  generic           — Generic Python — codebase MCP only (fallback, KHÔNG khuyến nghị cho Odoo)
  odoo-12           — Odoo 12 stack — Python 3.8, QWeb + jQuery, @api.multi
  odoo-17           — Odoo 17 — Python 3.10+, OWL, recordset-by-default, @api.model_create_multi
```

> **Project-specific overlays**: nếu project có addon roots / JIRA endpoint
> / Enterprise modules riêng, tạo private preset `extends: odoo-12` (hoặc
> `odoo-17`) trong fork riêng. Đừng commit nội bộ vào public toolkit —
> xem `templates/agent_toolkit/PORTING.md` cho recipe.

### 2.2. Cài interactive (toolkit hỏi từng giá trị)

```bash
python ~/agent-toolkit/setup.py init /path/to/your/project
```

Toolkit sẽ hỏi:
1. Chọn preset (1/2/3)
2. Đường dẫn Python binary (auto-detect `venv/`, `.venv/`)
3. Đường dẫn `psql` (auto-detect các vị trí phổ biến)
4. Confirm

### 2.3. Cài non-interactive (truyền hết qua CLI — khuyến khích)

```bash
python ~/agent-toolkit/setup.py init /path/to/your/project \
    --preset odoo-17 \
    --python /path/to/venv/bin/python \
    --psql /usr/bin/psql \
    --project-name "My Odoo 17 App" \
    --yes
```

**Windows ví dụ:** (thay `<USER>` bằng tên user, `<TOOLKIT_PATH>` bằng nơi anh
clone toolkit, `<PROJECT_PATH>` bằng project đích)

```powershell
python <TOOLKIT_PATH>\setup.py init <PROJECT_PATH> `
    --preset odoo-17 `
    --python <PROJECT_PATH>\venv\Scripts\python.exe `
    --yes
```

### 2.4. Dry-run (xem trước, không ghi gì)

```bash
python ~/agent-toolkit/setup.py init /path/to/project --preset odoo-17 --dry-run
```

In ra danh sách file sẽ được ghi và đường dẫn memory sẽ được seed, **không** chạm vào disk.

---

## 3. Sau khi install lần đầu

Sau khi `init` xong, làm 3 bước:

### Bước 1: Điền credentials và (nếu cần) chỉnh `agent-toolkit.config.json`

Sau init, project có **3 file config** ở 3 vị trí khác nhau:

| File | Mục đích | Commit Git? |
|------|----------|-------------|
| `agent-toolkit.config.json` | Override preset defaults (addon_roots, mcp_servers, db, project_name…) | ✅ Có (trừ `machine_local`) |
| `.codex/mcp.local.env` | Credentials thật (PASSWORD, JIRA user/pass) | ❌ KHÔNG (auto-gitignored) |
| `.cursor/mcp.json` | MCP config cho Cursor (auto-generated) | ❌ KHÔNG (auto-gitignored) |

Điền credentials:

```bash
$EDITOR /path/to/project/.codex/mcp.local.env
```

File `.codex/mcp.local.env.example` được render từ template. Copy thành `mcp.local.env` rồi điền (`<PREFIX>` = `env_prefix` từ `agent-toolkit.config.json`, mặc định lấy từ project name khi install):

```
<PREFIX>_PGPASSWORD=...               # password Postgres
<PREFIX>_JIRA_PRODUCTION_USER=...     # JIRA prod (nếu preset có jira_production MCP)
<PREFIX>_JIRA_PRODUCTION_PASSWORD=...
<PREFIX>_JIRA_PREPRODUCTION_USER=...  # JIRA preprod (optional)
<PREFIX>_JIRA_PREPRODUCTION_PASSWORD=...
```

`mcp.local.env` đã được thêm sẵn vào `.gitignore` — **tuyệt đối không commit**.

### Bước 2: Restart Cursor / Claude Code

Cursor/Claude Code chỉ load MCP config khi khởi động. Restart để các MCP server mới được nhận.

### Bước 3: Verify

```bash
python /path/to/project/.codex/tests/test_mcp_wrappers.py
```

Mong đợi:
- **Odoo 12**: `Ran 27 tests in <X>s — OK`
- **Odoo 17**: `Ran 27 tests in <X>s — OK (skipped=6)` (6 test JIRA bị skip vì preset không cài JIRA)

---

## 4. `agent-toolkit.config.json` — config trung tâm

Sau `init`, toolkit ghi file `agent-toolkit.config.json` ở root project. Đây là **single source of truth** cho mọi giá trị toolkit cần khi render template hay sinh `.cursor/mcp.json`. Mục đích: chỉnh đúng 1 file thay vì re-pass CLI flags hay sửa preset trong toolkit repo.

### 4.1. Cấu trúc file

```jsonc
{
  "_managed_by": "agent-toolkit",
  "_schema_version": 1,
  "_doc": "Edit this file to override preset defaults...",

  "preset": "odoo-17",                          // preset name
  "project_name": "test_odoo17_install",
  "workspace_root": "C:/tmp/test_odoo17_install",
  "response_language": "Vietnamese",            // Reply language

  "stack": {                                    // Override stack details if cần
    "language": "python",
    "language_version": "3.10",
    "framework": "odoo",
    "framework_version": "17",
    "label": "Odoo 17"
  },

  "addon_roots": [                              // ← CODEBASE FOLDERS
    "addons",
    "custom_addons",
    "enterprise",
    "my_custom_addons"                          // user thêm thoải mái
  ],

  "mcp_servers": [                              // MCP nào sẽ bật
    "codebase",
    "postgres"                                  // bỏ "realdata_test" → mcp.json bớt 1 dòng
  ],

  "db": {
    "default_db": "my_real_db",                 // override DB
    "default_port": 5433
  },

  "machine_local": {                            // ← KHÔNG nên commit nguyên block này
    "_doc": "Machine-specific paths.",
    "python_bin": "C:/.../venv/Scripts/python.exe",
    "psql_bin": "C:/Program Files/.../psql.exe"
  }
}
```

### 4.2. Thứ tự ưu tiên khi resolve

```
CLI flag  >  agent-toolkit.config.json  >  preset JSON  >  auto-detect
```

Ví dụ: `--python /other/python.exe` ưu tiên hơn `machine_local.python_bin` trong file. File đè preset. Preset đè auto-detect.

### 4.3. Use case thực tế

**A. Thêm addon root mới (codebase folder)**

```jsonc
"addon_roots": [
  "addons",
  "custom_addons",
  "enterprise",
  "tools/internal_addons"   // ← thêm
]
```

Chạy `setup.py update <project>` → `AGENTS.md`, `project_workspace.md`, canonical_decisions answer "addon roots" đều cập nhật theo.

**B. Bỏ một MCP server**

Project Odoo 17 không cần JIRA, hoặc test môi trường offline không cần `realdata_test`:

```jsonc
"mcp_servers": ["codebase", "postgres"]
```

`update` xong → `.cursor/mcp.json` chỉ còn 2 server, các start_*_mcp.py dư thừa vẫn nằm lại trong `.codex/` (chấp nhận được — Cursor không load chúng).

**C. Đổi DB mặc định**

```jsonc
"db": {
  "default_db": "production_clone",
  "default_port": 5432
}
```

`AGENTS.md` + `odoo-17-project-context.mdc` đều update.

**D. Project-level config commit lên Git, machine paths thì không**

Khuyến nghị: commit toàn bộ `agent-toolkit.config.json` **trừ block `machine_local`**. Cách triển khai:

```bash
# Cách 1: gitignore cả file, mỗi dev tự chạy `init`
echo "agent-toolkit.config.json" >> .gitignore

# Cách 2: commit file nhưng dùng sparse strategy — split thành 2 file
# (không support sẵn, nhưng có thể đặt machine_local.python_bin = ""
#  rồi dev pass --python qua CLI mỗi lần update)
```

Recommendation thực dụng: commit file luôn, mỗi máy chỉnh `machine_local.python_bin` rồi `setup.py update`. Path Windows / Linux khác nhau là chuyện bình thường, dev biết tự fix.

### 4.4. Sau khi edit file → re-run update

```bash
python ~/agent-toolkit/setup.py update /path/to/project
```

Update đọc file, merge, re-render mọi template, ghi lại file (chuẩn hoá format).

---

## 5. Spec-driven workflow — DEV chỉ làm Plan + Clarify

Toolkit v0.4+ ship workflow **GitHub Spec Kit-aligned**. DEV chỉ phải gõ
**3 lệnh**, phần còn lại agent tự chạy dưới autonomy + auto-verify.

### 5.1. Flow tổng quan

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

### 5.2. 6 slash command

| Phase | Slash command | DEV gõ tay? | Skill bundle |
|---|---|---|---|
| 1 — SPECIFY | `/plan <feature description>` | ✅ | `plan-feature` |
| 2 — CLARIFY | `/clarify <slug>` | ✅ | `clarify` |
| 3 — TASKS | `/tasks <slug>` | tự fire sau /clarify | `tasks-breakdown` |
| 3.5 — ANALYZE | `/analyze <slug>` | tự fire trong /implement | `analyze-artifacts` |
| 4 — IMPLEMENT | `/implement <slug>` | ✅ (sau khi review tasks.md) | autonomy + execute |
| 5 — VERIFY | `/verify <slug>` | tự fire cuối /implement | `verify-feature` |

### 5.3. Spec lưu ở đâu — branch-scoped

Toolkit lưu spec theo nhánh git:

```
.agent-toolkit/specs/<branch>/<slug>.md             # spec
.agent-toolkit/specs/<branch>/<slug>/tasks.md       # tasks (sau /tasks)
.agent-toolkit/specs/<branch>/<slug>/analyze-report.md   # sau /analyze
```

Trong đó `<branch>` = `git rev-parse --abbrev-ref HEAD` (`/` đổi thành
`_`, không có git → `_default`). 2 dev cùng làm 2 feature trên 2 branch
sẽ không đụng nhau.

### 5.4. Ví dụ end-to-end

```text
DEV:  /plan Thêm field priority vào res.partner cho cron export

→ Agent đọc codebase qua MCP, tạo
  `.agent-toolkit/specs/feature_partner_priority/partner-priority.md`
  với 8 mục + skeleton acceptance_evals. STOP.

DEV:  /clarify partner-priority

→ Agent hỏi 1 Q / turn về các Open Questions còn lại
  ("priority dạng integer hay selection?", "default value?", "có
  cần migrate dữ liệu cũ?", ...).
→ Trên DEV "done": refine acceptance_evals (set grader/layer/probe,
  smoke-test). Spec status: clarified.
→ Auto-fire /tasks → emit tasks.md với T1..T<N>. STOP — DEV review.

DEV: <đọc tasks.md, edit gì đó nếu cần>
DEV:  /implement partner-priority

→ Agent inline /analyze: 7 cross-artifact check. PASS.
→ Autonomy ON +4h, banner 🚀 IMPLEMENT.
→ Execute T1 → verify → T2 → verify → ... → tất cả PASS.
→ Inline /verify: probe parallel qua realdata_test MCP.
→ Emit Verify Report (PASS/GAP/BLOCKER table).
→ Update spec status: verified | gaps-found | blocked.
→ Autonomy auto-OFF nếu all PASS.
→ Báo cáo DEV.
```

### 5.5. Các slash command tiện ích khác

| Command | Mục đích |
|---|---|
| `/adr-add <title>` | Capture WHY behind a decision → `decision-log.md` |
| `/inv-add <id>` | Đăng ký invariant (must_keep_regex) → hook ép tuân |
| `/inv-list` | Liệt kê invariant đang active |
| `/probe-add <id>` | Đăng ký acceptance probe (mechanical PASS contract) |
| `/probe-coverage` | Pre-merge: file feature nào chưa có probe? |
| `/run-probes [id\|all]` | Chạy probe falsification trên live data |
| `/eval-define <slug>` | Manual override để chốt acceptance_evals (nếu skip /clarify) |
| `/eval-backfill <slug>` | Bù evals cho spec đã implement nhưng chưa có evals |
| `/bug-to-test <slug>` | Sau fix bug: viết regression test + register invariant |
| `/recall <topic>` | Tìm ADR/spec/decision trước đó liên quan topic |
| `/review <scope>` | Exhaustive code review (1 pass, full Blocker/Medium/Low) |
| `/test-env <url>` | Capture test environment URL cho /verify dùng |
| `/tdd on\|off\|status\|run` | Toggle TDD auto-loop (PostToolUse hook) |
| `/stop-autonomy` | Cắt sớm autonomy nếu đang ON |

---

## 6. Workflow theo từng preset

### 6.1. Preset `odoo-12` (Odoo 12 Community / Enterprise)

```bash
python ~/agent-toolkit/setup.py init /path/to/your-odoo12-app \
    --preset odoo-12 \
    --python /path/to/venv/bin/python \
    --yes
```

Project nhận:
- **3 MCP servers**: `codebase`, `postgres`, `realdata_test` (thêm JIRA
  hoặc external MCP qua project-specific overlay nếu cần — xem PORTING.md)
- **6 cursor rules**: 3 Odoo 12 specific (backend, generic,
  project-context) + 3 stack-agnostic (audit, decision-consistency,
  karpathy, mcp-routing)
- **Spec Kit chain skills**: `plan-feature`, `clarify`, `tasks-breakdown`,
  `analyze-artifacts`, `verify-feature` (workflow)
- **Guardrail skills**: `clarification-gate`, `code-review`,
  `doubt-driven-review`, `claim-falsification`,
  `classifier-output-audit`, `karpathy-guidelines`, `real-data-proof`
- **Odoo skills version-aware** (9 cái, mỗi cái tự detect version từ
  `__manifest__.py` rồi load đúng references): `odoo-code-review`,
  `odoo-code-patterns`, `odoo-codebase-discovery`,
  `odoo-data-verification`, `odoo-debug-troubleshoot`,
  `odoo-deterministic-answers`, `odoo-jira-workflow`,
  `odoo-module-scaffold`, `odoo-tdd`. Cùng skill phục vụ Odoo 12 → 20
  + tương lai.
- **Memory packs**: `_common` + `odoo-12` (workspace, MCP routing, user
  profile, feedback policy, karpathy reference…)
- **`canonical_decisions.json`**: shipped seed cho Odoo 12 conventions
- `addon_roots`, `default_db` rỗng — DEV configure qua Phase 1 Q&A
  protocol hoặc `agent-toolkit.config.json` overrides
- Response language: English (override qua `agent-toolkit.config.json`)

> **Project-specific defaults?** Nếu project có addon roots cố định,
> internal JIRA URLs, hoặc cần response language khác → tạo private
> preset overlay `extends: odoo-12` trong fork riêng. Đừng commit
> internal config vào public toolkit.

### 6.2. Preset `odoo-17` (Odoo 17 Community / Enterprise)

```bash
python ~/agent-toolkit/setup.py init /path/to/odoo17-project \
    --preset odoo-17 \
    --python /path/to/odoo17-venv/bin/python \
    --yes
```

Project nhận:
- **3 MCP servers**: `codebase`, `postgres`, `realdata_test` (không có
  JIRA — thêm sau nếu cần qua `agent-toolkit.config.json`)
- **8 cursor rules**: 4 Odoo 17 specific + 4 stack-agnostic
- **Spec Kit chain + guardrails**: như `odoo-12`
- **Odoo skills version-aware** (9 cái — cùng bộ skill như `odoo-12`
  vì skill tự detect version từ `__manifest__.py`): `odoo-code-review`,
  `odoo-code-patterns`, `odoo-codebase-discovery`,
  `odoo-data-verification`, `odoo-debug-troubleshoot`,
  `odoo-deterministic-answers`, `odoo-jira-workflow`,
  `odoo-module-scaffold`, `odoo-tdd` (JIRA tools chỉ hoạt động nếu
  preset có wire JIRA MCP)
- **Memory packs**: `_common` + `odoo-17` (~10 file)
- **`canonical_decisions.json`**: ~11 entry generic Odoo 17
  (recordset-default, `@api.model_create_multi`, OWL…)

Khác biệt chính so với Odoo 12:
- `@api.multi` bị **xoá** — recordset là default
- Override `create()` bắt buộc dùng `@api.model_create_multi(vals_list)`
- View bỏ `attrs="{...}"` và `states="…"` — dùng `invisible="<expr>"` trực tiếp
- Frontend là OWL, không còn jQuery

### 6.3. Preset `generic` (Plain Python — fallback, KHÔNG khuyến nghị cho Odoo)

```bash
python ~/agent-toolkit/setup.py init /path/to/python-app --preset generic --yes
```

Project nhận:
- **1 MCP server**: `codebase` (chỉ discovery, không có Postgres/Odoo)
- **Cursor rules `_common`**: 4 file (audit, decision-consistency,
  karpathy, mcp-routing)
- **Spec Kit chain + guardrails**: như mọi preset
- KHÔNG có Odoo-specific gì (không `odoo-code-review`, không stack skills)
- Memory packs `_common` only

Preset này tồn tại để **thử nghiệm core workflow** trên project
non-Odoo, KHÔNG phải production path cho stack khác. Để thật sự
support Django/Rails/v.v., xem `templates/agent_toolkit/PORTING.md`
+ tự author rules/skills/MCP cho stack đó.

---

## 7. Cấu trúc được cài vào project

Sau `init`, project có thêm:

```
your-project/
├── agent-toolkit.config.json       # ← CONFIG TRUNG TÂM (xem mục 4)
├── .codex/
│   ├── mcp_servers/                # MCP server impls (theo preset)
│   │   ├── codebase_server.py
│   │   ├── common.py
│   │   ├── postgres_server.py     # nếu preset có postgres
│   │   ├── realdata_test_server.py
│   │   └── jira_server.py         # nếu preset có jira
│   ├── start_*_mcp.py              # Stdio launchers
│   ├── canonical_decisions.json    # Registry — KHÔNG commit credentials
│   ├── config.toml.example         # Codex CLI config template
│   ├── mcp.local.env.example       # Credentials template (copy → mcp.local.env)
│   └── tests/                      # Verification tests
│       ├── test_mcp_wrappers.py
│       ├── smoke_mcp_servers.py
│       └── run_all_tests.py
├── .cursor/
│   ├── mcp.json                    # Auto-generated (gitignored)
│   ├── rules/*.mdc                 # Always-apply rules
│   └── skills/*/SKILL.md           # Focused skills
├── AGENTS.md                       # Entry point cho mọi AI agent
├── CLAUDE.md                       # Claude-specific overrides
└── .gitignore                      # Auto-augmented với mcp.local.env, mcp.json...

~/.claude/projects/<encoded>/memory/   # Claude Code memory (seeded ngoài project)
├── MEMORY.md                       # Index
├── user_profile.md
├── feedback_*.md
├── project_workspace.md
├── project_mcp_routing.md
└── reference_karpathy.md
```

`<encoded>` là path của project được encode (vd `c--projects-my-odoo17-app`). Toolkit tự tính.

---

## 8. Cập nhật toolkit cho project đã cài

Khi toolkit có thay đổi (rule mới, skill mới, MCP server fix bug…) **HOẶC** khi user vừa edit `agent-toolkit.config.json`:

```bash
python ~/agent-toolkit/setup.py update /path/to/project
```

`update` đọc `agent-toolkit.config.json` để biết preset + override, sau đó re-run logic của `init`:

- ✅ Ghi đè rules, skills, MCP server impls, start scripts, tests
- ✅ Reseed memory files (force=true → cập nhật cả nội dung)
- ✅ Re-render `AGENTS.md`, `CLAUDE.md`, `mcp.local.env.example`, `odoo-*-project-context.mdc`
- ✅ Re-generate `.cursor/mcp.json` (theo `mcp_servers` trong config.json)
- ✅ Re-write `agent-toolkit.config.json` (chuẩn hoá format)
- ❌ **Không** đụng `mcp.local.env` (credentials thật)
- ❌ **Không** đụng `.codex/canonical_decisions.json` nếu file đã tồn tại (registry curated locally)
- ❌ **Không** xóa file MCP server cũ khi user bỏ ra khỏi `mcp_servers` (file dư thừa vô hại — có thể xóa thủ công)

Override flag tại commandline (ưu tiên hơn config file):

```bash
python ~/agent-toolkit/setup.py update /path/to/project \
    --python /new/path/to/python.exe \
    --preset odoo-17
```

---

## 9. Khi Odoo 21+ ra mắt — chỉ cần thêm files

Toolkit hiện ship **9 Odoo skills version-aware** (Odoo 12 → 20). Khi
Odoo 21 (hoặc 22, 23…) ra mắt, **KHÔNG cần sửa skill body, KHÔNG cần
sửa preset gốc, KHÔNG cần sửa intent_router, KHÔNG cần bump tất cả
test**. Chỉ cần drop 5 file reference vào đúng chỗ — Step 0 của mỗi
skill tự đọc `__manifest__.py` của module rồi load reference tương
ứng.

### Bước 1: Drop 5 reference files (BẮT BUỘC)

Đây là phần *bắt buộc duy nhất*. Toolkit tự cascade `17 → 18 → 19 → 20`,
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
> — không có folder `references/`, KHÔNG cần đụng đến.

**Cơ chế hoạt động** (Step 0 của mỗi version-aware skill):

```
1. Đọc __manifest__.py của module đang nhắm tới
2. Parse field 'version': '21.0.x.x.x' → major = 21
3. Load references/odoo-21-<topic>.md
4. Fallback cascade nếu file thiếu: 21 → 20 → 19 → 18 → 17 (12 standalone)
```

→ Nếu anh quên drop `odoo-21-patterns.md`, skill tự fallback về
`odoo-20-patterns.md`. Không crash, không hardcode.

### Bước 2: (Optional) Thêm preset `odoo-21`

Chỉ cần nếu muốn dùng `--preset odoo-21` (default Python version,
stack_label…). Bỏ qua được — toolkit vẫn chạy với `--preset odoo-17`
hoặc `--preset odoo-12`.

`presets/odoo-21.json`:

```json
{
  "description": "Odoo 21 — Python 3.12+, OWL, recordset-by-default",
  "extends": "odoo-17",
  "stack_label": "Odoo 21",
  "stack": {
    "language_version": "3.12",
    "framework_version": "21"
  }
}
```

> **Lưu ý quan trọng**: `extends: odoo-17` đủ rồi. KHÔNG cần khai báo
> lại `rules`, `skills`, `memory_packs` — kế thừa từ parent. KHÔNG ghi
> `"skills": ["_common", "odoo", "odoo-21"]` vì folder `odoo-21/` không
> tồn tại — skill folder chỉ có `odoo/`, version detect tại runtime.

### Bước 3: (Optional) Thêm rules / memory / canonical_decisions per-version

Hoàn toàn optional (fallback về `odoo-17`):

```
templates/cursor/rules/odoo-21/*.mdc                # Cursor IDE rules
templates/memory/odoo-21/*.md                       # memory pack stack-specific
templates/codex/canonical_decisions.odoo-21.json    # registry seed riêng
```

Cursor rules dùng `globs:` per-file nên KHÔNG runtime-detect được — đây
là lý do duy nhất phải copy folder riêng. Nếu Odoo 21 không thay đổi
view syntax / ORM API → bỏ qua bước này.

### Bước 4: Bump toolkit version + CHANGELOG

```python
# lib/installer.py
__version__ = '0.6.0'  # bump khi schema_version đổi hoặc CLI flags break compat
```

Plus CHANGELOG.md entry liệt kê 5 reference files đã thêm.

### Tóm tắt — "Odoo 21 support trong 30 phút"

| File | Bắt buộc? | Effort |
|------|----------|--------|
| 5 × `references/odoo-21-*.md` | ✅ YES | 20 phút (copy `odoo-20-*.md` + chỉnh delta) |
| `presets/odoo-21.json` | ⚠️ Optional | 2 phút |
| `templates/cursor/rules/odoo-21/*.mdc` | ⚠️ Optional | tùy delta view/ORM |
| `templates/memory/odoo-21/*.md` | ⚠️ Optional | tùy delta |
| `templates/codex/canonical_decisions.odoo-21.json` | ⚠️ Optional | tùy delta |
| Skill body / intent_router / preset cũ | ❌ NO TOUCH | 0 phút |

### Bước 5: Verify

```bash
# Test suite vẫn pass sau khi thêm Odoo 21 references
python -m pytest tests/ -v   # 72+ pass, không cần update test nào

# Dry-run install vào project Odoo 21
python ~/agent-toolkit/setup.py init /tmp/test-odoo21 --preset odoo-21 --dry-run
# Hoặc dùng preset cũ — vẫn detect version từ manifest:
python ~/agent-toolkit/setup.py init /tmp/test-odoo21 --preset odoo-17 --dry-run

# Apply thật
python ~/agent-toolkit/setup.py init /path/to/odoo21-proj --preset odoo-21 --yes
```

> **Port sang stack non-Odoo (Django/Rails/FastAPI…)**: technically OK
> qua cơ chế preset, nhưng phải tự author full stack (rules, skills,
> MCP server, canonical_decisions). MCP server shipped (`realdata_test`,
> `jira`) là Odoo-specific. Xem `templates/agent_toolkit/PORTING.md` cho
> hướng dẫn chi tiết.

---

## 10. Verify install

### 10.1. Smoke test (offline, không cần DB)

```bash
python /path/to/project/.codex/tests/test_mcp_wrappers.py
```

27 unit test cho MCP wrappers (transport, env loading, sandbox guards, canonical registry).

### 10.2. Full smoke (có thể cần DB / credentials)

```bash
python /path/to/project/.codex/tests/run_all_tests.py
```

Re-execs dưới venv binary đã configure, chạy toàn bộ test suite + verify_agent_structure.

### 10.3. Smoke MCP servers (live JSON-RPC)

```bash
python /path/to/project/.codex/tests/smoke_mcp_servers.py
```

Spawn từng MCP server qua stdio, gửi `tools/list` thật, kiểm tra response.

---

## 11. Troubleshooting

### 11.1. `UnicodeEncodeError: 'charmap' codec can't encode character '✓'`

Windows console mặc định cp1252, không in được dấu ✓. Fix:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python <TOOLKIT_PATH>\setup.py init ...
```

Hoặc thêm `PYTHONIOENCODING=utf-8` vào shell profile.

### 11.2. `python` resolve sai interpreter (system Python thay vì venv)

Luôn truyền `--python` tuyệt đối:

```bash
python ~/agent-toolkit/setup.py init /path/to/project \
    --preset odoo-12 \
    --python /absolute/path/to/venv/Scripts/python.exe
```

`AGENTS.md` và `canonical_decisions.json` sẽ ghi đường dẫn này nguyên văn để mọi script downstream đều dùng đúng.

### 11.3. Memory không show trong Claude Code

Memory được seed vào `~/.claude/projects/<encoded>/memory/`. Để tìm đúng path:

```bash
python -c "from pathlib import Path; import sys; sys.path.insert(0, '$HOME/agent-toolkit/lib'); from installer import encode_claude_project_path; print(encode_claude_project_path(Path('/path/to/project')))"
```

Nếu Claude Code đang chạy, restart để load memory mới.

### 11.4. MCP server không xuất hiện trong Cursor

Check `.cursor/mcp.json`:

```bash
cat /path/to/project/.cursor/mcp.json
```

Mỗi server phải có `command` (Python interpreter) + `args` (start script tuyệt đối). Nếu trống, re-run `init` với `--python` đúng.

Cursor restart để reload MCP.

### 11.5. Test fail với `FileNotFoundError: jira_server.py` cho Odoo 17

Đã fix — test giờ skip JIRA cases khi preset không cài. Nếu vẫn thấy lỗi, đảm bảo bạn dùng version mới nhất của `templates/codex/tests/test_mcp_wrappers.py`. Re-run `setup.py update`.

### 11.6. Canonical decisions không có entry Odoo 17

Fresh install Odoo 17 phải có **11 entry** (stack, python binary, addon roots, api decorators, loop anti-patterns, sudo, verification, mcp routing, response language, module agnostic, determinism). Verify:

```bash
grep -c '"topic"' /path/to/project/.codex/canonical_decisions.json
# expected: 11
```

Nếu thấy 47 (Odoo 12 file), preset rendering bị sai — toolkit đang dùng default seed thay vì `canonical_decisions.odoo-17.json`. Check:

```bash
ls ~/agent-toolkit/templates/codex/canonical_decisions.odoo-17.json
```

File này phải tồn tại.

---

## 12. FAQ

### Tại sao toolkit là repo riêng, không nhét trong project?

- **Vòng đời khác nhau**: project có thể bị archive, toolkit thì sống tiếp.
- **Tái sử dụng**: 1 toolkit dùng cho N project (Odoo 12, Odoo 17, Odoo 18+ tương lai, plus private overlays per project) mà không phải copy-paste.
- **Commit history sạch**: thay đổi toolkit không lẫn vào git history của project.

### Có thể commit `.codex/` lên Git không?

**Có, và nên.** `.codex/` chứa:
- MCP server impls (code, không phải data)
- `canonical_decisions.json` (kiến thức của project)
- `config.toml.example` (template, không có credential)
- `mcp.local.env.example` (template)

**KHÔNG commit:**
- `.codex/mcp.local.env` (credentials thật — đã có trong `.gitignore`)
- `.cursor/mcp.json` (tự sinh từ máy local — đã có trong `.gitignore`)

Khi đồng nghiệp clone project, họ chỉ cần copy `mcp.local.env.example` → `mcp.local.env`, điền creds, restart Cursor → MCP chạy ngay.

### Memory ở `~/.claude/projects/<encoded>/memory/` có theo project không?

Memory là **per-machine, per-user** (Claude Code lưu cục bộ). Toolkit chỉ **seed** lần đầu. Khi qua máy mới:

1. Clone project về.
2. Chạy `setup.py init` → memory được seed lại từ template (placeholders điền lại theo path mới).
3. Memory user tự thêm trong session sẽ chỉ ở máy hiện tại — muốn portable thì copy ngược vào `templates/memory/<stack>/` trong toolkit và commit.

### Có cần cài Cursor / Claude Code / Codex CLI tất cả không?

Không. Pick một (hoặc nhiều):
- **Cursor** dùng `.cursor/rules/`, `.cursor/skills/`, `.cursor/mcp.json`.
- **Claude Code** dùng `~/.claude/projects/<encoded>/memory/`, `CLAUDE.md`.
- **Codex CLI** dùng `.codex/config.toml` (copy từ `config.toml.example`).
- **AGENTS.md** chung cho mọi agent.

Toolkit cài cả ba — bạn dùng cái nào tuỳ thích.

### Làm sao biết toolkit version nào đã cài cho project?

```bash
cat /path/to/project/agent-toolkit.config.json
```

Ghi: preset, python_bin, psql_bin, project_name, addon_roots, mcp_servers, db, schema version.

(File cũ `.agent-toolkit-install.json` được tự động migrate sang `agent-toolkit.config.json` khi chạy `update`.)

### Toolkit có support Linux / macOS / Windows tất cả không?

Có. Path detection (Python venv, psql) có nhánh per-OS trong `lib/installer.py`. Trên Windows nhớ set `PYTHONIOENCODING=utf-8` để in dấu Unicode.

---

## Tham khảo nhanh

| Lệnh | Mục đích |
|------|----------|
| `setup.py list-presets` | Liệt kê preset có sẵn |
| `setup.py init <path> --preset <name> --yes` | Cài hạ tầng vào project |
| `setup.py init <path> --preset <name> --dry-run` | Xem trước, không ghi |
| `setup.py update <path>` | Refresh project (đọc `agent-toolkit.config.json`) |
| `setup.py update <path> --python /new/python` | Override config tạm thời |
| `python <project>/.codex/tests/test_mcp_wrappers.py` | Verify install (27 MCP-wrapper tests, offline) |
| `python -m pytest <project>/.codex/tests/hooks/ -v` | Full hook suite (120+ tests) |

| File quan trọng (project) | Vai trò |
|---------------------------|---------|
| `agent-toolkit.config.json` | **Config trung tâm** — preset, addon_roots, mcp_servers, db, machine paths |
| `.codex/mcp.local.env` | Credentials (gitignored) |
| `.codex/canonical_decisions.json` | Knowledge registry (curate locally, không bị overwrite) |
| `.cursor/mcp.json` | Cursor MCP wiring (auto-generated, gitignored) |
| `AGENTS.md` | Entry point — render từ template + config |

| File quan trọng (toolkit) | Vai trò |
|---------------------------|---------|
| `presets/<name>.json` | Định nghĩa preset (stack, MCP, rules, memory…) |
| `templates/codex/canonical_decisions.<preset>.json` | Registry seed riêng cho preset |
| `templates/cursor/rules/<stack>/*.mdc` | Rule cho stack |
| `templates/cursor/skills/<stack>/<skill>/SKILL.md` | Skill cho stack |
| `templates/memory/<stack>/*.md` | Memory pack cho stack |
| `templates/AGENTS.md` | Entry point cho mọi agent |

---

**Bug / đề xuất:** mở issue trong repo của toolkit. Pull request thêm preset/rule/skill được hoan nghênh.
