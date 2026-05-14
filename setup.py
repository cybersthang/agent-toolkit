"""agent-toolkit — install Claude Code / Cursor / Codex agent infrastructure
into a target workspace, configured for a specific stack (Odoo 12, Odoo 17,
Django, plain Python ...).

Run from the toolkit directory:

    # Interactive: pick preset + ask for paths
    python setup.py init /path/to/project

    # Non-interactive: pass everything on CLI
    python setup.py init /path/to/project \
        --preset odoo-12 \
        --python /path/to/venv/bin/python \
        --psql /usr/bin/psql

    # Refresh from latest toolkit (preserves user's mcp.local.env)
    python setup.py update /path/to/project

    # Show what would be written without touching disk
    python setup.py init /path/to/project --preset odoo-17 --dry-run

The toolkit is stack-agnostic: presets/<name>.yaml drives WHICH templates
get installed and HOW placeholders are filled. Adding a new stack means
adding a preset + (optionally) a new rules/<stack>/ folder.
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

TOOLKIT_ROOT = Path(__file__).resolve().parent
TEMPLATES = TOOLKIT_ROOT / 'templates'
PRESETS_DIR = TOOLKIT_ROOT / 'presets'
LIB_DIR = TOOLKIT_ROOT / 'lib'
sys.path.insert(0, str(LIB_DIR))

from installer import (  # noqa: E402
    load_preset, render_text, render_into,
    detect_python, detect_psql, encode_claude_project_path,
    confirm, info, warn, ok,
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
        },
        'addon_roots': list(ctx.get('ADDON_ROOTS', []) or []),
        'mcp_servers': list(ctx.get('MCP_SERVERS', []) or []),
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

    preset_path = PRESETS_DIR / f'{args.preset}.json'
    if not preset_path.exists():
        preset_path = PRESETS_DIR / f'{args.preset}.yaml'
    if not preset_path.exists():
        sys.exit(f'preset not found: {preset_path}')

    preset = load_preset(preset_path)
    info(f'Using preset: {args.preset}')
    info(f'  description: {preset.get("description", "")}')
    info(f'  stack: {preset.get("stack", {})}')
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
    db_cfg = project_cfg.get('db') or preset.get('db', {}) or {}
    response_language = (
        project_cfg.get('response_language')
        or preset.get('response_language', 'English')
    )
    stack_cfg = project_cfg.get('stack') or {}
    preset_stack = preset.get('stack', {}) or {}

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
        'DEFAULT_DB': db_cfg.get('default_db', ''),
        'DEFAULT_PG_PORT': str(db_cfg.get('default_port', 5432)),
        'MCP_SERVERS': mcp_servers,
        'MCP_SERVERS_CSV': ', '.join(mcp_servers),
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
        info('\n[dry-run] would write into: ' + str(target))
        plan = build_plan(preset, ctx, target)
        for src, dst, mode in plan:
            print(f'  [{mode}] {dst.relative_to(target)}')
        info('\n[dry-run] would also seed memory into:')
        info(f'  {encode_claude_project_path(target)}')
        return

    if not args.yes and not confirm(f'Install into {target}? [y/N]: '):
        sys.exit('aborted')

    plan = build_plan(preset, ctx, target)
    for src, dst, mode in plan:
        if mode == 'COPY':
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif mode == 'TEMPLATE':
            dst.parent.mkdir(parents=True, exist_ok=True)
            render_into(src, dst, ctx)
        elif mode == 'SKIP_EXISTS':
            continue
        ok(f'  {mode:<10} {dst.relative_to(target)}')

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
    args.dry_run = False
    args.force = True
    info(f'Updating using saved preset: {args.preset}')
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
    # Pick preset-specific canonical_decisions seed if it exists, else fall
    # back to the default. Variants live next to the default file as
    # `canonical_decisions.<preset>.json`.
    canonical_default = codex_src / 'canonical_decisions.json'
    canonical_preset = codex_src / f'canonical_decisions.{preset_name}.json'
    canonical_chosen = canonical_preset if canonical_preset.exists() else canonical_default
    for src in codex_src.rglob('*'):
        if not src.is_file():
            continue
        rel = src.relative_to(codex_src)
        rel_str = str(rel).replace('\\', '/')
        # Skip noise that's machine-local or project-specific
        if '__pycache__' in rel.parts or src.suffix == '.pyc':
            continue
        if rel.name.startswith('_') and src.suffix == '.py':
            # Toolkit ships no per-project ad-hoc probe scripts
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

    # 4. AGENTS.md + CLAUDE.md
    for top_template in ('AGENTS.md', 'CLAUDE.md'):
        src = TEMPLATES / top_template
        if src.exists():
            plan.append((src, target / top_template, 'TEMPLATE'))

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
    runtime_src = TEMPLATES / 'agent_toolkit'
    if runtime_src.exists():
        for src in runtime_src.rglob('*'):
            if not src.is_file():
                continue
            rel = src.relative_to(runtime_src)
            dst = target / '.agent-toolkit' / rel
            if dst.exists():
                # Never overwrite a project's curated invariants/decisions.
                plan.append((src, dst, 'SKIP_EXISTS'))
                continue
            is_template = src.suffix in ('.j2', '.tmpl') or _looks_templated(src)
            plan.append((src, dst, 'TEMPLATE' if is_template else 'COPY'))

    # 7. .gitignore added later (via write_gitignore)
    return plan


def _looks_templated(path: Path) -> bool:
    """Cheap heuristic — file contains {{...}} placeholders."""
    try:
        return '{{' in path.read_text(encoding='utf-8', errors='ignore')[:8192]
    except Exception:
        return False


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


def _build_mcp_servers_payload(ctx, target):
    """Build the shared `{servers, count}` payload reused by every agent harness."""
    py = ctx['PYTHON_BIN'] or 'python'
    codex = (target / '.codex').as_posix()
    servers = {}
    for s in ctx['MCP_SERVERS']:
        starter = f'{codex}/start_{s}_mcp.py'
        if (target / '.codex' / f'start_{s}_mcp.py').exists():
            servers[s] = {'command': py, 'args': [starter]}
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
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser('list-presets', help='list available presets')
    sp.set_defaults(func=cmd_list_presets)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
