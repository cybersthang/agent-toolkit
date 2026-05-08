from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import SimpleMcpServer, ToolDefinition


WORKSPACE_ROOT = Path(
    os.environ.get("NAKIVO_WORKSPACE", Path(__file__).resolve().parents[2])
).resolve()
DEFAULT_ODOO_BIN = WORKSPACE_ROOT / "nakivo-server" / "odoo-bin"
DEFAULT_ODOO_CONF = WORKSPACE_ROOT / "odoo-12-enterprise-master" / "odoo.conf"
DEFAULT_SMOKE_TEST = WORKSPACE_ROOT / "scripts" / "smoke_test.py"
SAFE_MODULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_OUTPUT_CHARS = 12000

# Read-only ORM expression sandbox.
# Only single Python expressions; no statements, no assignment, no imports,
# no dunder access, and no obviously mutating ORM ops.
FORBIDDEN_EVAL_TOKENS = (
    "=",
    "import ",
    "__",
    ".write(",
    ".create(",
    ".unlink(",
    ".update(",
    ".commit(",
    ".rollback(",
    ".execute(",
    ".sudo(",
    "open(",
    "compile(",
    "exec(",
    "eval(",
    ";",
    "\n",
    "\r",
)
EVAL_RESULT_MARKER = "__MCP_EVAL_RESULT__"


def path_is_within(base_path: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base_path)
        return True
    except ValueError:
        return False


def resolve_workspace_path(path_value: str, default_path: Path) -> Path:
    raw_value = str(path_value or "").strip()
    candidate = Path(raw_value) if raw_value else default_path
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    candidate = candidate.resolve()
    if not path_is_within(WORKSPACE_ROOT, candidate):
        raise ValueError(f"Path escapes workspace root: {path_value}")
    return candidate


def clamp_timeout(raw_timeout: Any, default: int = 900) -> int:
    try:
        value = int(raw_timeout)
    except (TypeError, ValueError):
        return default
    return max(30, min(value, 7200))


def bool_arg(arguments: Dict[str, Any], name: str, default: bool = False) -> bool:
    value = arguments.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def get_database(arguments: Dict[str, Any]) -> str:
    database = str(arguments.get("database", "")).strip()
    if not database:
        database = os.environ.get("NAKIVO_PGDATABASE", "") or os.environ.get("PGDATABASE", "")
    if not database:
        raise ValueError("database is required or set NAKIVO_PGDATABASE")
    return database


def is_production_like(database: str) -> bool:
    lowered = database.lower()
    if any(marker in lowered for marker in ("staging", "stage", "test", "clone", "dev", "uat")):
        return False
    return any(marker in lowered for marker in ("prod", "production", "live"))


def get_python_bin(arguments: Dict[str, Any]) -> str:
    return str(
        arguments.get("python_bin")
        or os.environ.get("NAKIVO_PYTHON_BIN")
        or sys.executable
    )


def get_odoo_bin(arguments: Dict[str, Any]) -> Path:
    return resolve_workspace_path(
        str(arguments.get("odoo_bin") or os.environ.get("NAKIVO_ODOO_BIN", "")),
        DEFAULT_ODOO_BIN,
    )


def get_odoo_conf(arguments: Dict[str, Any]) -> Path:
    return resolve_workspace_path(
        str(arguments.get("odoo_conf") or os.environ.get("NAKIVO_ODOO_CONF", "")),
        DEFAULT_ODOO_CONF,
    )


def redact_command(command: List[str]) -> List[str]:
    redacted: List[str] = []
    previous = ""
    for item in command:
        if previous in {"--db-password", "--password"}:
            redacted.append("***")
        else:
            redacted.append(item)
        previous = item
    return redacted


def command_text(command: List[str]) -> str:
    return subprocess.list2cmdline(redact_command(command))


def base_env() -> Dict[str, str]:
    env = os.environ.copy()
    mappings = {
        "NAKIVO_PGHOST": "PGHOST",
        "NAKIVO_PGPORT": "PGPORT",
        "NAKIVO_PGUSER": "PGUSER",
        "NAKIVO_PGPASSWORD": "PGPASSWORD",
        "NAKIVO_PGDATABASE": "PGDATABASE",
    }
    for source_key, target_key in mappings.items():
        value = env.get(source_key)
        if value and not env.get(target_key):
            env[target_key] = value

    psql_bin = env.get("NAKIVO_PSQL_BIN", "")
    if psql_bin and Path(psql_bin).exists():
        psql_dir = str(Path(psql_bin).resolve().parent)
        env["PATH"] = psql_dir + os.pathsep + env.get("PATH", "")
    return env


def tail_text(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[-MAX_OUTPUT_CHARS:]


def run_command(command: List[str], timeout: int) -> Dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=base_env(),
        timeout=timeout,
        check=False,
    )
    return {
        "returncode": result.returncode,
        "command": redact_command(command),
        "command_text": command_text(command),
        "stdout_tail": tail_text(result.stdout.strip()),
        "stderr_tail": tail_text(result.stderr.strip()),
    }


def env_status(_: Dict[str, Any]) -> Dict[str, Any]:
    database = os.environ.get("NAKIVO_PGDATABASE", "") or os.environ.get("PGDATABASE", "")
    psql_bin = os.environ.get("NAKIVO_PSQL_BIN", "")
    odoo_bin = Path(os.environ.get("NAKIVO_ODOO_BIN", "") or DEFAULT_ODOO_BIN)
    odoo_conf = Path(os.environ.get("NAKIVO_ODOO_CONF", "") or DEFAULT_ODOO_CONF)
    smoke_test = DEFAULT_SMOKE_TEST
    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "database": database,
        "database_looks_production": bool(database and is_production_like(database)),
        "pg_host": os.environ.get("NAKIVO_PGHOST", "") or os.environ.get("PGHOST", ""),
        "pg_port": os.environ.get("NAKIVO_PGPORT", "") or os.environ.get("PGPORT", ""),
        "pg_user": os.environ.get("NAKIVO_PGUSER", "") or os.environ.get("PGUSER", ""),
        "pg_password_configured": bool(
            os.environ.get("NAKIVO_PGPASSWORD") or os.environ.get("PGPASSWORD")
        ),
        "psql_bin": psql_bin,
        "psql_exists": bool(psql_bin and Path(psql_bin).exists()),
        "odoo_bin": str(odoo_bin),
        "odoo_bin_exists": odoo_bin.exists(),
        "odoo_conf": str(odoo_conf),
        "odoo_conf_exists": odoo_conf.exists(),
        "smoke_test": str(smoke_test),
        "smoke_test_exists": smoke_test.exists(),
    }


def smoke_test_command(arguments: Dict[str, Any]) -> List[str]:
    smoke_test = resolve_workspace_path(
        str(arguments.get("smoke_test") or ""),
        DEFAULT_SMOKE_TEST,
    )
    command = [
        get_python_bin(arguments),
        str(smoke_test),
        "--db-name",
        get_database(arguments),
        "--db-host",
        os.environ.get("NAKIVO_PGHOST", "") or os.environ.get("PGHOST", "localhost"),
        "--db-port",
        os.environ.get("NAKIVO_PGPORT", "") or os.environ.get("PGPORT", "5432"),
        "--db-user",
        os.environ.get("NAKIVO_PGUSER", "") or os.environ.get("PGUSER", "odoo"),
        "--odoo-bin",
        str(get_odoo_bin(arguments)),
        "--odoo-conf",
        str(get_odoo_conf(arguments)),
    ]
    if bool_arg(arguments, "skip_registry"):
        command.append("--skip-registry")
    if bool_arg(arguments, "skip_row_count"):
        command.append("--skip-row-count")
    return command


def build_smoke_test_command(arguments: Dict[str, Any]) -> Dict[str, Any]:
    command = smoke_test_command(arguments)
    database = get_database(arguments)
    return {
        "command": redact_command(command),
        "command_text": command_text(command),
        "database_looks_production": is_production_like(database),
        "notes": [
            "Runs scripts/smoke_test.py against the configured real/staging data.",
            "The smoke script uses SELECT probes and an Odoo registry boot check.",
        ],
    }


def run_smoke_test(arguments: Dict[str, Any]) -> Dict[str, Any]:
    command = smoke_test_command(arguments)
    return run_command(command, clamp_timeout(arguments.get("timeout"), default=1200))


def registry_boot_command(arguments: Dict[str, Any]) -> List[str]:
    return [
        get_python_bin(arguments),
        str(get_odoo_bin(arguments)),
        "-c",
        str(get_odoo_conf(arguments)),
        "-d",
        get_database(arguments),
        "--stop-after-init",
    ]


def run_registry_boot(arguments: Dict[str, Any]) -> Dict[str, Any]:
    command = registry_boot_command(arguments)
    return run_command(command, clamp_timeout(arguments.get("timeout"), default=900))


def validate_module_name(module_name: str) -> str:
    module_name = module_name.strip()
    if not module_name:
        raise ValueError("module_name is required")
    if not SAFE_MODULE.fullmatch(module_name):
        raise ValueError("module_name contains unsupported characters")
    return module_name


def module_test_command(arguments: Dict[str, Any]) -> List[str]:
    module_name = validate_module_name(str(arguments.get("module_name", "")))
    module_action = str(arguments.get("module_action", "update")).strip().lower()
    if module_action not in {"update", "install", "none"}:
        raise ValueError("module_action must be update, install, or none")

    command = [
        get_python_bin(arguments),
        str(get_odoo_bin(arguments)),
        "-c",
        str(get_odoo_conf(arguments)),
        "-d",
        get_database(arguments),
        "--test-enable",
        "--stop-after-init",
    ]
    if module_action == "update":
        command.extend(["-u", module_name])
    elif module_action == "install":
        command.extend(["-i", module_name])

    test_tag = str(arguments.get("test_tag", "")).strip() or f"/{module_name}"
    if test_tag:
        command.extend(["--test-tags", test_tag])
    return command


def build_module_test_command(arguments: Dict[str, Any]) -> Dict[str, Any]:
    command = module_test_command(arguments)
    database = get_database(arguments)
    return {
        "command": redact_command(command),
        "command_text": command_text(command),
        "database_looks_production": is_production_like(database),
        "notes": [
            "Odoo module tests can write test records and update module metadata.",
            "Use run_module_test only on a staging clone or an explicitly approved real-data test database.",
        ],
    }


def run_module_test(arguments: Dict[str, Any]) -> Dict[str, Any]:
    database = get_database(arguments)
    if is_production_like(database) and not bool_arg(arguments, "allow_production_like"):
        raise ValueError(
            "database name looks production-like; pass allow_production_like=true only after explicit approval"
        )
    if not bool_arg(arguments, "allow_db_write"):
        raise ValueError(
            "run_module_test can write to the target DB; pass allow_db_write=true only for approved test data"
        )
    command = module_test_command(arguments)
    return run_command(command, clamp_timeout(arguments.get("timeout"), default=1800))


# ---------------------------------------------------------------------------
# Algorithm verification on real data (deterministic, read-only ORM evaluation).
# ---------------------------------------------------------------------------


def ensure_readonly_expression(expression: str) -> str:
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("expression is required")
    if len(expr) > 2000:
        raise ValueError("expression exceeds 2000 chars; keep it focused")
    lowered = expr.lower()
    for token in FORBIDDEN_EVAL_TOKENS:
        if token in lowered:
            raise ValueError(
                f"expression contains forbidden token '{token.strip() or token!r}'; "
                "ORM eval is read-only - no mutation, imports, dunders, or statements"
            )
    return expr


def write_eval_script(expression: str) -> Path:
    expr = ensure_readonly_expression(expression)
    fd, raw_path = tempfile.mkstemp(prefix="mcp_eval_", suffix=".py")
    os.close(fd)
    script = textwrap.dedent(
        f"""
        # Auto-generated read-only ORM eval for MCP algorithm verification.
        import json
        import sys

        def _mcp_run(env):
            try:
                value = ({expr})
            except Exception as exc:  # pragma: no cover - reported back to caller
                payload = {{"ok": False, "error": str(exc), "type": exc.__class__.__name__}}
            else:
                try:
                    payload = {{"ok": True, "value": value}}
                    sys.stdout.write({EVAL_RESULT_MARKER!r} + json.dumps(payload, default=str, ensure_ascii=False) + "\\n")
                    return
                except (TypeError, ValueError) as exc:
                    payload = {{"ok": False, "error": "non-json-serialisable: " + str(exc)}}
            sys.stdout.write({EVAL_RESULT_MARKER!r} + json.dumps(payload, default=str, ensure_ascii=False) + "\\n")

        _mcp_run(env)
        """
    ).strip() + "\n"
    Path(raw_path).write_text(script, encoding="utf-8")
    return Path(raw_path)


def odoo_shell_command(arguments: Dict[str, Any], script_path: Path) -> List[str]:
    return [
        get_python_bin(arguments),
        str(get_odoo_bin(arguments)),
        "shell",
        "-c",
        str(get_odoo_conf(arguments)),
        "-d",
        get_database(arguments),
        "--stop-after-init",
        "--no-http",
        "--logfile=" + str(WORKSPACE_ROOT / "tmp_mcp_eval.log"),
        "<",
        str(script_path),
    ]


def parse_eval_output(stdout: str) -> Dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.startswith(EVAL_RESULT_MARKER):
            try:
                return json.loads(line[len(EVAL_RESULT_MARKER):])
            except json.JSONDecodeError:
                continue
    return {"ok": False, "error": "no eval result marker found in odoo shell output"}


def fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_orm_eval_once(arguments: Dict[str, Any], expression: str) -> Dict[str, Any]:
    script_path = write_eval_script(expression)
    try:
        # Use a shell to redirect the script as stdin to odoo-bin shell.
        # Build a single-string command for shell=True execution to handle '<' redirect.
        cmd_str = subprocess.list2cmdline(
            [
                get_python_bin(arguments),
                str(get_odoo_bin(arguments)),
                "shell",
                "-c",
                str(get_odoo_conf(arguments)),
                "-d",
                get_database(arguments),
                "--stop-after-init",
                "--no-http",
            ]
        )
        cmd_str += " < " + subprocess.list2cmdline([str(script_path)])
        result = subprocess.run(
            cmd_str,
            shell=True,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=base_env(),
            timeout=clamp_timeout(arguments.get("timeout"), default=600),
            check=False,
        )
        parsed = parse_eval_output(result.stdout)
        return {
            "returncode": result.returncode,
            "expression": expression,
            "result": parsed,
            "fingerprint": fingerprint(parsed.get("value")) if parsed.get("ok") else None,
            "stdout_tail": tail_text(result.stdout.strip()),
            "stderr_tail": tail_text(result.stderr.strip()),
        }
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass


def eval_orm_expression(arguments: Dict[str, Any]) -> Dict[str, Any]:
    expression = str(arguments.get("expression") or "")
    return run_orm_eval_once(arguments, expression)


def consistency_check_eval(arguments: Dict[str, Any]) -> Dict[str, Any]:
    expression = str(arguments.get("expression") or "")
    runs = max(2, min(int(arguments.get("runs", 2)), 5))
    fingerprints: List[str] = []
    last: Optional[Dict[str, Any]] = None
    for _ in range(runs):
        outcome = run_orm_eval_once(arguments, expression)
        last = outcome
        if not outcome["result"].get("ok"):
            return {
                "deterministic": False,
                "reason": "eval failed",
                "runs_completed": len(fingerprints) + 1,
                "last_run": outcome,
            }
        fingerprints.append(outcome["fingerprint"])
    deterministic = len(set(fingerprints)) == 1
    return {
        "deterministic": deterministic,
        "runs": runs,
        "fingerprints": fingerprints,
        "value": (last or {}).get("result", {}).get("value"),
        "last_run_command_returncode": (last or {}).get("returncode"),
    }


def compare_with_expected(arguments: Dict[str, Any]) -> Dict[str, Any]:
    expression = str(arguments.get("expression") or "")
    expected = arguments.get("expected")
    outcome = run_orm_eval_once(arguments, expression)
    actual = outcome["result"].get("value") if outcome["result"].get("ok") else None
    matches = outcome["result"].get("ok") and json.dumps(actual, sort_keys=True, default=str) == json.dumps(
        expected, sort_keys=True, default=str
    )
    return {
        "matches": bool(matches),
        "expected": expected,
        "actual": actual,
        "fingerprint_actual": outcome.get("fingerprint"),
        "result_ok": outcome["result"].get("ok"),
        "error": outcome["result"].get("error"),
    }


SERVER = SimpleMcpServer(
    name="nakivo_realdata_test",
    version="0.1.0",
    tools=[
        ToolDefinition(
            name="env_status",
            description="Show real-data test MCP environment without exposing the DB password.",
            input_schema={"type": "object", "properties": {}},
            handler=env_status,
        ),
        ToolDefinition(
            name="build_smoke_test_command",
            description="Build the smoke-test command for the configured real/staging data without running it.",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "skip_registry": {"type": "boolean"},
                    "skip_row_count": {"type": "boolean"},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                    "smoke_test": {"type": "string"},
                },
            },
            handler=build_smoke_test_command,
        ),
        ToolDefinition(
            name="run_smoke_test",
            description="Run scripts/smoke_test.py against the configured real/staging data.",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "skip_registry": {"type": "boolean"},
                    "skip_row_count": {"type": "boolean"},
                    "timeout": {"type": "integer", "minimum": 30, "maximum": 7200},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                    "smoke_test": {"type": "string"},
                },
            },
            handler=run_smoke_test,
        ),
        ToolDefinition(
            name="run_registry_boot",
            description="Boot Odoo against the target DB with --stop-after-init.",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 30, "maximum": 7200},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                },
            },
            handler=run_registry_boot,
        ),
        ToolDefinition(
            name="build_module_test_command",
            description="Build an Odoo module test command without running it.",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "module_name": {"type": "string"},
                    "module_action": {
                        "type": "string",
                        "enum": ["update", "install", "none"],
                    },
                    "test_tag": {"type": "string"},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                },
                "required": ["module_name"],
            },
            handler=build_module_test_command,
        ),
        ToolDefinition(
            name="run_module_test",
            description="Run Odoo module tests on approved real/staging data with explicit write guards.",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "module_name": {"type": "string"},
                    "module_action": {
                        "type": "string",
                        "enum": ["update", "install", "none"],
                    },
                    "test_tag": {"type": "string"},
                    "allow_db_write": {"type": "boolean"},
                    "allow_production_like": {"type": "boolean"},
                    "timeout": {"type": "integer", "minimum": 30, "maximum": 7200},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                },
                "required": ["module_name", "allow_db_write"],
            },
            handler=run_module_test,
        ),
        ToolDefinition(
            name="eval_orm_expression",
            description=(
                "Run a single read-only ORM expression against the configured DB via odoo-bin shell. "
                "Mutation tokens (write/create/unlink/commit/import/dunders/=) are forbidden. "
                "Returns the value plus a sha256 fingerprint for cross-run comparison."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Single Python expression evaluated with `env` available, e.g. env['sale.order'].search_count([])",
                    },
                    "database": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 30, "maximum": 7200},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                },
                "required": ["expression"],
            },
            handler=eval_orm_expression,
        ),
        ToolDefinition(
            name="consistency_check_eval",
            description=(
                "Run the same read-only ORM expression multiple times against the same DB snapshot "
                "and verify the fingerprints match. Use this to prove an algorithm is deterministic on real data."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "runs": {"type": "integer", "minimum": 2, "maximum": 5, "default": 2},
                    "database": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 30, "maximum": 7200},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                },
                "required": ["expression"],
            },
            handler=consistency_check_eval,
        ),
        ToolDefinition(
            name="compare_with_expected",
            description=(
                "Run a read-only ORM expression and compare the JSON-serialised result with a caller-supplied expected value. "
                "Returns matches=true only on byte-identical JSON."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "expected": {},
                    "database": {"type": "string"},
                    "timeout": {"type": "integer", "minimum": 30, "maximum": 7200},
                    "python_bin": {"type": "string"},
                    "odoo_bin": {"type": "string"},
                    "odoo_conf": {"type": "string"},
                },
                "required": ["expression", "expected"],
            },
            handler=compare_with_expected,
        ),
    ],
)


if __name__ == "__main__":
    SERVER.serve()
