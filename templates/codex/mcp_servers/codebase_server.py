from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from common import SimpleMcpServer, ToolDefinition


WORKSPACE_ROOT = Path(
    os.environ.get("{{ENV_PREFIX}}_WORKSPACE", Path(__file__).resolve().parents[2])
).resolve()
# Addon roots come from the toolkit preset at install time; override at
# runtime with `{{ENV_PREFIX}}_ADDON_ROOTS=root1,root2,...` in .codex/mcp.local.env.
DEFAULT_ADDON_ROOTS = tuple(
    r.strip() for r in (
        os.environ.get("{{ENV_PREFIX}}_ADDON_ROOTS")
        or "{{ADDON_ROOTS_CSV}}"
    ).split(",") if r.strip()
)
TEXT_EXTENSIONS = {
    ".py",
    ".xml",
    ".csv",
    ".yml",
    ".yaml",
    ".js",
    ".md",
    ".rst",
    ".txt",
    ".ini",
    ".cfg",
}
MAX_RESULTS = 100
MAX_LINES = 250


def path_is_within(base_path: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base_path)
        return True
    except ValueError:
        return False


def resolve_path(path_value: str) -> Path:
    candidate = (WORKSPACE_ROOT / path_value).resolve()
    if not path_is_within(WORKSPACE_ROOT, candidate):
        raise ValueError(f"Path escapes workspace root: {path_value}")
    return candidate


def existing_addon_roots() -> list[str]:
    return [root for root in DEFAULT_ADDON_ROOTS if (WORKSPACE_ROOT / root).exists()]


def iter_search_roots(root_hint: str | None) -> list[Path]:
    if root_hint:
        return [resolve_path(root_hint)]
    return [WORKSPACE_ROOT / root for root in existing_addon_roots()]


def walk_manifest_files(base_path: Path) -> list[Path]:
    manifest_files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(base_path):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in {".git", "__pycache__", ".venv", "node_modules"}
            and not dirname.startswith(".")
        ]
        if "__manifest__.py" in filenames:
            manifest_files.append(Path(current_root) / "__manifest__.py")
            dirnames[:] = []
    return manifest_files


@lru_cache(maxsize=32)
def cached_manifest_files(root_hint: str | None) -> tuple[Path, ...]:
    seen: set[str] = set()
    manifest_files: list[Path] = []
    for search_root in iter_search_roots(root_hint):
        if not search_root.exists():
            continue
        for manifest_path in walk_manifest_files(search_root):
            rel_path = str(manifest_path.relative_to(WORKSPACE_ROOT))
            if rel_path in seen:
                continue
            seen.add(rel_path)
            manifest_files.append(manifest_path)
    manifest_files.sort(key=lambda item: str(item.relative_to(WORKSPACE_ROOT)))
    return tuple(manifest_files)


def clamp_limit(raw_limit: Any, default: int = 20, maximum: int = MAX_RESULTS) -> int:
    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def workspace_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "addon_roots": existing_addon_roots(),
    }


def discover_modules(arguments: dict[str, Any]) -> dict[str, Any]:
    root_hint = arguments.get("root_hint")
    name_contains = str(arguments.get("name_contains", "")).strip().lower()
    limit = clamp_limit(arguments.get("limit"), default=50)
    modules: list[dict[str, str]] = []

    for manifest_path in cached_manifest_files(root_hint):
        module_dir = manifest_path.parent
        module_name = module_dir.name
        rel_module_dir = str(module_dir.relative_to(WORKSPACE_ROOT))
        if name_contains and name_contains not in module_name.lower():
            continue
        modules.append(
            {
                "module": module_name,
                "path": rel_module_dir,
                "manifest_path": str(manifest_path.relative_to(WORKSPACE_ROOT)),
            }
        )
        if len(modules) >= limit:
            break

    return {"count": len(modules), "modules": modules}


def read_manifest(arguments: dict[str, Any]) -> dict[str, Any]:
    module_path = arguments.get("module_path")
    if not module_path:
        raise ValueError("module_path is required")

    target = resolve_path(str(module_path))
    manifest_path = target if target.name == "__manifest__.py" else target / "__manifest__.py"
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found: {module_path}")

    raw_text = manifest_path.read_text(encoding="utf-8")
    try:
        manifest = ast.literal_eval(raw_text)
    except (SyntaxError, ValueError):
        manifest = {"_raw": raw_text}

    return {
        "module_path": str(manifest_path.parent.relative_to(WORKSPACE_ROOT)),
        "manifest_path": str(manifest_path.relative_to(WORKSPACE_ROOT)),
        "manifest": manifest,
    }


def parse_rg_line(line: str) -> dict[str, Any] | None:
    first = line.find(":")
    if first < 0:
        return None
    second = line.find(":", first + 1)
    if second < 0:
        return None
    return {
        "path": line[:first],
        "line": int(line[first + 1 : second]),
        "text": line[second + 1 :],
    }


def search_with_rg(
    pattern: str,
    root_hint: str | None,
    limit: int,
    globs: list[str] | None = None,
) -> list[dict[str, Any]]:
    scope = "."
    if root_hint:
        scope = str(resolve_path(root_hint).relative_to(WORKSPACE_ROOT))

    command = ["rg", "-n", "--color", "never", "--hidden", pattern, scope]
    for glob in globs or []:
        command.extend(["-g", glob])

    result = subprocess.run(
        command,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "rg failed")

    matches: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parsed = parse_rg_line(line)
        if parsed is None:
            continue
        matches.append(parsed)
        if len(matches) >= limit:
            break
    return matches


def search_in_python(
    pattern: str,
    root_hint: str | None,
    limit: int,
    globs: list[str] | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    suffix_filters = {glob.rsplit(".", 1)[-1] for glob in globs or [] if glob.startswith("*.")}

    for search_root in iter_search_roots(root_hint):
        for current_root, dirnames, filenames in os.walk(search_root):
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if dirname not in {".git", "__pycache__", ".venv", "node_modules"}
                and not dirname.startswith(".")
            ]
            for filename in filenames:
                file_path = Path(current_root) / filename
                if suffix_filters and file_path.suffix.lstrip(".") not in suffix_filters:
                    continue
                if file_path.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                try:
                    lines = file_path.read_text(encoding="utf-8").splitlines()
                except UnicodeDecodeError:
                    continue
                for index, line in enumerate(lines, start=1):
                    if pattern in line:
                        matches.append(
                            {
                                "path": str(file_path.relative_to(WORKSPACE_ROOT)),
                                "line": index,
                                "text": line,
                            }
                        )
                        if len(matches) >= limit:
                            return matches
    return matches


def search_text(arguments: dict[str, Any]) -> dict[str, Any]:
    pattern = str(arguments.get("pattern", "")).strip()
    if not pattern:
        raise ValueError("pattern is required")
    limit = clamp_limit(arguments.get("limit"), default=20)
    root_hint = arguments.get("root_hint")
    glob_value = arguments.get("glob")
    globs = [str(glob_value)] if glob_value else None

    try:
        matches = search_with_rg(pattern, root_hint, limit, globs=globs)
    except FileNotFoundError:
        matches = search_in_python(pattern, root_hint, limit, globs=globs)

    return {"count": len(matches), "matches": matches}


def search_xml_ids(arguments: dict[str, Any]) -> dict[str, Any]:
    xml_id = str(arguments.get("xml_id", "")).strip()
    if not xml_id:
        raise ValueError("xml_id is required")
    limit = clamp_limit(arguments.get("limit"), default=20)

    try:
        matches = search_with_rg(
            xml_id,
            arguments.get("root_hint"),
            limit,
            globs=["*.xml", "*.csv", "*.yml", "*.yaml"],
        )
    except FileNotFoundError:
        matches = search_in_python(
            xml_id,
            arguments.get("root_hint"),
            limit,
            globs=["*.xml", "*.csv", "*.yml", "*.yaml"],
        )
    return {"count": len(matches), "matches": matches}


def search_model_definitions(arguments: dict[str, Any]) -> dict[str, Any]:
    model_name = str(arguments.get("model", "")).strip()
    limit = clamp_limit(arguments.get("limit"), default=20)
    matches: list[dict[str, Any]] = []

    for search_root in iter_search_roots(arguments.get("root_hint")):
        for current_root, dirnames, filenames in os.walk(search_root):
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if dirname not in {".git", "__pycache__", ".venv", "node_modules"}
                and not dirname.startswith(".")
            ]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                file_path = Path(current_root) / filename
                try:
                    lines = file_path.read_text(encoding="utf-8").splitlines()
                except UnicodeDecodeError:
                    continue
                for index, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if not stripped.startswith(("_name", "_inherit", "_inherits")):
                        continue
                    if model_name and model_name not in stripped:
                        continue
                    matches.append(
                        {
                            "path": str(file_path.relative_to(WORKSPACE_ROOT)),
                            "line": index,
                            "text": line.strip(),
                        }
                    )
                    if len(matches) >= limit:
                        return {"count": len(matches), "matches": matches}

    return {"count": len(matches), "matches": matches}


def list_test_targets(arguments: dict[str, Any]) -> dict[str, Any]:
    module_path = arguments.get("module_path")
    if not module_path:
        raise ValueError("module_path is required")

    module_dir = resolve_path(str(module_path))
    if not module_dir.is_dir():
        raise ValueError(f"Module path is not a directory: {module_path}")

    targets: list[str] = []
    tests_dir = module_dir / "tests"
    if tests_dir.exists():
        for test_file in sorted(tests_dir.rglob("test*.py")):
            targets.append(str(test_file.relative_to(WORKSPACE_ROOT)))

    return {
        "module_path": str(module_dir.relative_to(WORKSPACE_ROOT)),
        "test_files": targets,
        "suggested_test_tag": f"/{module_dir.name}",
    }


def read_file_chunk(arguments: dict[str, Any]) -> dict[str, Any]:
    path_value = arguments.get("path")
    if not path_value:
        raise ValueError("path is required")

    file_path = resolve_path(str(path_value))
    if not file_path.is_file():
        raise ValueError(f"File not found: {path_value}")

    start_line = max(1, int(arguments.get("start_line", 1)))
    end_line = int(arguments.get("end_line", start_line + 79))
    if end_line < start_line:
        raise ValueError("end_line must be greater than or equal to start_line")
    if end_line - start_line + 1 > MAX_LINES:
        end_line = start_line + MAX_LINES - 1

    lines = file_path.read_text(encoding="utf-8").splitlines()
    slice_text = "\n".join(lines[start_line - 1 : end_line])
    return {
        "path": str(file_path.relative_to(WORKSPACE_ROOT)),
        "start_line": start_line,
        "end_line": min(end_line, len(lines)),
        "text": slice_text,
    }


# ---------------------------------------------------------------------------
# Generic Odoo helpers (module-agnostic).
# ---------------------------------------------------------------------------


def parse_manifest_safely(manifest_path: Path) -> dict[str, Any]:
    raw_text = manifest_path.read_text(encoding="utf-8")
    try:
        manifest = ast.literal_eval(raw_text)
        return manifest if isinstance(manifest, dict) else {}
    except (SyntaxError, ValueError):
        return {}


def module_dependencies(arguments: dict[str, Any]) -> dict[str, Any]:
    module_name = str(arguments.get("module", "")).strip()
    if not module_name:
        raise ValueError("module is required")

    matched_path: Path | None = None
    for manifest_path in cached_manifest_files(arguments.get("root_hint")):
        if manifest_path.parent.name == module_name:
            matched_path = manifest_path
            break
    if matched_path is None:
        raise ValueError(f"Module not found in known addon roots: {module_name}")

    manifest = parse_manifest_safely(matched_path)
    direct_deps = list(manifest.get("depends") or [])
    return {
        "module": module_name,
        "manifest_path": str(matched_path.relative_to(WORKSPACE_ROOT)),
        "version": manifest.get("version"),
        "category": manifest.get("category"),
        "auto_install": bool(manifest.get("auto_install")),
        "direct_dependencies": direct_deps,
        "data_files": list(manifest.get("data") or []),
        "demo_files": list(manifest.get("demo") or []),
    }


def find_inheritance_chain(arguments: dict[str, Any]) -> dict[str, Any]:
    model_name = str(arguments.get("model", "")).strip()
    if not model_name:
        raise ValueError("model is required")
    limit = clamp_limit(arguments.get("limit"), default=50)

    name_pattern = re.compile(r"_name\s*=\s*['\"]([^'\"]+)['\"]")
    inherit_pattern = re.compile(r"_inherit\s*=\s*(?:['\"]([^'\"]+)['\"]|\[([^\]]+)\])")

    declarations: list[dict[str, Any]] = []
    for search_root in iter_search_roots(arguments.get("root_hint")):
        for current_root, dirnames, filenames in os.walk(search_root):
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if dirname not in {".git", "__pycache__", ".venv", "node_modules"}
                and not dirname.startswith(".")
            ]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                file_path = Path(current_root) / filename
                try:
                    text = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if model_name not in text:
                    continue
                for index, line in enumerate(text.splitlines(), start=1):
                    name_match = name_pattern.search(line)
                    inherit_match = inherit_pattern.search(line)
                    target_names: list[str] = []
                    role = ""
                    if name_match:
                        target_names = [name_match.group(1)]
                        role = "_name"
                    elif inherit_match:
                        single = inherit_match.group(1)
                        many = inherit_match.group(2)
                        if single:
                            target_names = [single]
                        elif many:
                            target_names = re.findall(r"['\"]([^'\"]+)['\"]", many)
                        role = "_inherit"
                    if model_name in target_names:
                        declarations.append(
                            {
                                "path": str(file_path.relative_to(WORKSPACE_ROOT)),
                                "line": index,
                                "role": role,
                                "models": target_names,
                            }
                        )
                        if len(declarations) >= limit:
                            return {"model": model_name, "count": len(declarations), "declarations": declarations}
    return {"model": model_name, "count": len(declarations), "declarations": declarations}


# ---------------------------------------------------------------------------
# Canonical decisions registry: makes recurring answers reproducible.
# ---------------------------------------------------------------------------


CANONICAL_REGISTRY_PATH = WORKSPACE_ROOT / ".codex" / "canonical_decisions.json"


def load_canonical_registry() -> dict[str, Any]:
    if not CANONICAL_REGISTRY_PATH.exists():
        return {"decisions": [], "version": 0}
    try:
        return json.loads(CANONICAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"decisions": [], "version": -1}


def list_canonical_decisions(arguments: dict[str, Any]) -> dict[str, Any]:
    registry = load_canonical_registry()
    topic = str(arguments.get("topic_contains", "")).strip().lower()
    decisions = registry.get("decisions") or []
    if topic:
        decisions = [d for d in decisions if topic in (d.get("topic") or "").lower()]
    return {
        "registry_path": str(CANONICAL_REGISTRY_PATH.relative_to(WORKSPACE_ROOT)),
        "version": registry.get("version"),
        "count": len(decisions),
        "decisions": decisions,
    }


def lookup_canonical_decision(arguments: dict[str, Any]) -> dict[str, Any]:
    topic = str(arguments.get("topic", "")).strip().lower()
    if not topic:
        raise ValueError("topic is required")
    registry = load_canonical_registry()
    matches: list[dict[str, Any]] = []
    for decision in registry.get("decisions") or []:
        haystack = " ".join(
            [
                str(decision.get("topic") or ""),
                " ".join(decision.get("aliases") or []),
                str(decision.get("question") or ""),
            ]
        ).lower()
        if topic in haystack:
            matches.append(decision)
    return {
        "topic": topic,
        "match_count": len(matches),
        "matches": matches,
        "advice": (
            "If multiple matches, pick the most specific topic. "
            "Always cite registry_path and version when answering."
        ),
        "registry_path": str(CANONICAL_REGISTRY_PATH.relative_to(WORKSPACE_ROOT))
        if CANONICAL_REGISTRY_PATH.exists() else None,
        "version": registry.get("version"),
    }


SERVER = SimpleMcpServer(
    name="{{PROJECT_NAME_SLUG}}_codebase",
    version="0.1.0",
    tools=[
        ToolDefinition(
            name="workspace_status",
            description="Show the active workspace root and addon roots.",
            input_schema={"type": "object", "properties": {}},
            handler=workspace_status,
        ),
        ToolDefinition(
            name="discover_modules",
            description="List Odoo modules by scanning __manifest__.py files under known addon roots.",
            input_schema={
                "type": "object",
                "properties": {
                    "root_hint": {"type": "string"},
                    "name_contains": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
                },
            },
            handler=discover_modules,
        ),
        ToolDefinition(
            name="read_manifest",
            description="Read and parse a module __manifest__.py file.",
            input_schema={
                "type": "object",
                "properties": {"module_path": {"type": "string"}},
                "required": ["module_path"],
            },
            handler=read_manifest,
        ),
        ToolDefinition(
            name="search_text",
            description="Search text inside the workspace and return short line matches.",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "root_hint": {"type": "string"},
                    "glob": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
                },
                "required": ["pattern"],
            },
            handler=search_text,
        ),
        ToolDefinition(
            name="search_xml_ids",
            description="Search XML IDs across xml/csv/yaml files.",
            input_schema={
                "type": "object",
                "properties": {
                    "xml_id": {"type": "string"},
                    "root_hint": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
                },
                "required": ["xml_id"],
            },
            handler=search_xml_ids,
        ),
        ToolDefinition(
            name="search_model_definitions",
            description="Search Python model declarations using _name, _inherit, or _inherits.",
            input_schema={
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "root_hint": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
                },
            },
            handler=search_model_definitions,
        ),
        ToolDefinition(
            name="list_test_targets",
            description="List test files for a module and suggest an Odoo test tag.",
            input_schema={
                "type": "object",
                "properties": {"module_path": {"type": "string"}},
                "required": ["module_path"],
            },
            handler=list_test_targets,
        ),
        ToolDefinition(
            name="read_file_chunk",
            description="Read a short line range from a file inside the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
            handler=read_file_chunk,
        ),
        ToolDefinition(
            name="module_dependencies",
            description="Read a module's __manifest__.py and return depends/data/demo/version (works for any Odoo 12 addon).",
            input_schema={
                "type": "object",
                "properties": {
                    "module": {"type": "string"},
                    "root_hint": {"type": "string"},
                },
                "required": ["module"],
            },
            handler=module_dependencies,
        ),
        ToolDefinition(
            name="find_inheritance_chain",
            description="Find every Python file declaring _name or _inherit for a given Odoo model name. Module-agnostic.",
            input_schema={
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "root_hint": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
                },
                "required": ["model"],
            },
            handler=find_inheritance_chain,
        ),
        ToolDefinition(
            name="list_canonical_decisions",
            description="List canonical project decisions from .codex/canonical_decisions.json - the single source of truth used to keep agent answers consistent across conversations.",
            input_schema={
                "type": "object",
                "properties": {"topic_contains": {"type": "string"}},
            },
            handler=list_canonical_decisions,
        ),
        ToolDefinition(
            name="lookup_canonical_decision",
            description="Look up the canonical answer for a topic before answering recurring questions. If a match exists, ALWAYS prefer the registered answer over re-deriving one.",
            input_schema={
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
            handler=lookup_canonical_decision,
        ),
    ],
)


if __name__ == "__main__":
    SERVER.serve()
