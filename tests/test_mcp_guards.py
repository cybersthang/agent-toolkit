"""Unit tests for the MCP server safety guards.

The Codex MCP servers ship two layers of pure-Python defence that must never
silently regress:

  * postgres_server.py
      - ensure_readonly_sql()  — rejects write/DDL SQL, allows read-only SELECT.
      - FORBIDDEN_SQL regex     — INSERT/UPDATE/DELETE/DROP/... token blocklist.
      - SAFE_IDENTIFIER regex   — table/schema name validator (used by
                                  describe_table) — blocks injection-y names.

  * realdata_test_server.py
      - validate_module_name() / SAFE_MODULE — Odoo module-name validator.
      - is_production_like()    — prod-detection guard (prod marker wins).

These guards are pure Python (the servers shell out to `psql` / `odoo-bin`,
they do NOT import psycopg2), so we can load each module BY PATH — the same
importlib pattern used by tests/test_agent_toolkit_init.py — and assert on the
guard functions directly. The ModuleNotFoundError-skip pattern below keeps CI
green if a future refactor adds a hard third-party import at module load time.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVERS_DIR = TOOLKIT_ROOT / "templates" / "codex" / "mcp_servers"


def _load_server_module(filename: str, module_name: str):
    """importlib-load an MCP server BY PATH.

    The server does `from common import ...`, so the mcp_servers dir must be on
    sys.path. Skip (with reason) — rather than error — if an optional dep like
    psycopg2 is required at import time.
    """
    path = MCP_SERVERS_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} not found at {path}")
    inserted = False
    if str(MCP_SERVERS_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_SERVERS_DIR))
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # main() is __main__-guarded; safe to import
        return mod
    except ModuleNotFoundError as exc:  # optional dep missing in CI
        pytest.skip(f"{filename} needs an unavailable dependency: {exc.name}")
    finally:
        if inserted and str(MCP_SERVERS_DIR) in sys.path:
            sys.path.remove(str(MCP_SERVERS_DIR))


@pytest.fixture(scope="module")
def pg():
    return _load_server_module("postgres_server.py", "postgres_server_under_test")


@pytest.fixture(scope="module")
def realdata():
    return _load_server_module("realdata_test_server.py", "realdata_test_server_under_test")


# --- (a) write/DDL SQL is REJECTED by the read-only guard --------------------

@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO res_users (login) VALUES ('x')",
        "UPDATE res_users SET active = false",
        "DELETE FROM res_users",
        "DROP TABLE res_users",
        "ALTER TABLE res_users ADD COLUMN x int",
        "TRUNCATE res_users",
        "SELECT 1; DROP TABLE res_users",          # multi-statement smuggling
    ],
)
def test_write_ddl_sql_is_rejected(pg, sql):
    with pytest.raises(ValueError):
        pg.ensure_readonly_sql(sql)


# --- (b) a plain SELECT passes the read-only guard ---------------------------

def test_select_passes_readonly_guard(pg):
    out = pg.ensure_readonly_sql("SELECT id, login FROM res_users WHERE active")
    assert out.lower().startswith("select")


def test_with_and_values_pass_readonly_guard(pg):
    assert pg.ensure_readonly_sql("WITH t AS (SELECT 1) SELECT * FROM t").lower().startswith("with")
    assert pg.ensure_readonly_sql("VALUES (1), (2)").lower().startswith("values")


# --- (c) an injection-y identifier is rejected by the validator --------------

@pytest.mark.parametrize(
    "ident",
    [
        "res_users; DROP TABLE x",
        "res users",            # space
        "res-users",            # hyphen
        "1users",               # leading digit
        "res_users'--",         # quote / comment
        "",                     # empty
    ],
)
def test_injectiony_identifier_is_rejected(pg, ident):
    assert pg.SAFE_IDENTIFIER.fullmatch(ident) is None


def test_clean_identifier_is_accepted(pg):
    assert pg.SAFE_IDENTIFIER.fullmatch("res_users") is not None
    assert pg.SAFE_IDENTIFIER.fullmatch("_private_table1") is not None


# --- realdata_test_server guards ---------------------------------------------

@pytest.mark.parametrize(
    "module_name",
    ["my.module", "drop;table", "mod-name", "1mod", "", "mod name"],
)
def test_module_name_validator_rejects_bad_names(realdata, module_name):
    with pytest.raises(ValueError):
        realdata.validate_module_name(module_name)


def test_module_name_validator_accepts_good_name(realdata):
    assert realdata.validate_module_name("sale_management") == "sale_management"


@pytest.mark.parametrize(
    "db_name",
    ["odoo_prod", "production_main", "live_db", "prod_clone_for_load_test"],
)
def test_prod_detection_flags_production_like_dbs(realdata, db_name):
    assert realdata.is_production_like(db_name) is True


@pytest.mark.parametrize("db_name", ["staging_clone", "test_db", "odoo_dev"])
def test_prod_detection_allows_non_production_dbs(realdata, db_name):
    assert realdata.is_production_like(db_name) is False
