# SPDX-License-Identifier: MIT
"""agent-toolkit — install Claude Code / Cursor / Codex agent infrastructure
into an Odoo workspace, configured for a specific Odoo version + variant.

Shipped presets (3):

    odoo-12   — Odoo 12 (Python 3.8, QWeb + jQuery, @api.multi era)
    odoo-17   — Odoo 17 (Python 3.10+, OWL, recordset, @api.model_create_multi)
    generic   — Plain Python fallback (not the primary path for Odoo)

The toolkit's core (hooks, invariants, Spec Kit workflow) is stack-agnostic,
but the shipped rules, skills, MCP servers, and canonical decisions are
tuned for Odoo. Project-specific defaults (addon roots, default DB, JIRA
endpoints, Enterprise overlays) belong in a private preset overlay that
extends the public preset — see templates/agent_toolkit/PORTING.md.

Non-Odoo stacks (Django/Rails/...) can be added via preset extension —
see templates/agent_toolkit/PORTING.md.

Run from the toolkit directory:

    # Interactive: pick preset + ask for paths
    python setup.py init /path/to/project

    # Non-interactive: pass everything on CLI
    python setup.py init /path/to/project \
        --preset odoo-12 \
        --python /path/to/venv/bin/python \
        --psql /usr/bin/psql

    # Refresh from latest toolkit (preserves user's mcp.local.env)
    # Dry-run + diff by default; pass --apply to write.
    python setup.py update /path/to/project

    # Show what would be written without touching disk
    python setup.py init /path/to/project --preset odoo-17 --dry-run

Presets live in presets/<name>.json. Adding a new Odoo version means
adding a preset (often via `extends: odoo-17`) + (optionally) a new
rules/<stack>/ folder and canonical_decisions.<preset>.json seed.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Windows console default cp1252 cannot encode UTF-8 status glyphs (✓).
# Reconfigure stdout/stderr to UTF-8 so `ok(✓ ...)` does not crash mid-apply.
# Python 3.7+ has `reconfigure`; older versions silently skip.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure') and getattr(_stream, 'encoding', '').lower() != 'utf-8':
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

TOOLKIT_ROOT = Path(__file__).resolve().parent
TEMPLATES = TOOLKIT_ROOT / 'templates'
PRESETS_DIR = TOOLKIT_ROOT / 'presets'
LIB_DIR = TOOLKIT_ROOT / 'lib'
sys.path.insert(0, str(LIB_DIR))

from installer import (  # noqa: E402
    __version__,
    load_preset, render_text, render_into,
    detect_python, detect_psql, encode_claude_project_path,
    confirm, info, warn, ok,
    validate_preset, resolve_preset, git_dirty_status,
)


# Project-level config file. Captures the effective settings for an installed
# project so `update` can re-run with the same shape, and so users can edit
# overrides (addon_roots, mcp_servers, db, python_bin) without touching the
# toolkit's preset JSON or re-passing CLI flags.
PROJECT_CONFIG_NAME = 'agent-toolkit.config.json'
LEGACY_CONFIG_NAME = '.agent-toolkit-install.json'


def load_project_config(target: Path) -> Optional[Dict[str, Any]]:
    """Return parsed project config dict, or None if neither file exists.

    Tries `agent-toolkit.config.json` first, then the legacy
    `.agent-toolkit-install.json` for backward compatibility.
    """
    cfg_path = target / PROJECT_CONFIG_NAME
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding='utf-8'))
    legacy = target / LEGACY_CONFIG_NAME
    if legacy.exists():
        warn(f'Found legacy {LEGACY_CONFIG_NAME}; will migrate to {PROJECT_CONFIG_NAME}')
        return json.loads(legacy.read_text(encoding='utf-8'))
    return None


def write_project_config(target: Path, ctx: Dict[str, Any], preset_name: str):
    """Persist the resolved config so `update` can re-run consistently."""
    cfg = {
        '_managed_by': 'agent-toolkit',
        '_schema_version': 1,
        '_doc': (
            'Edit this file to override preset defaults for this project. '
            'CLI flags > this file > preset defaults. Run '
            '`python <toolkit>/setup.py update <project>` after editing.'
        ),
        'preset': preset_name,
        'project_name': ctx.get('PROJECT_NAME', ''),
        'workspace_root': ctx.get('WORKSPACE_ROOT', ''),
        'response_language': ctx.get('RESPONSE_LANGUAGE', 'English'),
        'stack': {
            'language': ctx.get('STACK_LANGUAGE', ''),
            'language_version': ctx.get('STACK_LANGUAGE_VERSION', ''),
            'framework': ctx.get('STACK_FRAMEWORK', ''),
            'framework_version': ctx.get('STACK_FRAMEWORK_VERSION', ''),
            'label': ctx.get('STACK_LABEL', ''),
            # Stack-specific binary paths — preserved so user overrides
            # survive `setup.py update`. Empty = inherit from preset.
            'odoo_bin_rel': ctx.get('ODOO_BIN_REL', ''),
            'odoo_conf_rel': ctx.get('ODOO_CONF_REL', ''),
            'smoke_test_rel': ctx.get('SMOKE_TEST_REL', ''),
        },
        'addon_roots': list(ctx.get('ADDON_ROOTS', []) or []),
        'mcp_servers': list(ctx.get('MCP_SERVERS', []) or []),
        'external_mcp_servers': dict(ctx.get('EXTERNAL_MCP_SERVERS', {}) or {}),
        'env_prefix': ctx.get('ENV_PREFIX', ''),
        'db': {
            'default_db': ctx.get('DEFAULT_DB', ''),
            'default_port': int(ctx.get('DEFAULT_PG_PORT') or 5432),
        },
        'machine_local': {
            '_doc': 'Machine-specific paths. Consider gitignoring or per-developer overrides.',
            'python_bin': ctx.get('PYTHON_BIN', ''),
            'psql_bin': ctx.get('PSQL_BIN', ''),
        },
    }
    cfg_path = target / PROJECT_CONFIG_NAME
    cfg_path.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    ok(f'  wrote {PROJECT_CONFIG_NAME}')
    legacy = target / LEGACY_CONFIG_NAME
    if legacy.exists():
        legacy.unlink()
        info(f'  removed legacy {LEGACY_CONFIG_NAME}')


# -----------------------------------------------------------------------
def cmd_list_presets(args):
    presets = sorted({p.stem for p in PRESETS_DIR.glob('*.json')}
                     | {p.stem for p in PRESETS_DIR.glob('*.yaml')})
    print('Available presets:')
    for p in presets:
        path = PRESETS_DIR / f'{p}.json'
        if not path.exists():
            path = PRESETS_DIR / f'{p}.yaml'
        meta = load_preset(path)
        print(f'  {p:<20} — {meta.get("description", "")}')


def cmd_init(args):
    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)

    # 0. Load existing project config (if any). Values from this file act as
    #    defaults below preset-baked defaults but above auto-detection.
    #    Priority: CLI flag > project config > preset default > auto-detect.
    project_cfg: Dict[str, Any] = load_project_config(target) or {}
    machine_cfg = project_cfg.get('machine_local') or {}

    # 1. Resolve preset name (CLI > config > interactive prompt)
    if not args.preset:
        args.preset = project_cfg.get('preset')
    if not args.preset:
        presets = sorted({p.stem for p in PRESETS_DIR.glob('*.json')}
                         | {p.stem for p in PRESETS_DIR.glob('*.yaml')})
        # Filter out per-preset registry seeds like canonical_decisions.odoo-17
        presets = [p for p in presets if not p.startswith('canonical_decisions')]
        print('Available presets:')
        for i, p in enumerate(presets, 1):
            print(f'  {i}. {p}')
        idx = input(f'Pick preset [1-{len(presets)}]: ').strip()
        try:
            args.preset = presets[int(idx) - 1]
        except Exception:
            sys.exit('aborted')

    # Use resolve_preset so `extends:` inheritance and *_append additive
    # overrides work transparently. Validation runs as part of resolution.
    try:
        preset = resolve_preset(args.preset, PRESETS_DIR)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(str(exc))
    info(f'Using preset: {args.preset}')
    info(f'  description: {preset.get("description", "")}')
    info(f'  stack: {preset.get("stack", {})}')
    if preset.get('_inherited_from'):
        info(f'  extends: {preset["_inherited_from"]}')
    if project_cfg:
        info(f'  honoring overrides from {PROJECT_CONFIG_NAME}')

    # 2. Resolve every field with CLI > config > preset > detect priority.
    py_bin = (
        args.python
        or machine_cfg.get('python_bin')
        or project_cfg.get('python_bin')   # legacy flat shape
        or detect_python(target)
    )
    psql_bin = (
        args.psql
        or machine_cfg.get('psql_bin')
        or project_cfg.get('psql_bin')
        or detect_psql()
    )

    if not args.yes:
        py_bin = input(f'Python binary [{py_bin or "?"}]: ').strip() or py_bin
        psql_bin = input(f'psql binary [{psql_bin or "?"}]: ').strip() or psql_bin

    project_name = (
        args.project_name
        or project_cfg.get('project_name')
        or target.name
    )

    addon_roots = (
        project_cfg.get('addon_roots')
        or preset.get('addon_roots', [])
        or []
    )
    mcp_servers = (
        project_cfg.get('mcp_servers')
        or preset.get('mcp_servers', [])
        or []
    )
    # External (non-Python) MCP servers shipped verbatim from preset config.
    # Used for npm-based MCPs like `@playwright/mcp`. Project-level
    # `external_mcp_servers` overrides preset; otherwise preset wins.
    # Stays an empty dict when neither defines any.
    external_mcp_servers = (
        project_cfg.get('external_mcp_servers')
        if isinstance(project_cfg.get('external_mcp_servers'), dict)
        else None
    )
    if external_mcp_servers is None:
        external_mcp_servers = preset.get('external_mcp_servers') or {}
    if not isinstance(external_mcp_servers, dict):
        external_mcp_servers = {}

    db_cfg = project_cfg.get('db') or preset.get('db', {}) or {}
    response_language = (
        project_cfg.get('response_language')
        or preset.get('response_language', 'English')
    )
    stack_cfg = project_cfg.get('stack') or {}
    preset_stack = preset.get('stack', {}) or {}

    # Stack-specific binary paths (Odoo only) — never hard-code into
    # templates. Resolution order: project_cfg.stack.<key> > preset.stack.<key>
    # > empty string. Empty string is intentional: it signals "user did
    # not configure" to the consuming template, which then prints a
    # helpful "set <PREFIX>_ODOO_BIN env var to use" message instead of
    # silently pointing at a non-existent path.
    odoo_bin_rel = (
        stack_cfg.get('odoo_bin_rel')
        or preset_stack.get('odoo_bin_rel')
        or ''
    )
    odoo_conf_rel = (
        stack_cfg.get('odoo_conf_rel')
        or preset_stack.get('odoo_conf_rel')
        or ''
    )
    smoke_test_rel = (
        stack_cfg.get('smoke_test_rel')
        or preset_stack.get('smoke_test_rel')
        or ''
    )

    # ADDON_GLOBS = brace-expanded form of ADDON_ROOTS for cursor-rules
    # `globs:` lines, e.g. ["addons", "OCA"] → "{addons,OCA}/**/*".
    # Empty addon_roots → "*" (matches everything; the rule effectively
    # always applies, which is the right behavior for an
    # unconfigured stack — the rule body still has the constraints).
    if addon_roots:
        if len(addon_roots) == 1:
            addon_globs = f"{addon_roots[0]}/**/*"
        else:
            addon_globs = "{" + ",".join(addon_roots) + "}/**/*"
    else:
        addon_globs = "**/*"

    # ENV_PREFIX governs the env-var prefix used by every MCP wrapper +
    # server (`<PREFIX>_PGHOST`, `<PREFIX>_JIRA_*`, `<PREFIX>_WORKSPACE`).
    # Priority: CLI not exposed yet > project config > preset default >
    # auto-derive from project name. Stays uppercase, alphanum + underscore.
    env_prefix = (
        project_cfg.get('env_prefix')
        or preset.get('env_prefix')
        or re.sub(r'[^A-Z0-9_]', '_', project_name.upper()).strip('_')
        or 'PROJECT'
    )

    ctx: Dict[str, Any] = {
        'WORKSPACE_ROOT': str(target).replace('\\', '/'),
        'WORKSPACE_NAME': project_name,
        'PROJECT_NAME': project_name,
        'PYTHON_BIN': str(py_bin or '').replace('\\', '/'),
        'PSQL_BIN': str(psql_bin or '').replace('\\', '/'),
        'STACK_LANGUAGE': stack_cfg.get('language') or preset_stack.get('language', 'python'),
        'STACK_LANGUAGE_VERSION': stack_cfg.get('language_version') or preset_stack.get('language_version', '3'),
        'STACK_FRAMEWORK': stack_cfg.get('framework') or preset_stack.get('framework', ''),
        'STACK_FRAMEWORK_VERSION': stack_cfg.get('framework_version') or preset_stack.get('framework_version', ''),
        'STACK_LABEL': stack_cfg.get('label') or preset.get('stack_label')
            or '%s %s' % (
                preset_stack.get('framework', '').title(),
                preset_stack.get('framework_version', '')),
        'ADDON_ROOTS': addon_roots,
        'ADDON_ROOTS_CSV': ', '.join(addon_roots),
        'ADDON_GLOBS': addon_globs,
        'ODOO_BIN_REL': odoo_bin_rel,
        'ODOO_CONF_REL': odoo_conf_rel,
        'SMOKE_TEST_REL': smoke_test_rel,
        'DEFAULT_DB': db_cfg.get('default_db', ''),
        'DEFAULT_PG_PORT': str(db_cfg.get('default_port', 5432)),
        'MCP_SERVERS': mcp_servers,
        'MCP_SERVERS_CSV': ', '.join(mcp_servers),
        'EXTERNAL_MCP_SERVERS': external_mcp_servers,
        'PRESET_NAME': args.preset,
        'RESPONSE_LANGUAGE': response_language,
        'ENV_PREFIX': env_prefix,
        'PROJECT_NAME_SLUG': re.sub(r'[^a-z0-9_]', '_',
                                    project_name.lower()).strip('_') or 'project',
        'TODAY_ISO_DATE': datetime.date.today().isoformat(),
    }

    info('\nResolved context:')
    for k, v in ctx.items():
        info(f'  {k}: {v}')

    if args.dry_run:
        info('\n[dry-run] target: ' + str(target))
        plan = build_plan(preset, ctx, target)
        new_n, changed_n, unchanged_n, skipped_n = 0, 0, 0, 0
        diff_enabled = getattr(args, 'diff', False)
        for src, dst, mode in plan:
            rel = dst.relative_to(target)
            if mode == 'SKIP_EXISTS':
                skipped_n += 1
                if dst.exists():
                    continue
            if not dst.exists():
                print(f'  NEW       {rel}')
                new_n += 1
            elif _content_will_change(src, dst, mode, ctx):
                print(f'  MODIFY    {rel}')
                if diff_enabled:
                    _print_diff(src, dst, mode, ctx)
                changed_n += 1
            else:
                unchanged_n += 1
        info(f'\n[dry-run] {new_n} new, {changed_n} modified, '
             f'{unchanged_n} unchanged, {skipped_n} skip-exists')
        info('[dry-run] would also seed memory into:')
        info(f'  {encode_claude_project_path(target)}')
        info('[dry-run] Run with --apply to write changes')
        return

    if not args.yes and not confirm(f'Install into {target}? [y/N]: '):
        sys.exit('aborted')

    backup_enabled = getattr(args, 'backup', False)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    plan = build_plan(preset, ctx, target)

    # Tier 2: two-pass atomic apply.
    # Pass 1 (pre-render): materialize all template outputs in memory so
    # a render failure aborts BEFORE any disk write. Catches missing
    # placeholders, encoding errors, unreadable sources up-front.
    materialized = []
    for src, dst, mode in plan:
        if mode == 'SKIP_EXISTS':
            continue
        new_content: Optional[str] = None
        if mode == 'TEMPLATE':
            new_content = render_text(
                src.read_text(encoding='utf-8'), ctx
            )
        materialized.append((src, dst, mode, new_content))

    # Pass 2 (write): per-file atomic via temp + os.replace, so an
    # interrupted write never leaves a half-written destination.
    backed_up = 0
    total = len(materialized)
    for i, (src, dst, mode, new_content) in enumerate(materialized, 1):
        # H4 backup: only when content actually differs from disk.
        will_change = _content_will_change(src, dst, mode, ctx)
        if backup_enabled and dst.exists() and will_change:
            backup_path = dst.with_suffix(dst.suffix + f'.bak.{ts}')
            shutil.copy2(dst, backup_path)
            backed_up += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + '.tmp')
        if mode == 'COPY':
            shutil.copy2(src, tmp)
        else:  # TEMPLATE
            tmp.write_text(new_content or '', encoding='utf-8')
        os.replace(tmp, dst)
        # Progress prefix for large file sets.
        prefix = f'[{i}/{total}]' if total > 30 else ''
        ok(f'{prefix:<8} {mode:<10} {dst.relative_to(target)}')
    if backed_up:
        info(f'  backed up {backed_up} pre-existing file(s) as *.bak.{ts}')

    seed_memory(preset, ctx, target, force=args.force)
    write_mcp_configs(ctx, target, force=args.force)
    write_gitignore(target)
    write_project_config(target, ctx, args.preset)

    print()
    ok('install complete.')
    info('Next:')
    info(f'  1. Edit {target}/.codex/mcp.local.env — fill PASSWORD + JIRA creds')
    info(f'  2. Edit {target}/{PROJECT_CONFIG_NAME} to override addon_roots,')
    info('     mcp_servers, db etc. then re-run `setup.py update <project>`')
    info('  3. Restart Cursor / Claude Code')
    info(f'  4. Verify: python {target}/.codex/tests/test_mcp_wrappers.py')


def cmd_update(args):
    """Refresh templates/scripts but preserve user's mcp.local.env.

    Reads `agent-toolkit.config.json` (or legacy `.agent-toolkit-install.json`)
    from the target. Project config takes precedence over preset defaults, so
    edits to addon_roots/mcp_servers/db propagate on update.

    Safe-by-default (B1 fix): with no flags, runs as dry-run + diff so the
    user can review changes before applying. Pass `--apply` to write.
    Backups of pre-existing files are created automatically when applying;
    opt out with `--no-backup`.
    """
    target = Path(args.target).resolve()
    cfg = load_project_config(target)
    if cfg is None:
        sys.exit(
            f'No {PROJECT_CONFIG_NAME} or {LEGACY_CONFIG_NAME} at {target}; '
            'use `init` instead'
        )
    # Only seed the args that aren't already set; cmd_init re-reads the
    # config itself for the rich override merge.
    args.preset = args.preset or cfg.get('preset')
    args.project_name = args.project_name or cfg.get('project_name')
    machine = cfg.get('machine_local') or {}
    args.python = args.python or machine.get('python_bin') or cfg.get('python_bin')
    args.psql = args.psql or machine.get('psql_bin') or cfg.get('psql_bin')
    args.yes = True
    # Safe default: dry-run with diff unless --apply is given.
    args.dry_run = not getattr(args, 'apply', False)
    # Backup ON by default when applying; --no-backup to opt out.
    args.backup = (
        getattr(args, 'apply', False)
        and not getattr(args, 'no_backup', False)
    )
    # `--force` only forces overwriting SKIP_EXISTS files
    # (canonical_decisions.json, .agent-toolkit/invariants.json...).
    # Default OFF so curated state survives.
    args.force = bool(getattr(args, 'force', False))
    mode_label = 'APPLY' if not args.dry_run else 'DRY-RUN'
    info(f'Updating using saved preset: {args.preset}')
    info(f'  mode={mode_label}  backup={args.backup}  force={args.force}')

    # Tier 3: git-aware safety. Refuse to apply over a dirty working tree
    # unless user passes --force-dirty or the project isn't a git repo.
    if not args.dry_run and not getattr(args, 'force_dirty', False):
        dirty = git_dirty_status(target)
        if dirty:
            sys.exit(
                f'\nrefusing to --apply: {target} has {dirty}.\n'
                f'  Commit or stash first, or pass --force-dirty to override.\n'
                f'  (Backups will still be written to *.bak.{datetime.datetime.now():%Y%m%d-%H%M%S})'
            )

    cmd_init(args)


# -----------------------------------------------------------------------
def build_plan(preset, ctx, target):
    """Decide for each toolkit file: copy raw, template, or skip.

    `ctx['MCP_SERVERS']` is honored over `preset['mcp_servers']` so a project
    config can drop or add MCP servers without forking the preset.
    """
    plan: List = []
    rules_set = preset.get('rules', ['_common'])
    skills_set = preset.get('skills', ['_common'])
    mcp_set = set(ctx.get('MCP_SERVERS') or preset.get('mcp_servers', []))

    # 1. .codex/ tree — MCP server impls + scripts
    codex_src = TEMPLATES / 'codex'
    preset_name = ctx.get('PRESET_NAME')
    # Pick preset-specific canonical_decisions seed; fall back to the
    # `generic` variant when the preset has no dedicated file. Variants
    # live as `canonical_decisions.<preset>.json` next to each other.
    # NOTE: pre-v0.13 shipped an unsuffixed `canonical_decisions.json`
    # holding the odoo-12 default — that file has been renamed to
    # `canonical_decisions.odoo-12.json` so every preset is explicit.
    canonical_fallback = codex_src / 'canonical_decisions.generic.json'
    canonical_preset = codex_src / f'canonical_decisions.{preset_name}.json'
    canonical_chosen = canonical_preset if canonical_preset.exists() else canonical_fallback
    for src in codex_src.rglob('*'):
        if not src.is_file():
            continue
        rel = src.relative_to(codex_src)
        rel_str = str(rel).replace('\\', '/')
        # Skip noise that's machine-local or project-specific
        if '__pycache__' in rel.parts or src.suffix == '.pyc':
            continue
        if rel.name.startswith('_') and src.suffix == '.py' and len(rel.parts) <= 1:
            # Skip top-level `.codex/_foo.py` ad-hoc probe scripts (toolkit
            # ships none today; defensive guard). DON'T skip nested
            # `tests/hooks/_helpers.py` or `_audit/_*.py` — those are
            # shared test infrastructure that MUST ship.
            continue
        # canonical_decisions handling: only ship the chosen variant, never
        # the others. Output filename is always `canonical_decisions.json`.
        if rel.name.startswith('canonical_decisions') and rel.name.endswith('.json'):
            if src != canonical_chosen:
                continue
            dst = target / '.codex' / 'canonical_decisions.json'
            if dst.exists():
                # Never overwrite a project's existing registry on update.
                plan.append((src, dst, 'SKIP_EXISTS'))
            else:
                plan.append((src, dst, 'TEMPLATE'))
            continue
        if rel_str.startswith('mcp_servers/') and rel_str.endswith('.py'):
            stem = rel.parts[1]
            # Skip if not a server file the preset asked for. `common.py` is
            # the shared helper imported by every server — always include it.
            if stem == 'common.py':
                pass  # always include
            elif stem.endswith('_server.py'):
                srv_name = stem[:-len('_server.py')]
                # `jira_server.py` is shared by jira_production +
                # jira_preproduction profiles via env-var mapping. Include
                # it if ANY profile name starts with the server stem.
                included = (
                    srv_name in mcp_set
                    or any(name.startswith(srv_name + '_') for name in mcp_set)
                )
                if not included:
                    continue
            else:
                # Unknown file under mcp_servers/ — skip
                continue
        if rel.name.startswith('start_') and rel.name.endswith('_mcp.py'):
            srv_name = rel.stem.replace('start_', '').replace('_mcp', '')
            if srv_name not in mcp_set:
                continue
        # Skip user's existing mcp.local.env
        if rel.name == 'mcp.local.env':
            continue
        dst = target / '.codex' / rel
        is_template = src.suffix in ('.j2', '.tmpl') or _looks_templated(src)
        if rel.name == 'mcp.local.env.example':
            is_template = True
        plan.append((src, dst, 'TEMPLATE' if is_template else 'COPY'))

    # 2. .cursor/rules/<stack> + _common
    cursor_rules_src = TEMPLATES / 'cursor' / 'rules'
    for stack in rules_set:
        stack_dir = cursor_rules_src / stack
        if not stack_dir.exists():
            warn(f'rules/{stack} not in toolkit, skipping')
            continue
        for src in stack_dir.glob('*.mdc'):
            dst = target / '.cursor' / 'rules' / src.name
            plan.append((src, dst, 'TEMPLATE' if _looks_templated(src) else 'COPY'))

    # 3. .cursor/skills
    skills_src = TEMPLATES / 'cursor' / 'skills'
    for stack in skills_set:
        stack_dir = skills_src / stack
        if not stack_dir.exists():
            continue
        for src in stack_dir.rglob('*'):
            if not src.is_file():
                continue
            dst = target / '.cursor' / 'skills' / src.relative_to(stack_dir)
            plan.append((src, dst, 'TEMPLATE' if _looks_templated(src) else 'COPY'))

    # 4. AGENTS.md + CLAUDE.md + .pre-commit-config.yaml
    for top_template in ('AGENTS.md', 'CLAUDE.md'):
        src = TEMPLATES / top_template
        if src.exists():
            plan.append((src, target / top_template, 'TEMPLATE'))
    # Pre-commit config is shipped as .yaml.tmpl to avoid pre-commit picking
    # up the toolkit's own template repo as a config. Renamed at install time.
    precommit_src = TEMPLATES / 'pre-commit-config.yaml.tmpl'
    if precommit_src.exists():
        plan.append((precommit_src, target / '.pre-commit-config.yaml',
                     'TEMPLATE' if _looks_templated(precommit_src) else 'COPY'))

    # 5. .claude/ — Claude Code project-scoped settings + hooks
    claude_src = TEMPLATES / 'claude'
    if claude_src.exists():
        for src in claude_src.rglob('*'):
            if not src.is_file():
                continue
            rel = src.relative_to(claude_src)
            if '__pycache__' in rel.parts or src.suffix == '.pyc':
                continue
            dst = target / '.claude' / rel
            is_template = src.suffix in ('.j2', '.tmpl') or _looks_templated(src)
            plan.append((src, dst, 'TEMPLATE' if is_template else 'COPY'))

    # 6. .agent-toolkit/ — per-project runtime files (invariants, decision log).
    # These are user-curated after install; preserve existing content on update.
    #
    # Framework-overlay picker (v0.13+): files named `<stem>.<framework>.json`
    # (e.g. `coverage_config.odoo.json`) ship as-overlays; the installer keeps
    # the one matching the preset's `stack.framework`, falls back to
    # `<stem>.generic.json` otherwise, and emits as `<stem>.json` in the
    # target. Drops sibling overlays for other frameworks. Lets the toolkit
    # core stay stack-agnostic while a single preset can supply Odoo (or
    # Django, etc.) defaults without renaming files post-install.
    runtime_src = TEMPLATES / 'agent_toolkit'
    preset_framework = (preset.get('stack') or {}).get('framework') or 'generic'
    overlay_stems = _discover_overlay_stems(runtime_src)
    if runtime_src.exists():
        for src in runtime_src.rglob('*'):
            if not src.is_file():
                continue
            rel = src.relative_to(runtime_src)
            overlay_match = _classify_overlay(rel.name, overlay_stems, preset_framework)
            if overlay_match == 'drop':
                continue
            if overlay_match is not None:
                # overlay_match is the rewritten target filename `<stem>.json`
                dst = target / '.agent-toolkit' / rel.parent / overlay_match
            else:
                dst = target / '.agent-toolkit' / rel
            if dst.exists():
                # Never overwrite a project's curated invariants/decisions.
                plan.append((src, dst, 'SKIP_EXISTS'))
                continue
            is_template = src.suffix in ('.j2', '.tmpl') or _looks_templated(src)
            plan.append((src, dst, 'TEMPLATE' if is_template else 'COPY'))

    # 7. .gitignore added later (via write_gitignore)
    return plan


def _discover_overlay_stems(runtime_src: Path) -> Dict[str, set]:
    """Scan `templates/agent_toolkit/` for `<stem>.<framework>.json` files.

    Returns `{stem: {framework, ...}}` so `_classify_overlay` can tell
    overlays from plain files. A stem is an "overlay" only when ≥2
    framework variants exist OR a `.generic.json` sibling is present —
    a lone `foo.odoo.json` with no sibling is treated as a plain file.
    """
    if not runtime_src.exists():
        return {}
    candidates: Dict[str, set] = {}
    for src in runtime_src.iterdir():
        if not src.is_file() or src.suffix != '.json':
            continue
        parts = src.stem.split('.')
        if len(parts) < 2:
            continue
        stem, framework = '.'.join(parts[:-1]), parts[-1]
        candidates.setdefault(stem, set()).add(framework)
    # An overlay set must include a `generic` variant — that's the marker
    # distinguishing real overlays from incidental dotted filenames like
    # `test_env.schema.json` / `test_env.example.json`.
    return {s: fws for s, fws in candidates.items() if 'generic' in fws}


def _classify_overlay(filename: str, overlay_stems: Dict[str, set],
                      preset_framework: str):
    """Decide what to do with `filename` in the agent_toolkit copy loop.

    - Not an overlay → return `None` (caller uses original path).
    - Overlay matches `preset_framework` or is `.generic.json` fallback →
      return the rewritten target name `<stem>.json`.
    - Overlay for a different framework → return `'drop'`.
    """
    if not filename.endswith('.json'):
        return None
    parts = filename[:-len('.json')].split('.')
    if len(parts) < 2:
        return None
    stem, framework = '.'.join(parts[:-1]), parts[-1]
    if stem not in overlay_stems:
        return None
    variants = overlay_stems[stem]
    if framework == preset_framework and framework in variants:
        return f'{stem}.json'
    # Preset has no dedicated variant → fall back to generic.
    if preset_framework not in variants and framework == 'generic':
        return f'{stem}.json'
    return 'drop'


def _looks_templated(path: Path) -> bool:
    """Heuristic — file contains {{...}} placeholders.

    H2 fix: scan the FULL file, not just first 8KB — a placeholder past
    the 8KB mark was silently treated as COPY and shipped unrendered.
    Markdown templates routinely run >8KB.
    """
    try:
        return '{{' in path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return False


def _content_will_change(src: Path, dst: Path, mode: str, ctx: Dict[str, Any]) -> bool:
    """Compare what would-be-written content to what already exists.

    Skips unchanged files in dry-run reports and skips backup of files
    whose content is identical to the template-rendered output.
    """
    if not dst.exists() or mode == 'SKIP_EXISTS':
        return mode != 'SKIP_EXISTS'
    try:
        if mode == 'COPY':
            new_bytes = src.read_bytes()
            return dst.read_bytes() != new_bytes
        # TEMPLATE
        new_text = render_text(src.read_text(encoding='utf-8'), ctx)
        old_text = dst.read_text(encoding='utf-8', errors='replace')
        return old_text != new_text
    except Exception:
        # Treat unreadable destination as "would change" so we don't
        # silently skip it.
        return True


def _print_diff(src: Path, dst: Path, mode: str, ctx: Dict[str, Any],
                max_lines: int = 40):
    """Emit a unified diff between dst (old) and rendered src (new).

    Truncates at max_lines so a single large file doesn't drown the output.
    Used by `update --diff` to preview changes before --apply.
    """
    import difflib
    try:
        if mode == 'COPY':
            new_text = src.read_text(encoding='utf-8', errors='replace')
        else:
            new_text = render_text(src.read_text(encoding='utf-8'), ctx)
        old_text = dst.read_text(encoding='utf-8', errors='replace')
    except Exception as exc:
        info(f'    (diff unavailable: {exc})')
        return
    diff = list(difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile='current/' + dst.name,
        tofile='new/' + dst.name,
        n=2,
    ))
    if not diff:
        return
    for line in diff[:max_lines]:
        sys.stdout.write('    ' + line if not line.endswith('\n')
                         else '    ' + line)
    if len(diff) > max_lines:
        info(f'    ... ({len(diff) - max_lines} more diff lines truncated)')


def _parse_frontmatter(text: str) -> Dict[str, str]:
    """Extract top-level scalar key/values from `--- ... ---` YAML frontmatter.

    Ignores nested blocks (`metadata:` etc.) and lines starting with whitespace
    or `#`. Returns empty dict if no frontmatter present.
    """
    if not text.startswith('---'):
        return {}
    end_idx = text.find('\n---', 4)
    if end_idx == -1:
        return {}
    block = text[4:end_idx]
    out: Dict[str, str] = {}
    for line in block.splitlines():
        if not line or line[0] in (' ', '\t', '#'):
            continue
        if ':' in line:
            k, _, v = line.partition(':')
            k = k.strip()
            v = v.strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            elif v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
            if k and v:
                out[k] = v
    return out


def regenerate_memory_index(target_mem: Path):
    """Append entries for memory files missing from MEMORY.md.

    Scans target_mem for *.md files, parses frontmatter, and adds one
    `- [Title](file.md) — description` line per file not yet indexed.
    Preserves human-curated entries (titles) already in the file.
    """
    index_path = target_mem / 'MEMORY.md'
    existing = index_path.read_text(encoding='utf-8') if index_path.exists() else ''

    indexed = set()
    for line in existing.splitlines():
        m = re.search(r'\(([^)]+\.md)\)', line)
        if m:
            indexed.add(m.group(1))

    added = []
    for md in sorted(target_mem.glob('*.md')):
        if md.name == 'MEMORY.md' or md.name in indexed:
            continue
        try:
            fm = _parse_frontmatter(md.read_text(encoding='utf-8'))
        except Exception:
            continue
        desc = fm.get('description', '').strip()
        if not desc:
            continue
        title_base = md.stem.replace('_', ' ').replace('-', ' ')
        title = title_base[:1].upper() + title_base[1:]
        added.append(f'- [{title}]({md.name}) — {desc}')

    if added:
        sep = '\n' if existing.endswith('\n') or not existing else '\n'
        new_text = (existing.rstrip() + '\n' if existing else '') + '\n'.join(added) + '\n'
        index_path.write_text(new_text, encoding='utf-8')
        info(f'  added {len(added)} entries to MEMORY.md')


def seed_memory(preset, ctx, target, force):
    target_mem = encode_claude_project_path(target)
    target_mem.mkdir(parents=True, exist_ok=True)
    src_dirs = [TEMPLATES / 'memory' / '_common']
    for stack in preset.get('memory_packs', []):
        d = TEMPLATES / 'memory' / stack
        if d.exists():
            src_dirs.append(d)
    n = 0
    for src_dir in src_dirs:
        for src in src_dir.glob('*.md'):
            dst = target_mem / src.name
            if dst.exists() and not force:
                continue
            text = render_text(src.read_text(encoding='utf-8'), ctx)
            dst.write_text(text, encoding='utf-8')
            n += 1
    info(f'  seeded {n} memory files into {target_mem}')
    # H1 fix: regenerate MEMORY.md so the index lists every *.md actually
    # present in the dir, not just whatever the template ships.
    regenerate_memory_index(target_mem)


def _build_mcp_servers_payload(ctx, target):
    """Build the shared mcpServers payload reused by every agent harness.

    Two sources merged:
      1. `ctx['MCP_SERVERS']` — list of Python MCP names with sibling
         `start_<name>_mcp.py` scripts (codebase, postgres, ...).
      2. `ctx['EXTERNAL_MCP_SERVERS']` — dict of external servers shipped
         verbatim (command + args + optional env). Used for npm packages
         like `@playwright/mcp` or any non-Python MCP. Stored generic; the
         installer does NOT hardcode any specific server name.
    """
    py = ctx['PYTHON_BIN'] or 'python'
    codex = (target / '.codex').as_posix()
    servers = {}
    # Python MCP servers (have sibling start scripts)
    for s in ctx.get('MCP_SERVERS') or []:
        starter = f'{codex}/start_{s}_mcp.py'
        if (target / '.codex' / f'start_{s}_mcp.py').exists():
            servers[s] = {'command': py, 'args': [starter]}
    # External MCP servers (npm / binary — config shipped verbatim from preset)
    external = ctx.get('EXTERNAL_MCP_SERVERS') or {}
    for name, spec in external.items():
        if not isinstance(spec, dict):
            continue
        entry = {}
        if 'command' in spec:
            entry['command'] = spec['command']
        if 'args' in spec:
            entry['args'] = list(spec.get('args') or [])
        if 'env' in spec:
            entry['env'] = dict(spec.get('env') or {})
        if entry:
            servers[name] = entry
    return servers


def write_mcp_configs(ctx, target, force):
    """Write MCP discovery files for every supported agent harness.

    Cursor and Claude Code use different file paths for the *same* MCP
    server set:
      - Cursor: `.cursor/mcp.json` (Cursor reads this directly)
      - Claude Code: `.mcp.json` at workspace root (project-scoped MCP
        config; loaded automatically when Claude Code opens the workspace)

    Codex CLI reuses `.cursor/mcp.json` via its own config — no extra file
    needed there. Both files contain only command/args (no secrets);
    credentials live in `.codex/mcp.local.env` which the server scripts
    load at startup.
    """
    servers = _build_mcp_servers_payload(ctx, target)
    payload_text = json.dumps({'mcpServers': servers}, indent=2) + '\n'

    targets = [
        ('cursor', target / '.cursor' / 'mcp.json'),
        ('claude-code', target / '.mcp.json'),
    ]
    for label, path in targets:
        if path.exists() and not force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload_text, encoding='utf-8')
        ok(f'  wrote {path.relative_to(target)} for {label} ({len(servers)} servers)')


def write_gitignore(target):
    gi = target / '.gitignore'
    snippets = [
        '.codex/mcp.local.env',
        '.cursor/mcp.json',
        '.mcp.json',
        '.claude/settings.local.json',
        '__pycache__/',
        '*.pyc',
    ]
    if gi.exists():
        existing = gi.read_text(encoding='utf-8')
        added = []
        for snip in snippets:
            if snip not in existing:
                added.append(snip)
        if added:
            gi.write_text(existing.rstrip() + '\n# agent-toolkit\n'
                          + '\n'.join(added) + '\n', encoding='utf-8')
            info(f'  appended {len(added)} entries to .gitignore')
    else:
        gi.write_text('# agent-toolkit\n' + '\n'.join(snippets) + '\n',
                      encoding='utf-8')
        info('  created .gitignore')


# -----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--version', action='version',
                    version=f'agent-toolkit {__version__}')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('init', help='install agent infra into a project')
    sp.add_argument('target', help='target workspace path')
    sp.add_argument('--preset', help='preset name (run `list-presets`)')
    sp.add_argument('--python', help='Python venv binary')
    sp.add_argument('--psql', help='psql binary path')
    sp.add_argument('--project-name', help='friendly project name')
    sp.add_argument('--yes', '-y', action='store_true')
    sp.add_argument('--force', action='store_true')
    sp.add_argument('--dry-run', action='store_true')
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser('update', help='refresh templates in an installed project')
    sp.add_argument('target')
    sp.add_argument('--preset', help='override preset (defaults to config file)')
    sp.add_argument('--python', help='override Python venv binary')
    sp.add_argument('--psql', help='override psql binary path')
    sp.add_argument('--project-name', help='override project name')
    sp.add_argument('--apply', action='store_true',
                    help='Actually write changes. Without this flag, update '
                         'runs as a dry-run preview (default for safety).')
    sp.add_argument('--no-backup', action='store_true',
                    help='Skip creating *.bak.<ts> copies before overwriting '
                         '(only meaningful with --apply).')
    sp.add_argument('--diff', action='store_true', default=True,
                    help='Show unified diff for modified files in dry-run '
                         '(default: on).')
    sp.add_argument('--no-diff', dest='diff', action='store_false',
                    help='Suppress diff output in dry-run.')
    sp.add_argument('--force', action='store_true',
                    help='Overwrite SKIP_EXISTS files (canonical_decisions, '
                         '.agent-toolkit/invariants.json). Default OFF.')
    sp.add_argument('--force-dirty', action='store_true',
                    help='Apply even when git working tree is dirty. '
                         'Default OFF — refuse to overwrite uncommitted changes.')
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser('list-presets', help='list available presets')
    sp.set_defaults(func=cmd_list_presets)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
