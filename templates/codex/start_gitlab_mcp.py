from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


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


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / ".codex" / "mcp_servers" / "gitlab_server.py"

    env = os.environ.copy()
    load_env_file(repo_root / ".codex" / "mcp.local.env", env) or load_env_file(
        repo_root / ".cursor" / "mcp.local.env", env
    )
    env["{{ENV_PREFIX}}_GITLAB_SERVER_NAME"] = (
        env.get("{{ENV_PREFIX}}_GITLAB_SERVER_NAME") or "gitlab"
    )
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
