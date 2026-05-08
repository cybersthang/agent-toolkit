"""Shared install helpers — kept dependency-free (stdlib only)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional


# ----------------------------------------------------- preset loader ---
def load_preset(path: Path) -> dict:
    """Load a preset.

    Accepts JSON (.json) or YAML (.yaml/.yml). YAML support requires
    PyYAML; if not installed, JSON is the only option (toolkit ships
    JSON presets to stay dependency-free).
    """
    text = path.read_text(encoding='utf-8')
    if path.suffix.lower() == '.json':
        import json
        return json.loads(text)
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        # Fall back to the tiny stdlib parser
        return _parse_yaml(text)


def _parse_yaml(text: str) -> dict:
    """Tiny stdlib YAML reader.

    Supports: top-level + nested key/value, lists with `- item`,
    string/int/float/bool coercion. Comments (`#`) and blank lines
    skipped. Indentation must be consistent within a block.

    Not supported: flow style (`[a,b]`), anchors, multi-line strings.
    """
    root: dict = {}
    # Each stack entry: (indent_of_children, container, parent_key_for_list_items)
    stack = [(-1, root, None)]
    pending_key = None  # last key whose value might be a list/dict on next line
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()

        # Pop stack until top frame's children-indent < current indent
        while stack and stack[-1][0] >= indent and stack[-1][2] is None:
            stack.pop()
        # For list frames, pop only when indent is shallower
        while stack and stack[-1][2] is not None and stack[-1][0] > indent:
            stack.pop()

        _, container, list_parent_key = stack[-1]

        if line.startswith('- '):
            value = _coerce(line[2:].strip())
            # We expect container == parent dict, list_parent_key == key name
            if list_parent_key is None:
                # First list item under pending_key in container
                key = pending_key
                if key is None:
                    continue
                if not isinstance(container.get(key), list):
                    container[key] = []
                container[key].append(value)
                stack.append((indent, container, key))
            else:
                container[list_parent_key].append(value)
            continue

        if ':' in line:
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            # If we were inside a list frame, pop it (current line is a key, not list)
            while stack and stack[-1][2] is not None:
                stack.pop()
            _, container, _ = stack[-1]
            if val == '':
                # nested dict OR list — decide on next line
                container[key] = {}
                pending_key = key
                # Push a frame whose children belong to container[key]
                # but only if next line is a dict (key:val); if it's `- item`,
                # we'll convert container[key] to [] in the list branch above.
                stack.append((indent, container, None))
                # Walk back: when we read a dict child (key: val) at deeper
                # indent, we need a frame pointing into container[key].
                # Achieve this by also pushing a child-dict frame.
                stack.append((indent, container[key], None))
            else:
                container[key] = _coerce(val)
                pending_key = key
    return root


def _coerce(s: str):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s.lower() in ('true', 'false'):
        return s.lower() == 'true'
    if re.match(r'^-?\d+$', s):
        return int(s)
    if re.match(r'^-?\d+\.\d+$', s):
        return float(s)
    return s


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


def detect_psql() -> Optional[str]:
    if os.name == 'nt':
        candidates = [
            r'C:\Program Files\pgAdmin 4\runtime\psql.exe',
            r'C:\Program Files\PostgreSQL\17\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\16\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\15\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\14\bin\psql.exe',
        ]
    else:
        candidates = ['/usr/bin/psql', '/usr/local/bin/psql', '/opt/homebrew/bin/psql']
    for c in candidates:
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
