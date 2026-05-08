from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


PROFILE = "preproduction"
PROFILE_ALIASES = {
    "NAKIVO_JIRA_PREPRODUCTION_BASE_URL": "NAKIVO_JIRA_BASE_URL",
    "NAKIVO_JIRA_PREPRODUCTION_USER": "NAKIVO_JIRA_USER",
    "NAKIVO_JIRA_PREPRODUCTION_PASSWORD": "NAKIVO_JIRA_PASSWORD",
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


def apply_profile(env: dict[str, str]) -> None:
    for source_key, target_key in PROFILE_ALIASES.items():
        source_value = env.get(source_key)
        if source_value:
            env[target_key] = source_value
    env["NAKIVO_JIRA_PROFILE"] = PROFILE
    env["NAKIVO_JIRA_SERVER_NAME"] = f"jira_{PROFILE}"


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / ".codex" / "mcp_servers" / "jira_server.py"

    env = os.environ.copy()
    load_env_file(repo_root / ".codex" / "mcp.local.env", env) or load_env_file(
        repo_root / ".cursor" / "mcp.local.env", env
    )
    apply_profile(env)
    env["NAKIVO_WORKSPACE"] = str(repo_root)
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
