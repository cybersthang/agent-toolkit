# AGENTS.md — agent-toolkit upstream

**Audience**: AI agents (Claude Code / Cursor / Codex / Copilot Workspace)
working inside this `agent-toolkit/` directory.

---

## HARD RULE — read this FIRST

When the user asks you to do anything that touches `setup.py init`,
`setup.py update`, or means installing/porting this toolkit into a
project:

**Phrases that trigger this rule** (any language):
- "build agent-toolkit cho project X"
- "rebuild lại toolkit"
- "setup agent-toolkit cho dự án mới"
- "install agent-toolkit vào <path>"
- "port toolkit qua project khác"
- "init/update toolkit"
- "configure toolkit for ..."

**You MUST**:
1. Open and read [`AI_REBUILD_CHECKLIST.md`](AI_REBUILD_CHECKLIST.md)
   in full. It contains the 4-phase Q&A protocol.
2. Walk through every Phase 1 field with the user — DO NOT silently
   default to preset values. Show the preset default + ASK
   "use this or override?".
3. Run Phase 2 validation before invoking `setup.py`.
4. Get explicit user "yes" at Phase 3 confirm before calling `setup.py`.
5. Run Phase 4 post-install verification (pre-commit install, pytest
   smoke, MCP boot check) before reporting "done".

**You MUST NOT**:
- Invoke `setup.py init` with just `--preset <X> --yes` without first
  asking the user the Phase 1 questions. `--yes` skips the toolkit's
  own interactive prompts — that does NOT exempt you from the AI-side
  Q&A. The toolkit assumes the AI gathered consent; if you skipped,
  the user gets misconfigured defaults silently.
- Hard-code project-specific values (addon roots, env var prefixes,
  module names like `nakivo_profiler`, db names like `Nakivo01`) into
  templates. Use `{{PLACEHOLDER}}` and let `setup.py` render at install
  time. See `presets/odoo-12-nakivo.json` for how NAKIVO-specific
  defaults are kept OUT of the generic `odoo-12` preset.
- Copy files from another project's `.codex/` / `.claude/` directly
  into a new target. The toolkit's `setup.py` is the single source of
  truth — running it ensures placeholders render correctly for the new
  ENV_PREFIX, addon roots, etc.

---

## Failure mode this rule prevents

Without the Phase 1 Q&A:
- AI silently picks `--preset odoo-12-nakivo` for a non-NAKIVO project →
  installs `Nakivo01` as default DB + `nakivo` as addon root → toolkit
  is broken on day 1.
- AI assumes Python path from `which python` → ends up pointing at a
  global Python instead of the user's project venv → hooks fail import.
- AI skips post-install pre-commit install → pre-commit gates silently
  don't run at commit time (the user thinks they're protected; they
  aren't).
- AI reports "toolkit installed" before running smoke pytest → first
  real Edit attempt blows up the agent's flow with an unintelligible
  hook error.

The checklist exists because every one of these has happened in a real
session. Read it before you skip it.

---

## Where things live (quick orientation)

| File / dir | Purpose |
|---|---|
| `setup.py` | CLI entry. Commands: `init`, `update`, `list-presets`. Renders templates + writes `agent-toolkit.config.json` into target. |
| `lib/installer.py` | Preset loader + validator + templating helpers. Versioning (`__version__`). |
| `presets/*.json` | Stack/project presets. Generic + extends-overlay convention (e.g. `odoo-12` is generic, `odoo-12-nakivo` extends it with NAKIVO-specific defaults). |
| `templates/` | Files copied/rendered into target. Every `{{KEY}}` must have a corresponding `ctx[KEY]` in `setup.py`. |
| `templates/cursor/` | Cursor IDE rules + skills (per-stack subdirs + `_common/`). |
| `templates/claude/` | Claude Code hooks + slash commands + settings. |
| `templates/codex/` | MCP server implementations + pre-commit hooks + CLI tools (`falsify.py`). |
| `templates/agent_toolkit/` | Files that land in target's `.agent-toolkit/` (registry config, doc) |
| `templates/memory/` | Claude Code per-project memory seeds. |
| `tests/` | Toolkit-level tests (presets / installer / templating). |
| `AI_REBUILD_CHECKLIST.md` | **AI must read this before invoking setup.py.** |
| `USAGE.md` | Human-readable user guide (Vietnamese). |
| `README.md` | Entry pointer. |
| `CHANGELOG.md` | Versioned change log. |

---

## When this rule does NOT apply

- User asks a read-only question about the toolkit ("what does
  preset X include?", "where is the invariant hook?"). Answer
  directly; no Q&A protocol needed.
- User is debugging an already-installed toolkit (a project with
  `agent-toolkit.config.json` present). Use that file as the source of
  values; do NOT re-ask Phase 1.
- User explicitly says "install with all defaults, just do it". Then
  you may proceed — but EMIT a warning showing what preset defaults
  will land + which project-specific fields will be missing. Get one
  more confirmation before running.

---

Last reviewed: 2026-05-18. Toolkit version: see `lib/installer.py:__version__`.
