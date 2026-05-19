# AI Rebuild Checklist — agent-toolkit

**Audience**: AI agents (Claude / Cursor / Codex) tasked with **building or
rebuilding** an agent-toolkit installation on a target project.

**Hard rule**: Read this file FIRST when the user says anything like:
- "build agent-toolkit cho project X"
- "rebuild lại toolkit"
- "setup agent-toolkit cho dự án mới"
- "install agent-toolkit vào <path>"
- "port toolkit qua project khác"

This toolkit is **template-driven** — concrete values (project name, addon
roots, DB name, Python path, env-var prefix) MUST come from the user. The
toolkit ships zero project-specific defaults — silently inheriting any
prior project's values is a known anti-pattern. Project-specific defaults
belong in a **private preset overlay** that `extends` a public preset
(see `templates/agent_toolkit/PORTING.md`).

---

## Phase 0 — Pre-flight (AI must verify before asking user)

| Check | Tool | Block if fails |
|---|---|---|
| Toolkit source exists | `ls <path-to-toolkit-clone>/setup.py` (wherever toolkit cloned) | YES |
| Target path is writable | `Test-Path <target>` / try `mkdir -p` | YES |
| Target is empty OR a git repo | `git -C <target> status` | WARN — ask user confirm overwrite |
| Python ≥ 3.8 available | `python --version` | YES — toolkit needs stdlib |
| Toolkit version | `python setup.py --version` (or read `lib/installer.py:__version__`) | NO — info only |

If any HARD check fails, STOP and report to user. Do NOT proceed.

---

## Phase 1 — Required user inputs (ask EVERY field unless user provided)

> AI MUST NOT silently default. Each field's "Default if user skips"
> column is what you fall back to ONLY after explicit user confirmation
> "use the default". Otherwise: ASK.

### 1.1 Identification (always required)

| Field | Why | Example | Default if user skips | Ask format |
|---|---|---|---|---|
| `TARGET_PATH` | Where toolkit lands | `C:/projects/odoo17-shop` | folder of current cwd | "Path tuyệt đối tới project root?" |
| `PROJECT_NAME` | Identifier baked into config + env-prefix derivation | `odoo17-shop` | basename of `TARGET_PATH` | "Tên project (slug, no spaces)?" |
| `PRESET_NAME` | Template family to install | `odoo-12`, `odoo-17`, `generic`, or a private overlay extending one | NONE — must pick | "Preset nào? Chạy `python setup.py list-presets` xem options" |
| `RESPONSE_LANGUAGE` | Reply language the agent uses | `Vietnamese`, `English`, `日本語` | `English` | "Reply language?" |

### 1.2 Toolchain paths (required for runtime)

| Field | Why | Example | Default if user skips | Validation |
|---|---|---|---|---|
| `PYTHON_BIN` | Hook scripts + MCP servers use this | `C:/Users/<user>/proj/venv/Scripts/python.exe` | auto-detect via `setup.py detect_python()` (looks for `venv/`, `.venv/`, `../venv/`) | File must exist; run `<bin> --version` to confirm ≥ 3.8 |
| `PSQL_BIN` | Postgres MCP wrapper invokes psql | `C:/Program Files/PostgreSQL/16/bin/psql.exe` | auto-detect via `setup.py detect_psql()` | File must exist; only required if `postgres` is in `MCP_SERVERS` |

### 1.3 Stack-specific (Odoo only — skip if preset is `generic`)

| Field | Why | Example | Default if user skips |
|---|---|---|---|
| `ADDON_ROOTS` | Where the codebase MCP indexes addons. Renders into `cursor/rules/<stack>-backend.mdc:globs` AND `cursor/skills/<stack>-codebase-discovery/SKILL.md` AND `coverage_config.json:feature_globs` | `["custom_addons", "OCA", "enterprise"]` | NONE — must ask for Odoo presets (empty → toolkit useless) |
| `ODOO_BIN_REL` | Path to `odoo-bin` relative to TARGET_PATH. Used by `realdata_test` MCP. | `odoo-server/odoo-bin` or `odoo/odoo-bin` | NONE — ask; can leave empty if user doesn't run realdata_test |
| `ODOO_CONF_REL` | Path to odoo.conf relative to TARGET_PATH | `odoo.conf` or `etc/odoo.conf` | NONE — ask; required only if smoke tests run odoo-bin |
| `SMOKE_TEST_REL` | Path to user's custom smoke test script | `scripts/smoke_test.py` | empty → realdata_test MCP returns N/A on smoke calls |

### 1.4 Database (skip if `postgres` not in MCP_SERVERS)

| Field | Why | Example | Default if user skips |
|---|---|---|---|
| `DEFAULT_DB` | Postgres MCP wrapper points here unless overridden per-call | `shop_dev` | NONE — must ask |
| `DEFAULT_PG_HOST` | DB host | `localhost` | `localhost` |
| `DEFAULT_PG_PORT` | DB port | `5432` | `5432` |
| `DEFAULT_PG_USER` | DB user | `odoo` | `postgres` |
| `DEFAULT_PG_PASSWORD` | DO NOT ASK INLINE | (collected separately) | NONE — store in `.codex/mcp.local.env` only, gitignored |

### 1.5 MCP servers (which to wire up)

| Field | Default | Possible values |
|---|---|---|
| `MCP_SERVERS` | from preset (`odoo-12` defaults to `[codebase, postgres, realdata_test, jira_*]`) | any subset of the preset's list |
| `EXTERNAL_MCP_SERVERS` | from preset (`odoo-12` ships `playwright`) | dict; user can add/remove per-server |

If a server requires extra config (e.g. Jira URL + API token), AI MUST
ask for those values and save them to `.codex/mcp.local.env`. NEVER paste
real credentials into `agent-toolkit.config.json` (ADR-004).

### 1.6 Env-var prefix

| Field | Why | Default | Validation |
|---|---|---|---|
| `ENV_PREFIX` | Every MCP wrapper reads `<PREFIX>_PGHOST`, `<PREFIX>_WORKSPACE`, etc. | auto-derived from `PROJECT_NAME` (uppercase, alnum + `_`) | Must match `[A-Z][A-Z0-9_]*`; user can override |

Example: `PROJECT_NAME=odoo17-shop` → auto `ENV_PREFIX=ODOO17_SHOP`.

---

## Phase 2 — Validation (before invoking setup.py)

Run these checks AFTER collecting all answers. Fail-fast on any mismatch.

```text
[ ] TARGET_PATH exists or parent is writable
[ ] PRESET_NAME corresponds to a file in `presets/`
[ ] PYTHON_BIN exists AND runs Python ≥ 3.8
[ ] PSQL_BIN exists IF postgres in MCP_SERVERS
[ ] Each entry in ADDON_ROOTS exists under TARGET_PATH (warn if any missing)
[ ] ODOO_BIN_REL points to an executable file under TARGET_PATH
[ ] ENV_PREFIX matches /^[A-Z][A-Z0-9_]*$/
[ ] No real credential strings in any collected field (use entropy check from .codex/precommit_hooks/credential_guard.py)
```

Report each check + ✓ / ✗ to user. STOP on any ✗.

---

## Phase 3 — Confirm + run

Show user a single summary block:

```text
About to install agent-toolkit with these values:

  Target:       <TARGET_PATH>
  Project name: <PROJECT_NAME>
  Preset:       <PRESET_NAME>
  Language:     <RESPONSE_LANGUAGE>
  Python:       <PYTHON_BIN>
  psql:         <PSQL_BIN>
  Addon roots:  <ADDON_ROOTS>
  Odoo bin:     <ODOO_BIN_REL>
  Odoo conf:    <ODOO_CONF_REL>
  Default DB:   <DEFAULT_DB>
  MCP servers:  <MCP_SERVERS>
  Env prefix:   <ENV_PREFIX>

Proceed? (yes/no)
```

ONLY after explicit "yes", run:

```bash
python <toolkit>/setup.py init <TARGET_PATH> \
  --preset <PRESET_NAME> \
  --python "<PYTHON_BIN>" \
  --psql "<PSQL_BIN>" \
  --project-name "<PROJECT_NAME>"
```

For UPDATE (re-running on an existing install to pull toolkit changes):

```bash
python <toolkit>/setup.py update <TARGET_PATH> --apply
```

Update preserves the project's `agent-toolkit.config.json` answers; it
re-renders templates with the saved values. AI does NOT need to re-ask
Phase 1 questions on update.

---

## Phase 4 — Post-install (AI MUST run before reporting success)

1. **Install pre-commit hook**:
   ```bash
   cd <TARGET_PATH> && <PYTHON_BIN> -m pip install pre-commit
   cd <TARGET_PATH> && <PYTHON_BIN> -m pre_commit install
   ```
   Verify `.git/hooks/pre-commit` exists.

2. **Smoke-test hooks**:
   ```bash
   cd <TARGET_PATH> && <PYTHON_BIN> -m pytest .codex/tests/hooks -q
   ```
   Expected: all tests pass. If any fail with project-specific literal
   strings hardcoded into the toolkit (instead of `{{PLACEHOLDER}}`),
   that's a toolkit bug — file an issue.

3. **Verify env file**:
   - `.codex/mcp.local.env.example` exists
   - User copied → `.codex/mcp.local.env` (gitignored) with their credentials
   - Confirm `.codex/mcp.local.env` is NOT staged in git (`git status` clean)

4. **First-run discovery**:
   ```bash
   cd <TARGET_PATH> && <PYTHON_BIN> .codex/start_codebase_mcp.py --list-tools
   ```
   Confirms MCP server boots without errors.

5. **Report to user**:
   - What was installed (file count)
   - Next steps: "Edit `.agent-toolkit/invariants.json` to register
     project-specific guards. Run `/probe-add` for each new feature."
   - Known untouched-by-toolkit configs: `CLAUDE.md`, `AGENTS.md` (user
     may edit those manually).

---

## Anti-patterns — AI MUST NOT

| Anti-pattern | Why bad | Correct move |
|---|---|---|
| Use a private preset overlay for a project it wasn't built for | Inherits wrong addon root + wrong DB → toolkit broken | Use the public preset (`odoo-12` / `odoo-17` / `generic`); create a new private overlay if needed |
| Hard-code env var name with a project prefix (e.g. `<MYPROJ>_PYTHON_BIN`) | Project-specific env var name | Render `{{ENV_PREFIX}}_PYTHON_BIN` from setup.py ctx |
| Skip `ADDON_ROOTS` for Odoo projects | Cursor rule globs render empty → rule never fires | ASK; never silent-default to `["addons"]` |
| Run `setup.py init` without `--preset` in CI | Falls back to interactive prompt → CI hangs | Always pass `--preset <name> --yes` in non-interactive contexts |
| Install toolkit then commit `mcp.local.env` | Leaks secrets | Verify `.gitignore` covers `**/mcp.local.env` before any git operation |
| Treat preset defaults as user answers | Public presets ship with empty addon_roots — silently inheriting them gives wrong globs | Always SHOW preset defaults to user + ask "use these or override?" |
| Skip Phase 4 smoke-test and report success | Toolkit may install but hooks not wired → silent failure | Always run pytest + first MCP boot before saying done |

---

## Failure-mode playbook

| Symptom | Likely cause | Fix |
|---|---|---|
| Project-specific literal strings (not from `{{PLACEHOLDER}}`) in installed config | Toolkit bug — placeholder missed at render | Update toolkit + re-run `setup.py update --apply`; file an issue if it persists |
| `pre-commit run` says "no hooks installed" | Skipped Phase 4 step 1 | Run `pre-commit install` |
| MCP server fails to boot — "WORKSPACE not set" | ENV_PREFIX mismatch | Check `.codex/mcp.local.env`: must have `<ENV_PREFIX>_WORKSPACE=<TARGET_PATH>` |
| Cursor rule never fires on edit | ADDON_ROOTS empty OR rule glob template not re-rendered | `setup.py update --apply --force-dirty` |
| `evidence-audit` blocks every Stop | `_defaults.required_tool_prefixes` points at MCP server not installed | Edit `acceptance-probes.json` → set to your real MCP prefix |
| pytest fails with UnicodeDecodeError on Windows | Python 3.8 cp1252 subprocess issue | Toolkit ≥ 0.4.0 fixed via `_force_utf8_streams()` in `falsify.py` |

---

## When the user asks "build cho project mới X" — exact dialogue

```
AI: Before I install agent-toolkit at <X>, I need to confirm a few inputs.
    I'll ask each one; reply with the value or "default" to accept the
    fallback I propose.

    1. Target path: <X> — confirm? (yes/edit)
    2. Project name: <derived from path basename> — confirm? (yes/edit)
    3. Which preset? (run `python setup.py list-presets` to see options)
       Options: odoo-12, odoo-17, generic (or your private overlay
       that `extends` one of these).
    4. Reply language: Vietnamese / English / other?
    5. Python interpreter path: <detected or NONE>
       …
```

DO NOT proceed past question 1 without an answer. DO NOT batch questions
unless user explicitly says "ask all at once".

---

## File this checklist is referenced from

- `agent-toolkit/README.md` — entry pointer
- `agent-toolkit/USAGE.md` — full doc
- `agent-toolkit/setup.py` — `init` and `update` commands
- `agent-toolkit/AGENTS.md` (if user created) — agent's project rules

Last reviewed: 2026-05-18 (toolkit v0.4.0 hard-code-removal pass).
