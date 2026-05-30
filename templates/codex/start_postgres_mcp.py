from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


ALIASES = {
    "db_host": "{{ENV_PREFIX}}_PGHOST",
    "db_port": "{{ENV_PREFIX}}_PGPORT",
    "db_user": "{{ENV_PREFIX}}_PGUSER",
    "db_password": "{{ENV_PREFIX}}_PGPASSWORD",
    "db_name": "{{ENV_PREFIX}}_PGDATABASE",
    "database": "{{ENV_PREFIX}}_PGDATABASE",
    "http_port": "{{ENV_PREFIX}}_HTTP_PORT",
}

PSQL_ENV_ALIASES = {
    "{{ENV_PREFIX}}_PGHOST": "PGHOST",
    "{{ENV_PREFIX}}_PGPORT": "PGPORT",
    "{{ENV_PREFIX}}_PGUSER": "PGUSER",
    "{{ENV_PREFIX}}_PGPASSWORD": "PGPASSWORD",
    "{{ENV_PREFIX}}_PGDATABASE": "PGDATABASE",
}


def load_env_file(path: Path, env: dict[str, str]) -> bool:
    if not path.exists():
        return False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return True


def normalize_postgres_env(env: dict[str, str]) -> None:
    for source_key, target_key in ALIASES.items():
        source_value = env.get(source_key)
        if source_value and not env.get(target_key):
            env[target_key] = source_value
    for source_key, target_key in PSQL_ENV_ALIASES.items():
        source_value = env.get(source_key)
        if source_value and not env.get(target_key):
            env[target_key] = source_value


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / ".codex" / "mcp_servers" / "postgres_server.py"

    env = os.environ.copy()
    load_env_file(repo_root / ".codex" / "mcp.local.env", env) or load_env_file(
        repo_root / ".cursor" / "mcp.local.env", env
    )
    normalize_postgres_env(env)
    env["{{ENV_PREFIX}}_WORKSPACE"] = str(repo_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    os.chdir(str(repo_root))
    os.environ.update(env)
    sys.path.insert(0, str(target.parent))
    sys.argv = [str(target)]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
