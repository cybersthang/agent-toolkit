---
name: test-env-bootstrap
description: Auto-discover test server URL, DB, creds, and process_manager from project config files. Emits/updates `.agent-toolkit/test_env.json` (v2 schema) so AGENT can drive browser-driver / daemon_manager / creds_resolver hooks without DEV intervention. Triggered explicitly via `/test-env-bootstrap [--force]` or implicitly on first `/run-probes` when `test_env.json` is missing or `schema_version < 2`.
---

# test-env-bootstrap

## Goal

Replace the manual "DEV pastes URL + login + password into chat" workflow with auto-discovery from project files. Every supported stack publishes its HTTP port, credential strategy, and start command somewhere conventional — we scan those locations and emit a v2 `test_env.json`.

Project-agnostic: NO stack name hardcoded. Discovery rules below cover Odoo, Django, Rails, and a generic fallback. New stacks plug in via `templates/agent_toolkit/test_env_discovery/<stack>.py`.

## Discovery sources (priority order)

| Stack | URL source | DB source | Start cmd source |
|---|---|---|---|
| Odoo | `*.conf` → `http_port = <N>` | `*.conf` → `db_name =` OR preset.json `default_db` | preset.json `boot_cmd_template` |
| Django | `manage.py` runserver default OR `settings.py` `ALLOWED_HOSTS` | `settings.DATABASES.default.NAME` | `python manage.py runserver` |
| Rails | `config/puma.rb` / `config/application.rb` | `config/database.yml` `<env>.database` | `bin/rails server` |
| Generic | `agent-toolkit.config.json.test_env_url` | manual | `agent-toolkit.config.json.stack.boot_cmd` |

## Workflow

1. **Detect stack** from `.agent-toolkit/agent_toolkit.config.json.preset` (e.g. `odoo-17`).
2. **Locate config file** per stack:
   - Odoo: search `*.conf` upward from project root.
   - Django: locate `manage.py`.
   - Rails: locate `config/application.rb`.
3. **Parse port + DB**:
   - Odoo: regex `http_port\s*=\s*(\d+)` and `db_name\s*=\s*([\w_-]+)`.
   - Django: import settings (sandboxed exec) or regex.
   - Rails: YAML parse.
4. **Resolve creds_ref**:
   - Scan `.codex/mcp.local.env` for any var matching `*_LOGIN` / `*_PASSWORD` patterns.
   - If none found AND preset has a `default_test_credentials_ref` field → use that.
   - Else fall back to stack-default (Odoo: `admin/admin`; Django: `admin/admin` per superuser convention).
5. **Build process_manager**:
   - Use preset's `boot_cmd_template` with `{PLACEHOLDER}` interpolated from `agent_toolkit.config.json`.
   - `health_check_url`: stack-default (`/web/login` Odoo, `/admin/login/` Django, `/` Rails).
   - `shutdown_signal`: detect platform → `Stop-Process` on Windows, `SIGTERM` elsewhere.
6. **Emit** `.agent-toolkit/test_env.json` matching v2 schema.
7. **Validate** against `test_env.schema.json` — abort if any required field missing + tell DEV what to fill.

## Inputs

- `--force`: overwrite existing test_env.json without confirmation.
- `--dry-run`: print discovered values, don't write.

## Outputs

`.agent-toolkit/test_env.json` per schema v2.

## Refuse / clarify when

- Stack preset not registered → output discovered defaults + ask DEV to confirm.
- Multiple config files found → list candidates + ask DEV which to use.
- Creds resolution returns empty → ask DEV to add env vars to `.codex/mcp.local.env` then re-run.

## Inputs the skill MUST NOT do

- Persist real passwords into `.agent-toolkit/test_env.json` (always env-var references).
- Hard-code stack-specific paths in discovery code (use the per-stack `discovery/<stack>.py` plugin pattern).
- Skip schema validation — silent writes lead to downstream creds_resolver failures.

## Linked patches in this Sprint

- D1 schema v2 (this skill consumes it).
- D2 probes schema extension (probes reference test_env via creds_ref).
- C1 evidence_audit recognizes probe output that quotes test_env data.

## Public extension hook

Plugin authors add new stacks by dropping `templates/agent_toolkit/test_env_discovery/<stack>.py` with a function `discover(project_root: Path) -> dict`. The skill auto-loads matching the preset's `stack.discovery_module` field.
