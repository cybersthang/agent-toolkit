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

    if not args.preset:
        presets = sorted({p.stem for p in PRESETS_DIR.glob('*.json')}
                         | {p.stem for p in PRESETS_DIR.glob('*.yaml')})
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

    py_bin = args.python or detect_python(target)
    psql_bin = args.psql or detect_psql()

    if not args.yes:
        py_bin = input(f'Python binary [{py_bin or "?"}]: ').strip() or py_bin
        psql_bin = input(f'psql binary [{psql_bin or "?"}]: ').strip() or psql_bin

    project_name = args.project_name or target.name

    addon_roots = preset.get('addon_roots', []) or []
    mcp_servers = preset.get('mcp_servers', []) or []
    ctx: Dict[str, Any] = {
        'WORKSPACE_ROOT': str(target).replace('\\', '/'),
        'WORKSPACE_NAME': project_name,
        'PROJECT_NAME': project_name,
        'PYTHON_BIN': str(py_bin or '').replace('\\', '/'),
        'PSQL_BIN': str(psql_bin or '').replace('\\', '/'),
        'STACK_LANGUAGE': preset.get('stack', {}).get('language', 'python'),
        'STACK_LANGUAGE_VERSION': preset.get('stack', {}).get('language_version', '3'),
        'STACK_FRAMEWORK': preset.get('stack', {}).get('framework', ''),
        'STACK_FRAMEWORK_VERSION': preset.get('stack', {}).get('framework_version', ''),
        'STACK_LABEL': preset.get('stack_label')
            or '%s %s' % (
                preset.get('stack', {}).get('framework', '').title(),
                preset.get('stack', {}).get('framework_version', '')),
        'ADDON_ROOTS': addon_roots,
        'ADDON_ROOTS_CSV': ', '.join(addon_roots),
        'DEFAULT_DB': preset.get('db', {}).get('default_db', ''),
        'DEFAULT_PG_PORT': str(preset.get('db', {}).get('default_port', 5432)),
        'MCP_SERVERS': mcp_servers,
        'MCP_SERVERS_CSV': ', '.join(mcp_servers),
        'PRESET_NAME': args.preset,
        'RESPONSE_LANGUAGE': preset.get('response_language', 'English'),
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
    write_cursor_mcp(ctx, target, force=args.force)
    write_gitignore(target)

    print()
    ok('install complete.')
    info('Next:')
    info(f'  1. Edit {target}/.codex/mcp.local.env — fill PASSWORD + JIRA creds')
    info('  2. Restart Cursor / Claude Code')
    info(f'  3. Verify: python {target}/.codex/tests/test_mcp_wrappers.py')


def cmd_update(args):
    """Refresh templates/scripts but preserve user's mcp.local.env."""
    target = Path(args.target).resolve()
    info_path = target / '.agent-toolkit-install.json'
    if not info_path.exists():
        sys.exit(f'No install record at {info_path}; use `init` instead')
    state = json.loads(info_path.read_text(encoding='utf-8'))
    args.preset = state['preset']
    args.python = state.get('python_bin')
    args.psql = state.get('psql_bin')
    args.project_name = state.get('project_name')
    args.yes = True
    args.dry_run = False
    args.force = True
    info(f'Updating using saved preset: {args.preset}')
    cmd_init(args)


# -----------------------------------------------------------------------
def build_plan(preset, ctx, target):
    """Decide for each toolkit file: copy raw, template, or skip."""
    plan: List = []
    rules_set = preset.get('rules', ['_common'])
    skills_set = preset.get('skills', ['_common'])
    mcp_set = set(preset.get('mcp_servers', []))

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

    # 5. .gitignore added later (via write_gitignore)
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


def write_cursor_mcp(ctx, target, force):
    cursor_mcp = target / '.cursor' / 'mcp.json'
    if cursor_mcp.exists() and not force:
        return
    py = ctx['PYTHON_BIN'] or 'python'
    codex = (target / '.codex').as_posix()
    servers = {}
    for s in ctx['MCP_SERVERS']:
        starter = f'{codex}/start_{s}_mcp.py'
        if (target / '.codex' / f'start_{s}_mcp.py').exists():
            servers[s] = {'command': py, 'args': [starter]}
    payload = {'mcpServers': servers}
    cursor_mcp.parent.mkdir(parents=True, exist_ok=True)
    cursor_mcp.write_text(
        json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    ok(f'  wrote {cursor_mcp.relative_to(target)} ({len(servers)} servers)')


def write_gitignore(target):
    gi = target / '.gitignore'
    snippets = [
        '.codex/mcp.local.env',
        '.cursor/mcp.json',
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
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser('list-presets', help='list available presets')
    sp.set_defaults(func=cmd_list_presets)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
