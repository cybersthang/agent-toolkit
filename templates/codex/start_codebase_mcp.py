from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = repo_root / ".codex" / "mcp_servers" / "codebase_server.py"

    env = os.environ.copy()
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
