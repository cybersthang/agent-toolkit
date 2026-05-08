---
name: Project Python is the venv {{STACK_LANGUAGE_VERSION}} — never the system Python
description: All MCP servers, framework runs, and tests must use {{PYTHON_BIN}}, not a system-PATH `python`.
type: feedback
---
The project Python interpreter is `{{PYTHON_BIN}}` (Python {{STACK_LANGUAGE_VERSION}}). Every script, MCP wrapper, framework invocation, and test runner must use this binary explicitly. A bare `python` resolved through PATH is forbidden because it can pick up a system Python that lacks the project dependencies and silently diverges from the runtime.

**Why:** Past incidents have shown `python -m unittest` resolving to the wrong interpreter via PATH; even when the version number matched, the package set differed. Pinning the venv binary makes runs reproducible.

**How to apply:**
- Bash/PowerShell: invoke `"{{PYTHON_BIN}}"` explicitly, never bare `python`.
- `.codex/mcp.local.env` exports the venv binary; new wrappers should consume it.
- `.codex/config.toml.example` pins `command = '{{PYTHON_BIN}}'` for every MCP server.
- Use `.codex/tests/run_all_tests.py` — it re-execs itself under the venv if invoked with the wrong interpreter.
- The canonical registry should have a `python-bin` entry so the answer to "which Python do we use?" is byte-stable across conversations.
