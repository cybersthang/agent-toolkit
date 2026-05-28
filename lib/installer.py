# SPDX-License-Identifier: MIT
"""Shared install helpers — kept dependency-free (stdlib only)."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Toolkit version. Bump when schema_version of agent-toolkit.config.json
# changes or when CLI flags break backward compatibility.
__version__ = '0.26.0'


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
    # Per-Odoo-version invariants overlay (R4). Array of invariant entries
    # (same schema as .agent-toolkit/invariants.json) carrying version-specific
    # API-diff rules. Recognised here so presets validate; NOT yet consumed by
    # the installer. Wave-C follow-up: `setup.py --merge-invariants` should
    # merge this onto the project's invariants.json at init time.
    'invariants_overlay',
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


# --- P2.7: jsonschema-style preset validation (stdlib only) ---------------
# v0.23 P2.7
# `validate_preset` (above) only checks field NAMES (typo guard) + a thin
# list-type sanity pass. `validate_preset_schema` is the stricter,
# jsonschema-equivalent check: REQUIRED fields present, every known field has
# the right TYPE, and each `invariants_overlay` entry matches the invariant
# schema (id/description/applies_to/rules/severity). Hand-rolled so the
# toolkit stays stdlib-only (jsonschema is NOT a dep — see requirements-dev.txt
# which pins only pytest/pytest-cov/ruff; the runtime ships zero install-time
# Python deps). Returns a list of human-readable errors (empty = OK); never
# raises so the caller picks fail-hard vs warn.

# Expected JSON type(s) per known preset field. `list`/`dict`/`str`/`int` map
# to Python types. A tuple means "any of these types is acceptable".
_PRESET_FIELD_TYPES: Dict[str, Any] = {
    'description': str,
    'stack': dict,
    'stack_label': str,
    'response_language': str,
    'addon_roots': list,
    'mcp_servers': list,
    'db': dict,
    'rules': list,
    'skills': list,
    'memory_packs': list,
    'env_prefix': str,
    'external_mcp_servers': dict,
    'extends': str,
    'addon_roots_append': list,
    'mcp_servers_append': list,
    'mcp_servers_remove': list,
    'rules_append': list,
    'skills_append': list,
    'memory_packs_append': list,
    'external_mcp_servers_append': dict,
    'invariants_overlay': list,
}

# Invariant-entry schema (mirrors templates/agent_toolkit/invariants.json
# `_schema`). Used to validate each `invariants_overlay` entry.
_INVARIANT_REQUIRED = ('id', 'description', 'applies_to', 'rules', 'severity')
_INVARIANT_SEVERITIES = ('blocker', 'warn')


def _type_label(t: Any) -> str:
    if isinstance(t, tuple):
        return ' or '.join(x.__name__ for x in t)
    return t.__name__


def validate_invariant_entry(entry: Any, where: str) -> List[str]:
    """Validate a single invariant entry against the shipped schema.

    `where` is a human-readable locator (e.g. `odoo-13.invariants_overlay[0]`)
    prefixed onto every error. Returns a list of errors (empty = OK).
    """
    errors: List[str] = []
    if not isinstance(entry, dict):
        return [f'{where}: must be an object, got {type(entry).__name__}']
    for req in _INVARIANT_REQUIRED:
        if req not in entry:
            errors.append(f'{where}: missing required field `{req}`')
    # Type checks (only for fields that are present).
    if 'id' in entry and not isinstance(entry['id'], str):
        errors.append(f'{where}: `id` must be a string')
    if 'description' in entry and not isinstance(entry['description'], str):
        errors.append(f'{where}: `description` must be a string')
    if 'applies_to' in entry and not isinstance(entry['applies_to'], list):
        errors.append(f'{where}: `applies_to` must be a list')
    if 'rules' in entry and not isinstance(entry['rules'], dict):
        errors.append(f'{where}: `rules` must be an object')
    if 'severity' in entry:
        sev = entry['severity']
        if sev not in _INVARIANT_SEVERITIES:
            errors.append(
                f'{where}: `severity` must be one of '
                f'{_INVARIANT_SEVERITIES}, got {sev!r}'
            )
    return errors


def validate_preset_schema(data: Any, name: str = '<preset>') -> List[str]:
    """Full jsonschema-style validation of a preset dict (P2.7).

    Stricter superset of `validate_preset`: in addition to the unknown-field
    typo guard, this enforces required fields, per-field TYPE correctness, and
    recurses into every `invariants_overlay` entry. Returns a list of
    human-readable errors (empty list = OK); does not raise.
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        return [f'{name}: preset must be a JSON object, got '
                f'{type(data).__name__}']

    # 1. Required top-level fields.
    for req in _PRESET_REQUIRED:
        if req not in data:
            errors.append(f'{name}: missing required field `{req}`')

    # 2. Unknown-field typo guard (reuse the allow-list).
    for key in data.keys():
        if key.startswith('_'):
            continue  # private/meta fields
        if key not in _PRESET_KNOWN:
            suggestion = _closest_match(key, _PRESET_KNOWN)
            hint = f' (did you mean `{suggestion}`?)' if suggestion else ''
            errors.append(f'{name}: unknown field `{key}`{hint}')

    # 3. Per-field type correctness.
    for key, expected in _PRESET_FIELD_TYPES.items():
        if key in data and not isinstance(data[key], expected):
            errors.append(
                f'{name}: `{key}` must be {_type_label(expected)}, got '
                f'{type(data[key]).__name__}'
            )

    # 4. Recurse into invariants_overlay entries (only if it's a list — a
    #    type error was already recorded above otherwise).
    overlay = data.get('invariants_overlay')
    if isinstance(overlay, list):
        seen_ids: set = set()
        for i, entry in enumerate(overlay):
            where = f'{name}.invariants_overlay[{i}]'
            errors.extend(validate_invariant_entry(entry, where))
            if isinstance(entry, dict) and isinstance(entry.get('id'), str):
                if entry['id'] in seen_ids:
                    errors.append(
                        f'{where}: duplicate invariant id `{entry["id"]}` '
                        f'within overlay'
                    )
                seen_ids.add(entry['id'])
    return errors


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
    # v0.23 P2.7: use the stricter jsonschema-style validator (required
    # fields + per-field types + invariants_overlay entry schema). It is a
    # superset of the old name-only `validate_preset`, so the latter is no
    # longer called here (kept for backward-compat callers).
    errors = validate_preset_schema(data, name=name)
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
    out = (result.stdout or "").strip()
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


# ----------------------------------------------------- invariants merge ---
def _atomic_write_json(path: Path, data: Any) -> None:
    """Atomic JSON write via temp file + os.replace.

    Mirrors `templates/claude/hooks/_common.py:atomic_write_json` but kept
    here so the installer stays self-contained (the hooks file is shipped
    INTO target projects, not imported from this side). Worst case: a
    partial write leaves the original `path` untouched and the temp file
    behind for the OS to GC.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', delete=False,
            dir=str(path.parent), prefix=f'.{path.name}.', suffix='.tmp',
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.write('\n')
            tmp_path = tmp.name
        os.replace(tmp_path, str(path))
    except OSError:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def merge_invariants(
    project_data: Optional[Dict[str, Any]],
    template_data: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Merge template invariants into project data, dedup'd by `id`.

    Strategy:
    - Preserve project's metadata keys (`_doc`, `_schema`, `_workflow`,
      `version`, plus any other private/meta fields the project added).
    - For each invariant in `template_data['invariants']`, append to the
      project's `invariants` list UNLESS an entry with the same `id`
      already exists (project entry wins — never overwrite curated edits).
    - When `project_data` is None (file didn't exist), seed from template
      metadata and add all template invariants.

    Returns `(merged_dict, added_ids, skipped_ids)` so the caller can
    surface a human-readable diff.
    """
    tmpl_invs: List[Dict[str, Any]] = list(template_data.get('invariants') or [])

    if project_data is None:
        merged = dict(template_data)
        merged['invariants'] = list(tmpl_invs)
        return merged, [inv.get('id', '<no-id>') for inv in tmpl_invs], []

    merged = dict(project_data)
    existing_invs: List[Dict[str, Any]] = list(merged.get('invariants') or [])
    existing_ids = {inv.get('id') for inv in existing_invs if inv.get('id')}

    added: List[str] = []
    skipped: List[str] = []
    for inv in tmpl_invs:
        inv_id = inv.get('id')
        if not inv_id:
            # Defensive: a malformed template entry without `id` — skip
            # rather than risk shipping a phantom duplicate on next run.
            skipped.append('<no-id>')
            continue
        if inv_id in existing_ids:
            skipped.append(inv_id)
            continue
        existing_invs.append(inv)
        existing_ids.add(inv_id)
        added.append(inv_id)

    merged['invariants'] = existing_invs
    # If project file lacked metadata fields, backfill from template so
    # the hook + docs render correctly. Project values always win.
    for meta_key in ('_doc', '_schema', '_workflow', 'version'):
        if meta_key not in merged and meta_key in template_data:
            merged[meta_key] = template_data[meta_key]
    return merged, added, skipped


def load_preset_overlay(
    preset_name: str,
    presets_dir: Path,
) -> List[Dict[str, Any]]:
    """Resolve a preset (honoring `extends:`) and return its
    `invariants_overlay` array (R4).

    Returns an empty list when the preset has no overlay (most non-Odoo or
    base presets). Propagates FileNotFoundError / ValueError from
    `resolve_preset` so the caller can surface a clear "bad preset name"
    message rather than silently merging nothing.

    v0.23 R4-consumer.
    """
    preset = resolve_preset(preset_name, presets_dir)
    overlay = preset.get('invariants_overlay') or []
    if not isinstance(overlay, list):
        # Schema validation in resolve_preset already rejects this, but be
        # defensive against a caller passing a hand-built dict.
        return []
    return [e for e in overlay if isinstance(e, dict)]


def merge_invariants_file(
    project_path: Path,
    template_path: Path,
    overlay_invariants: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[str], List[str]]:
    """Read project + template invariants files, write merged result.

    Merges TWO sources into the project's invariants list (dedup by `id`,
    project wins, then template, then preset overlay):
      1. Template `invariants.json` defaults (existing behavior).
      2. The active preset's `invariants_overlay` (R4 — pass via
         `overlay_invariants`; resolve with `load_preset_overlay`). Optional;
         `None`/empty means "template only" (backward compatible).

    Returns `(added_ids, skipped_ids)`. Atomic write via temp + os.replace.
    `project_path` need not exist — when absent, the template (plus overlay)
    is seeded. Raises FileNotFoundError if template is missing (toolkit bug,
    not user error).

    v0.23 R4-consumer.
    """
    if not template_path.exists():
        raise FileNotFoundError(
            f'template invariants not found: {template_path}'
        )
    template_data = json.loads(template_path.read_text(encoding='utf-8'))
    project_data: Optional[Dict[str, Any]] = None
    if project_path.exists():
        project_data = json.loads(project_path.read_text(encoding='utf-8'))
    merged, added, skipped = merge_invariants(project_data, template_data)

    # R4: fold the preset overlay onto the just-merged result. We re-run the
    # same dedup-by-id pass treating `merged` as the project side, so:
    #   - overlay ids already present (from project OR template) are skipped,
    #   - genuinely new overlay ids are appended.
    if overlay_invariants:
        overlay_data = {'invariants': list(overlay_invariants)}
        merged, ov_added, ov_skipped = merge_invariants(merged, overlay_data)
        added.extend(ov_added)
        skipped.extend(ov_skipped)

    _atomic_write_json(project_path, merged)
    return added, skipped


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
