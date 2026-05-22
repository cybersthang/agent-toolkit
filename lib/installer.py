# SPDX-License-Identifier: MIT
"""Shared install helpers — kept dependency-free (stdlib only)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional


# Toolkit version. Bump when schema_version of agent-toolkit.config.json
# changes or when CLI flags break backward compatibility.
__version__ = '0.12.3'


# ----------------------------------------------------- preset loader ---
def load_preset(path: Path) -> dict:
    """Load a preset from JSON.

    JSON only; if you want YAML, install pyyaml and import it yourself.
    The toolkit dropped its hand-rolled YAML parser (H3) — it was 50 lines
    of dead code that didn't support flow style, anchors, or multi-line
    strings, and JSON covers every shipped preset.
    """
    if path.suffix.lower() not in ('.json',):
        raise ValueError(
            f'unsupported preset format: {path.suffix}. '
            f'Use .json (drop pyyaml in if you need YAML).'
        )
    return json.loads(path.read_text(encoding='utf-8'))


# --- Preset schema (lightweight hand-rolled — no jsonschema dep) ---
# Tier 3 fix: validate preset JSON shape so typos like `addon_root` (singular)
# fail at load-time with a clear message, instead of silently using the
# preset default (empty list) and breaking install downstream.
_PRESET_REQUIRED = {'description', 'stack'}
_PRESET_KNOWN = {
    'description', 'stack', 'stack_label', 'response_language',
    'addon_roots', 'mcp_servers', 'db', 'rules', 'skills', 'memory_packs',
    'env_prefix',
    # External (non-Python) MCP servers — npm packages, binaries, etc.
    # Stored as dict {server_name: {command, args, env?}}. Merged with the
    # Python `mcp_servers` list in `_build_mcp_servers_payload`. Used for
    # off-the-shelf MCP servers (e.g. `@playwright/mcp` via npx).
    'external_mcp_servers',
    # Inheritance + additive overrides (Tier 3 extensibility)
    'extends', 'addon_roots_append', 'mcp_servers_append',
    'mcp_servers_remove', 'rules_append', 'skills_append',
    'memory_packs_append', 'external_mcp_servers_append',
}


def validate_preset(data: dict, name: str = '<preset>') -> list:
    """Return a list of human-readable validation errors (empty list = OK).

    Doesn't raise; caller decides whether to fail-hard or warn.
    """
    errors = []
    for req in _PRESET_REQUIRED:
        if req not in data:
            errors.append(f'{name}: missing required field `{req}`')
    for key in data.keys():
        if key.startswith('_'):
            continue  # private/meta fields
        if key not in _PRESET_KNOWN:
            # Likely typo. Suggest closest match.
            suggestion = _closest_match(key, _PRESET_KNOWN)
            hint = f' (did you mean `{suggestion}`?)' if suggestion else ''
            errors.append(f'{name}: unknown field `{key}`{hint}')
    # Type sanity for list fields.
    for list_key in ('addon_roots', 'mcp_servers', 'rules', 'skills',
                     'memory_packs', 'addon_roots_append',
                     'mcp_servers_append', 'mcp_servers_remove',
                     'rules_append', 'skills_append', 'memory_packs_append'):
        if list_key in data and not isinstance(data[list_key], list):
            errors.append(
                f'{name}: `{list_key}` must be a list, got '
                f'{type(data[list_key]).__name__}'
            )
    return errors


def _closest_match(needle: str, haystack) -> Optional[str]:
    """Levenshtein-cheap closest-string lookup for 'did you mean' hints."""
    import difflib
    matches = difflib.get_close_matches(needle, list(haystack), n=1, cutoff=0.6)
    return matches[0] if matches else None


def resolve_preset(name: str, presets_dir: Path,
                   _seen: Optional[set] = None) -> dict:
    """Load a preset and recursively merge any `extends:` parent chain.

    Additive override fields (`*_append`, `mcp_servers_remove`) let a child
    preset tweak its parent without redeclaring the full list. Plain fields
    overwrite the parent. Inheritance cycles are detected and rejected.
    """
    _seen = _seen or set()
    if name in _seen:
        raise ValueError(f'preset inheritance cycle through `{name}`')
    _seen.add(name)

    path = presets_dir / f'{name}.json'
    if not path.exists():
        suggestion = _closest_match(name, [p.stem for p in presets_dir.glob('*.json')])
        hint = f' (did you mean `{suggestion}`?)' if suggestion else ''
        raise FileNotFoundError(f'preset not found: {name}{hint}')

    data = load_preset(path)
    errors = validate_preset(data, name=name)
    if errors:
        msg = 'preset validation failed:\n  ' + '\n  '.join(errors)
        raise ValueError(msg)

    parent_name = data.get('extends')
    if not parent_name:
        return data

    parent = resolve_preset(parent_name, presets_dir, _seen)
    # Start from parent, then overlay child.
    merged: Dict[str, Any] = dict(parent)
    for k, v in data.items():
        if k == 'extends':
            continue
        if k.endswith('_append'):
            # `addon_roots_append: [...]` extends parent's `addon_roots`.
            # For dict fields (e.g. `external_mcp_servers`), `_append` is a
            # shallow merge (child entries overlay parent entries).
            base_key = k[:-len('_append')]
            base_val = merged.get(base_key)
            if isinstance(base_val, dict) and isinstance(v, dict):
                merged[base_key] = {**base_val, **v}
            else:
                base = list(base_val or [])
                base.extend(v)
                merged[base_key] = base
        elif k == 'mcp_servers_remove':
            base = [m for m in (merged.get('mcp_servers') or []) if m not in v]
            merged['mcp_servers'] = base
        elif isinstance(v, dict) and isinstance(merged.get(k), dict):
            # Shallow merge for dicts (e.g. `db`, `stack`).
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


# --- Git-aware safety (Tier 3) ---
def git_dirty_status(target: Path) -> Optional[str]:
    """Return a short status summary if target is a dirty git repo, else None.

    Returns None when:
    - target is not a git repo
    - target is clean
    - git is not installed
    """
    import subprocess
    try:
        result = subprocess.run(
            ['git', '-C', str(target), 'status', '--porcelain'],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None  # not a git repo, or other error
    out = result.stdout.strip()
    if not out:
        return None  # clean
    lines = out.splitlines()
    return f'{len(lines)} uncommitted change(s)'


# ----------------------------------------------------- templating ---
_PLACEHOLDER_RE = re.compile(r'\{\{\s*([A-Z_][A-Z0-9_]*)\s*\}\}')


def render_text(text: str, ctx: Dict[str, Any]) -> str:
    """Lightweight {{ KEY }} substitution.

    Lists become newline-joined strings prefixed with `- ` so they can be
    dropped into Markdown bullets without further work.
    """
    def _sub(m):
        key = m.group(1)
        value = ctx.get(key, '')
        if isinstance(value, list):
            return '\n'.join('- %s' % item for item in value)
        return str(value)
    return _PLACEHOLDER_RE.sub(_sub, text)


def render_into(src: Path, dst: Path, ctx: Dict[str, Any]):
    text = src.read_text(encoding='utf-8')
    dst.write_text(render_text(text, ctx), encoding='utf-8')


# ----------------------------------------------------- detect ---
def detect_python(workspace: Path) -> Optional[str]:
    candidates = [
        workspace / '..' / 'venv' / 'Scripts' / 'python.exe',
        workspace / '..' / 'venv' / 'bin' / 'python',
        workspace / 'venv' / 'Scripts' / 'python.exe',
        workspace / 'venv' / 'bin' / 'python',
        workspace / '.venv' / 'Scripts' / 'python.exe',
        workspace / '.venv' / 'bin' / 'python',
    ]
    for c in candidates:
        c = c.resolve()
        if c.exists():
            return str(c)
    return None


def psql_candidates(os_name: Optional[str] = None) -> list:
    """Return candidate `psql` binary paths for the given OS family.

    Split out from `detect_psql` so tests can exercise both branches
    without monkey-patching `os.name` (which corrupts the pathlib
    `_flavour` cache on Py3.8 + Windows and breaks pytest-cov teardown).

    `os_name` defaults to the live `os.name`. Pass `"nt"` or `"posix"`
    explicitly in tests to force a branch.
    """
    name = os_name if os_name is not None else os.name
    if name == 'nt':
        return [
            r'C:\Program Files\pgAdmin 4\runtime\psql.exe',
            r'C:\Program Files\PostgreSQL\17\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\16\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\15\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\14\bin\psql.exe',
        ]
    return ['/usr/bin/psql', '/usr/local/bin/psql', '/opt/homebrew/bin/psql']


def detect_psql() -> Optional[str]:
    for c in psql_candidates():
        if Path(c).exists():
            return c
    return None


def encode_claude_project_path(workspace: Path) -> Path:
    """Return ~/.claude/projects/<encoded>/memory/ for a given workspace.

    Encoding rule observed from live Claude Code installs (Windows + POSIX):
    - lowercase the drive letter on Windows (`C:` → `c:`)
    - replace `:`, `\\`, `/`, `.`, `_` with `-`
    - keep consecutive dashes (drive letter `C:` → `c--`)
    """
    s = str(workspace.resolve())
    if len(s) >= 2 and s[1] == ':':
        s = s[0].lower() + s[1:]
    for ch in (':', '\\', '/', '.', '_'):
        s = s.replace(ch, '-')
    return Path.home() / '.claude' / 'projects' / s / 'memory'


# ----------------------------------------------------- IO ---
def info(msg: str):
    print(f'  {msg}')


def ok(msg: str):
    print(f'  ✓ {msg}')


def warn(msg: str):
    print(f'  ! {msg}', file=sys.stderr)


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower().startswith('y')
    except EOFError:
        return False
