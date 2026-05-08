from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from common import SimpleMcpServer, ToolDefinition


WORKSPACE_ROOT = Path(
    os.environ.get("NAKIVO_WORKSPACE", Path(__file__).resolve().parents[2])
).resolve()
READONLY_START = ("select", "with", "values")
FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|alter|drop|create|grant|revoke|truncate|copy|vacuum|"
    r"analyze|comment|merge|call|do|refresh)\b",
    re.IGNORECASE,
)
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def env_status(_: dict[str, Any]) -> dict[str, Any]:
    env_values = {
        "NAKIVO_PSQL_BIN": os.environ.get("NAKIVO_PSQL_BIN", ""),
        "NAKIVO_PGHOST": os.environ.get("NAKIVO_PGHOST", ""),
        "NAKIVO_PGPORT": os.environ.get("NAKIVO_PGPORT", ""),
        "NAKIVO_PGUSER": os.environ.get("NAKIVO_PGUSER", ""),
        "NAKIVO_PGADMIN_DB": os.environ.get("NAKIVO_PGADMIN_DB", ""),
        "NAKIVO_PGDATABASE": os.environ.get("NAKIVO_PGDATABASE", ""),
    }
    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "env": env_values,
        "psql_exists": bool(env_values["NAKIVO_PSQL_BIN"])
        and Path(env_values["NAKIVO_PSQL_BIN"]).exists(),
    }


def psql_command(database: str, sql: str) -> list[str]:
    psql_bin = os.environ.get("NAKIVO_PSQL_BIN")
    if not psql_bin:
        raise ValueError("NAKIVO_PSQL_BIN is not configured")
    if not Path(psql_bin).exists():
        raise ValueError(f"psql binary not found: {psql_bin}")

    return [
        psql_bin,
        "-h",
        os.environ.get("NAKIVO_PGHOST", "127.0.0.1"),
        "-p",
        os.environ.get("NAKIVO_PGPORT", "5432"),
        "-U",
        os.environ.get("NAKIVO_PGUSER", ""),
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
        "-P",
        "footer=off",
        "-F",
        "\t",
        "-A",
        "-c",
        sql,
    ]


def run_psql(database: str, sql: str) -> dict[str, Any]:
    command = psql_command(database, sql)
    env = os.environ.copy()
    result = subprocess.run(
        command,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "psql failed")
    return {
        "database": database,
        "sql": sql,
        "stdout": result.stdout.strip(),
    }


def get_database(arguments: dict[str, Any]) -> str:
    database = str(arguments.get("database", "")).strip() or os.environ.get("NAKIVO_PGDATABASE", "")
    if not database:
        raise ValueError("database is required or set NAKIVO_PGDATABASE")
    return database


def list_databases(_: dict[str, Any]) -> dict[str, Any]:
    admin_db = os.environ.get("NAKIVO_PGADMIN_DB", "postgres")
    sql = (
        "SELECT datname FROM pg_database "
        "WHERE datistemplate = FALSE ORDER BY datname"
    )
    return run_psql(admin_db, sql)


def list_schemas(arguments: dict[str, Any]) -> dict[str, Any]:
    sql = (
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name NOT LIKE 'pg_%' "
        "AND schema_name <> 'information_schema' "
        "ORDER BY schema_name"
    )
    return run_psql(get_database(arguments), sql)


def describe_table(arguments: dict[str, Any]) -> dict[str, Any]:
    table_name = str(arguments.get("table_name", "")).strip()
    schema_name = str(arguments.get("schema_name", "public")).strip() or "public"
    if not table_name:
        raise ValueError("table_name is required")
    if not SAFE_IDENTIFIER.fullmatch(table_name):
        raise ValueError("table_name contains unsupported characters")
    if not SAFE_IDENTIFIER.fullmatch(schema_name):
        raise ValueError("schema_name contains unsupported characters")

    sql = (
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        f"WHERE table_schema = '{schema_name}' "
        f"AND table_name = '{table_name}' "
        "ORDER BY ordinal_position"
    )
    return run_psql(get_database(arguments), sql)


def ensure_readonly_sql(sql: str) -> str:
    normalized = sql.strip().rstrip(";").strip()
    if not normalized:
        raise ValueError("sql is required")
    lowered = normalized.lower()
    if not lowered.startswith(READONLY_START):
        raise ValueError("Only SELECT, WITH, and VALUES queries are allowed")
    if ";" in normalized:
        raise ValueError("Only one SQL statement is allowed")
    if FORBIDDEN_SQL.search(normalized):
        raise ValueError("Write or DDL statements are not allowed")
    return normalized


def query_readonly(arguments: dict[str, Any]) -> dict[str, Any]:
    sql = ensure_readonly_sql(str(arguments.get("sql", "")))
    limit = max(1, min(int(arguments.get("limit", 100)), 500))
    wrapped_sql = f"SELECT * FROM ({sql}) AS mcp_query LIMIT {limit}"
    return run_psql(get_database(arguments), wrapped_sql)


SERVER = SimpleMcpServer(
    name="nakivo_postgres",
    version="0.1.0",
    tools=[
        ToolDefinition(
            name="env_status",
            description="Show the active Postgres MCP environment values without exposing the password.",
            input_schema={"type": "object", "properties": {}},
            handler=env_status,
        ),
        ToolDefinition(
            name="list_databases",
            description="List non-template Postgres databases.",
            input_schema={"type": "object", "properties": {}},
            handler=list_databases,
        ),
        ToolDefinition(
            name="list_schemas",
            description="List user schemas in a database.",
            input_schema={
                "type": "object",
                "properties": {"database": {"type": "string"}},
            },
            handler=list_schemas,
        ),
        ToolDefinition(
            name="describe_table",
            description="Describe columns for a table using information_schema.",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "schema_name": {"type": "string"},
                    "table_name": {"type": "string"},
                },
                "required": ["table_name"],
            },
            handler=describe_table,
        ),
        ToolDefinition(
            name="query_readonly",
            description="Run a single read-only SELECT/WITH/VALUES query with a safety limit.",
            input_schema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "sql": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                "required": ["sql"],
            },
            handler=query_readonly,
        ),
    ],
)


if __name__ == "__main__":
    SERVER.serve()
