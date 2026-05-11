# agent-toolkit

Reusable Claude Code / Cursor / Codex agent infrastructure. Clone once,
install into any project — Odoo 12, Odoo 17, plain Python, etc.

> **Hướng dẫn chi tiết bằng tiếng Việt:** xem [USAGE.md](USAGE.md).

## What you get

For any project where you run `setup.py init`:

- **`.codex/`** — MCP server implementations (codebase, postgres, jira, realdata_test) + canonical decisions registry + tests
- **`.cursor/rules/`** — Cursor IDE rules (always-apply) for the chosen stack
- **`.cursor/skills/`** — Cursor skills
- **`.cursor/mcp.json`** — auto-generated MCP server config with absolute paths
- **`AGENTS.md`** + **`CLAUDE.md`** — agent entry-points pre-filled with project facts
- **`~/.claude/projects/<encoded>/memory/*.md`** — Claude Code memory seeded with workspace + Python paths
- **`.codex/mcp.local.env`** — credentials template (you fill the secrets)
- **`.gitignore`** snippets

## Quick start

```bash
# Clone toolkit once on any machine
git clone <toolkit-repo> ~/agent-toolkit

# Install into any project
python ~/agent-toolkit/setup.py init /path/to/your/project --preset odoo-12 --yes

# Edit credentials
$EDITOR /path/to/your/project/.codex/mcp.local.env

# Restart Cursor / Claude Code → MCP servers load automatically
```

## Available presets

```bash
python setup.py list-presets
```

| Preset | Stack | MCP servers | Rules | Skills | Memory |
|--------|-------|-------------|-------|--------|--------|
| `odoo-12` | Odoo 12 Enterprise, Python 3.8, QWeb+jQuery, `@api.multi` | codebase, postgres, realdata_test, jira×2 | _common + odoo-12 | _common + odoo-12 | _common + odoo-12 |
| `odoo-17` | Odoo 17, Python 3.10+, OWL, recordset-by-default, `@api.model_create_multi` | codebase, postgres, realdata_test | _common + odoo-17 | _common + odoo-17 | _common + odoo-17 |
| `generic` | Plain Python | codebase | _common | _common | (none) |

Add a new preset by dropping a JSON file into `presets/`. Optionally add
matching `templates/cursor/rules/<name>/` and `templates/memory/<name>/`.

### Shipped skills

| Skill | Scope | What it does |
|-------|-------|--------------|
| `code-review` | `_common` (every preset) | Exhaustive single-pass review — surfaces ALL Blocker + Medium + Low findings in one session, with a reproducible PROOF line per finding. Opens on "review / audit / phân tích sâu / tìm bug / còn gì cần fix?". |
| `odoo-12-code-review` | `odoo-12` | Odoo-12 overlay on `code-review` — `@api.multi`, `attrs/states` (correct in 12), QWeb+jQuery, NAKIVO monkey-patch checklist. |
| `odoo-17-code-review` | `odoo-17` | Odoo-17 overlay — recordset-default ORM, `@api.model_create_multi`, removed `attrs/states`, OWL, removed jQuery. |
| `odoo-17-code-patterns`, `odoo-17-codebase-discovery`, `odoo-17-data-verification`, `odoo-17-module-scaffold` | `odoo-17` | Patterns, MCP routing, real-data verification, scaffolding (unchanged). |

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
├── setup.py                  # CLI entry
├── lib/installer.py          # render + detect helpers
├── presets/
│   ├── odoo-12.json
│   ├── odoo-17.json
│   └── generic.json
├── templates/
│   ├── codex/
│   │   ├── mcp_servers/                      # 5 MCP server impls (codebase, postgres, realdata_test, jira, common)
│   │   ├── start_*_mcp.py                    # stdio launcher wrappers
│   │   ├── canonical_decisions.json          # default seed (Odoo 12 / NAKIVO)
│   │   ├── canonical_decisions.odoo-17.json  # preset-specific seed
│   │   ├── config.toml.example
│   │   ├── mcp.local.env.example
│   │   └── tests/
│   ├── cursor/
│   │   ├── rules/
│   │   │   ├── _common/      # stack-agnostic: karpathy, decision-consistency, mcp-routing, audit-methodology
│   │   │   ├── odoo-12/      # backend, generic, project-context, nakivo-modules
│   │   │   └── odoo-17/      # backend, generic, project-context, data-verification
│   │   └── skills/
│   │       ├── _common/      # code-review (stack-agnostic exhaustive Blocker/Medium/Low pass)
│   │       ├── odoo-12/      # odoo-12-code-review (Odoo-12 overlay on code-review)
│   │       └── odoo-17/      # odoo-17-code-review + codebase-discovery, code-patterns, data-verification, module-scaffold
│   ├── memory/
│   │   ├── _common/          # user_profile, feedback_*, reference_karpathy, MEMORY.md
│   │   ├── odoo-12/          # project_workspace, project_mcp_routing
│   │   └── odoo-17/          # project_workspace, project_mcp_routing
│   ├── AGENTS.md             # template with {{PLACEHOLDERS}}
│   └── CLAUDE.md
└── README.md
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

## Adding a new stack preset (example: Django)

1. Drop `presets/django.json`:
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
  "skills": ["_common"],
  "memory_packs": ["django"]
}
```

2. Optionally add `templates/cursor/rules/django/*.mdc` (Django-specific
   rules). If the dir is missing, only `_common` rules ship.

3. Optionally add `templates/memory/django/*.md` for stack-specific
   memory templates with `{{PLACEHOLDERS}}`.

4. `python setup.py init /path/to/django-proj --preset django` works
   immediately.

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

- `templates/codex/canonical_decisions.json` — default seed (Odoo 12 / NAKIVO).
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

```bash
python /path/to/project/.codex/tests/test_mcp_wrappers.py
# Odoo 12: Ran 27 tests in <X>s — OK
# Odoo 17: Ran 27 tests in <X>s — OK (skipped=6  # JIRA tests skipped, not installed)
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
