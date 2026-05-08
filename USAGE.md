# agent-toolkit — Hướng Dẫn Sử Dụng

Toolkit này đóng gói toàn bộ hạ tầng AI agent (Claude Code / Cursor / Codex) thành một thư mục có thể tái sử dụng cho nhiều project khác nhau (Odoo 12, Odoo 17, Django, Python thuần…). Clone về một lần, chạy `setup.py init` cho từng project.

## Mục lục

- [1. Cài đặt toolkit lên máy](#1-cài-đặt-toolkit-lên-máy)
- [2. Cài hạ tầng vào một project](#2-cài-hạ-tầng-vào-một-project)
- [3. Sau khi install lần đầu](#3-sau-khi-install-lần-đầu)
- [4. `agent-toolkit.config.json` — config trung tâm](#4-agent-toolkitconfigjson--config-trung-tâm)
- [5. Workflow theo từng preset](#5-workflow-theo-từng-preset)
- [6. Cấu trúc được cài vào project](#6-cấu-trúc-được-cài-vào-project)
- [7. Cập nhật toolkit cho project đã cài](#7-cập-nhật-toolkit-cho-project-đã-cài)
- [8. Thêm preset mới (vd: Django)](#8-thêm-preset-mới-vd-django)
- [9. Verify install](#9-verify-install)
- [10. Troubleshooting](#10-troubleshooting)
- [11. FAQ](#11-faq)

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

Output:
```
Available presets:
  odoo-12   — Odoo 12 Enterprise stack — Python 3.8, QWeb + jQuery, @api.multi
  odoo-17   — Odoo 17 Community / Enterprise — Python 3.10+, OWL frontend
  generic   — Generic Python project — minimal MCP set (codebase only)
```

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

**Windows ví dụ:**

```powershell
python C:\Users\thang.vo\agent-toolkit\setup.py init C:\projects\my-odoo17-app `
    --preset odoo-17 `
    --python C:\projects\my-odoo17-app\venv\Scripts\python.exe `
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

File `.codex/mcp.local.env.example` được render từ template. Copy thành `mcp.local.env` rồi điền:

```
NAKIVO_PGPASSWORD=...           # password Postgres
NAKIVO_JIRA_PRODUCTION_USER=... # JIRA prod (chỉ Odoo 12 preset)
NAKIVO_JIRA_PRODUCTION_PASSWORD=...
NAKIVO_JIRA_PREPRODUCTION_USER=...
NAKIVO_JIRA_PREPRODUCTION_PASSWORD=...
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

## 5. Workflow theo từng preset

### 4.1. Preset `odoo-12` (NAKIVO Odoo 12 Enterprise)

```bash
python ~/agent-toolkit/setup.py init /path/to/Cursor_NAKIVO \
    --preset odoo-12 \
    --python C:/Users/thang.vo/Desktop/NAKIVO/venv/Scripts/python.exe \
    --yes
```

Project nhận:
- **5 MCP servers**: `codebase`, `postgres`, `realdata_test`, `jira_production`, `jira_preproduction`
- **8 cursor rules**: 4 Odoo 12 specific + 4 stack-agnostic (audit, decision-consistency, karpathy, mcp-routing)
- **9 memory files**: workspace, MCP routing, user profile, feedback policy, karpathy reference…
- **canonical_decisions.json**: 47 entry NAKIVO-curated (audit findings, JIRA URLs, profiler decisions)

### 4.2. Preset `odoo-17` (Odoo 17 Community / Enterprise)

```bash
python ~/agent-toolkit/setup.py init /path/to/odoo17-project \
    --preset odoo-17 \
    --python /path/to/odoo17-venv/bin/python \
    --yes
```

Project nhận:
- **3 MCP servers**: `codebase`, `postgres`, `realdata_test` (không có JIRA — thêm sau nếu cần)
- **8 cursor rules**: 4 Odoo 17 specific + 4 stack-agnostic
- **4 cursor skills**: `odoo-17-codebase-discovery`, `odoo-17-data-verification`, `odoo-17-code-patterns`, `odoo-17-module-scaffold`
- **10 memory files**: workspace + MCP routing + 8 file `_common`
- **canonical_decisions.json**: 11 entry generic (recordset-default, `@api.model_create_multi`, OWL…)

Khác biệt chính so với Odoo 12:
- `@api.multi` bị **xoá** — recordset là default
- Override `create()` bắt buộc dùng `@api.model_create_multi(vals_list)`
- View bỏ `attrs="{...}"` và `states="…"` — dùng `invisible="<expr>"` trực tiếp
- Frontend là OWL, không còn jQuery

### 4.3. Preset `generic` (Plain Python)

```bash
python ~/agent-toolkit/setup.py init /path/to/python-app --preset generic --yes
```

Project nhận:
- **1 MCP server**: `codebase` (chỉ discovery, không có Postgres/Odoo)
- **3 cursor rules**: `_common` (audit, decision-consistency, karpathy, mcp-routing)
- **8 memory files**: `_common` only
- Không có Odoo-specific gì

---

## 6. Cấu trúc được cài vào project

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

## 7. Cập nhật toolkit cho project đã cài

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

## 8. Thêm preset mới (vd: Django)

### Bước 1: Drop preset JSON

`presets/django.json`:

```json
{
  "description": "Django project — Python 3.11, Postgres",
  "stack_label": "Django",
  "response_language": "English",
  "stack": {
    "language": "python",
    "language_version": "3.11",
    "framework": "django",
    "framework_version": "5"
  },
  "addon_roots": ["apps", "core"],
  "mcp_servers": ["codebase", "postgres"],
  "db": {"default_db": "myproject", "default_port": 5432, "default_user": "django"},
  "rules": ["_common", "django"],
  "skills": ["_common", "django"],
  "memory_packs": ["django"]
}
```

### Bước 2: (Optional) Drop rules/skills/memory cho stack mới

```
templates/cursor/rules/django/django-models.mdc
templates/cursor/rules/django/django-views.mdc
templates/cursor/skills/django/django-orm-patterns/SKILL.md
templates/memory/django/project_workspace.md
```

Nếu bỏ qua, project chỉ ăn `_common` rules/skills (đã đủ cho karpathy + decision-consistency + audit).

### Bước 3: (Optional) Drop registry seed

`templates/codex/canonical_decisions.django.json` — copy từ `canonical_decisions.odoo-17.json` rồi sửa cho Django (ORM, migrations, admin…).

Nếu bỏ qua, toolkit fallback dùng `canonical_decisions.json` mặc định (bao gồm Odoo 12 entries — không phù hợp Django; nên drop bản riêng).

### Bước 4: Test

```bash
python ~/agent-toolkit/setup.py init /tmp/test-django --preset django --yes
```

---

## 9. Verify install

### 8.1. Smoke test (offline, không cần DB)

```bash
python /path/to/project/.codex/tests/test_mcp_wrappers.py
```

27 unit test cho MCP wrappers (transport, env loading, sandbox guards, canonical registry).

### 8.2. Full smoke (có thể cần DB / credentials)

```bash
python /path/to/project/.codex/tests/run_all_tests.py
```

Re-execs dưới venv binary đã configure, chạy toàn bộ test suite + verify_agent_structure.

### 8.3. Smoke MCP servers (live JSON-RPC)

```bash
python /path/to/project/.codex/tests/smoke_mcp_servers.py
```

Spawn từng MCP server qua stdio, gửi `tools/list` thật, kiểm tra response.

---

## 10. Troubleshooting

### 9.1. `UnicodeEncodeError: 'charmap' codec can't encode character '✓'`

Windows console mặc định cp1252, không in được dấu ✓. Fix:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python C:\Users\thang.vo\agent-toolkit\setup.py init ...
```

Hoặc thêm `PYTHONIOENCODING=utf-8` vào shell profile.

### 9.2. `python` resolve sai interpreter (system Python thay vì venv)

Luôn truyền `--python` tuyệt đối:

```bash
python ~/agent-toolkit/setup.py init /path/to/project \
    --preset odoo-12 \
    --python /absolute/path/to/venv/Scripts/python.exe
```

`AGENTS.md` và `canonical_decisions.json` sẽ ghi đường dẫn này nguyên văn để mọi script downstream đều dùng đúng.

### 9.3. Memory không show trong Claude Code

Memory được seed vào `~/.claude/projects/<encoded>/memory/`. Để tìm đúng path:

```bash
python -c "from pathlib import Path; import sys; sys.path.insert(0, '$HOME/agent-toolkit/lib'); from installer import encode_claude_project_path; print(encode_claude_project_path(Path('/path/to/project')))"
```

Nếu Claude Code đang chạy, restart để load memory mới.

### 9.4. MCP server không xuất hiện trong Cursor

Check `.cursor/mcp.json`:

```bash
cat /path/to/project/.cursor/mcp.json
```

Mỗi server phải có `command` (Python interpreter) + `args` (start script tuyệt đối). Nếu trống, re-run `init` với `--python` đúng.

Cursor restart để reload MCP.

### 9.5. Test fail với `FileNotFoundError: jira_server.py` cho Odoo 17

Đã fix — test giờ skip JIRA cases khi preset không cài. Nếu vẫn thấy lỗi, đảm bảo bạn dùng version mới nhất của `templates/codex/tests/test_mcp_wrappers.py`. Re-run `setup.py update`.

### 9.6. Canonical decisions không có entry Odoo 17

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

## 11. FAQ

### Tại sao toolkit là repo riêng, không nhét trong project?

- **Vòng đời khác nhau**: project có thể bị archive, toolkit thì sống tiếp.
- **Tái sử dụng**: 1 toolkit dùng cho N project (Odoo 12 → 17 → Django…) mà không phải copy-paste.
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
| `python <project>/.codex/tests/test_mcp_wrappers.py` | Verify install (27 tests) |

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
