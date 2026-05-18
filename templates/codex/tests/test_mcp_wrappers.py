from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = ROOT / ".codex" / "mcp_servers"
START_DIR = ROOT / ".codex"


def _has_server(stem: str) -> bool:
    return (MCP_DIR / f"{stem}.py").exists()


def _has_starter(stem: str) -> bool:
    return (START_DIR / f"start_{stem}_mcp.py").exists()


JIRA_INSTALLED = _has_server("jira_server") and (
    _has_starter("jira_production") or _has_starter("jira_preproduction")
)
POSTGRES_INSTALLED = _has_server("postgres_server") and _has_starter("postgres")
REALDATA_INSTALLED = _has_server("realdata_test_server") and _has_starter("realdata_test")
CODEBASE_INSTALLED = _has_server("codebase_server") and _has_starter("codebase")


def load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.path.insert(0, str(module_path.parent))
    previous_module = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module
        try:
            sys.path.remove(str(module_path.parent))
        except ValueError:
            pass
    return module


class TestCodexMcpWrappers(unittest.TestCase):

    class BinaryStdio:
        def __init__(self, data: bytes = b"") -> None:
            self.buffer = io.BytesIO(data)

    def test_config_example_uses_codex_safe_mcp_server_names(self):
        config_path = ROOT / ".codex" / "config.toml.example"
        raw_config = config_path.read_text(encoding="utf-8")
        server_names = re.findall(r"^\[mcp_servers\.([^\]]+)\]", raw_config, re.MULTILINE)

        self.assertTrue(server_names)
        for server_name in server_names:
            self.assertNotIn('"', server_name)
            self.assertRegex(server_name, r"^[a-zA-Z0-9_-]+$")

    def test_common_server_uses_jsonl_transport_for_codex_stdio(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "common.py"
        module = load_module(module_path, "test_common_server_jsonl")
        server = module.SimpleMcpServer("test_server", "0", [])
        request = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            + "\n"
        ).encode("utf-8")
        stdin = self.BinaryStdio(request)
        stdout = self.BinaryStdio()

        with patch.object(module.sys, "stdin", stdin):
            with patch.object(module.sys, "stdout", stdout):
                message = server._read_message()
                server._handle_message(message)

        self.assertEqual(server.transport_style, "jsonl")
        raw_output = stdout.buffer.getvalue()
        self.assertTrue(raw_output.endswith(b"\n"))
        self.assertEqual(json.loads(raw_output.decode("utf-8"))["id"], 1)

    def test_common_server_keeps_content_length_transport_compatibility(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "common.py"
        module = load_module(module_path, "test_common_server_headers")
        server = module.SimpleMcpServer("test_server", "0", [])
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        ).encode("utf-8")
        request = b"Content-Length: " + str(len(payload)).encode("ascii") + b"\r\n\r\n" + payload
        stdin = self.BinaryStdio(request)
        stdout = self.BinaryStdio()

        with patch.object(module.sys, "stdin", stdin):
            with patch.object(module.sys, "stdout", stdout):
                message = server._read_message()
                server._handle_message(message)

        self.assertEqual(server.transport_style, "headers")
        raw_output = stdout.buffer.getvalue()
        self.assertTrue(raw_output.startswith(b"Content-Length: "))

    def test_mcp_server_info_names_are_codex_safe(self):
        # Dynamic: only check the server files actually shipped with this preset.
        server_paths = sorted(MCP_DIR.glob("*_server.py"))
        self.assertTrue(server_paths, "no MCP server files found in .codex/mcp_servers/")
        for index, server_path in enumerate(server_paths):
            if server_path.name == "common.py":
                continue
            # JIRA server reads {{ENV_PREFIX}}_JIRA_SERVER_NAME at import time; provide a stub.
            previous = os.environ.get("{{ENV_PREFIX}}_JIRA_SERVER_NAME")
            if server_path.name == "jira_server.py":
                os.environ["{{ENV_PREFIX}}_JIRA_SERVER_NAME"] = "jira_test"
            try:
                module = load_module(server_path, f"test_mcp_server_name_{index}")
                self.assertRegex(module.SERVER.name, r"^[a-zA-Z0-9_-]+$")
            finally:
                if server_path.name == "jira_server.py":
                    if previous is None:
                        os.environ.pop("{{ENV_PREFIX}}_JIRA_SERVER_NAME", None)
                    else:
                        os.environ["{{ENV_PREFIX}}_JIRA_SERVER_NAME"] = previous

    def test_codebase_wrapper_sets_workspace_and_target(self):
        module_path = ROOT / ".codex" / "start_codebase_mcp.py"
        module = load_module(module_path, "test_start_codebase_mcp")
        expected_target = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"

        with patch.object(module.os, "chdir") as chdir_mock:
            with patch.object(module.runpy, "run_path", side_effect=SystemExit(17)) as run_mock:
                with self.assertRaises(SystemExit) as exc:
                    module.main()

        self.assertEqual(exc.exception.code, 17)
        chdir_mock.assert_called_once_with(str(ROOT))
        run_mock.assert_called_once_with(str(expected_target), run_name="__main__")
        self.assertEqual(module.sys.argv, [str(expected_target)])
        self.assertEqual(module.os.environ["{{ENV_PREFIX}}_WORKSPACE"], str(ROOT))
        self.assertEqual(module.os.environ["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(module.os.environ["PYTHONUTF8"], "1")
        self.assertEqual(module.os.environ["PYTHONDONTWRITEBYTECODE"], "1")

    @unittest.skipUnless(POSTGRES_INSTALLED, "postgres server not installed by this preset")
    def test_postgres_load_env_file_reads_key_values(self):
        module_path = ROOT / ".codex" / "start_postgres_mcp.py"
        module = load_module(module_path, "test_start_postgres_mcp_env")

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "mcp.local.env"
            env_file.write_text(
                "# comment\nPGHOST=127.0.0.1\nPGPORT=5433\nEMPTY=\n",
                encoding="utf-8",
            )
            env = {}
            loaded = module.load_env_file(env_file, env)

        self.assertTrue(loaded)
        self.assertEqual(
            env,
            {"PGHOST": "127.0.0.1", "PGPORT": "5433", "EMPTY": ""},
        )

    @unittest.skipUnless(POSTGRES_INSTALLED, "postgres server not installed by this preset")
    def test_postgres_normalize_env_maps_odoo_style_keys(self):
        module_path = ROOT / ".codex" / "start_postgres_mcp.py"
        module = load_module(module_path, "test_start_postgres_mcp_normalize")

        env = {
            "db_host": "localhost",
            "db_port": "5435",
            "db_user": "test_user",
            "db_password": "test_pw",
            "db_name": "test_db",
            "http_port": "12",
        }
        module.normalize_postgres_env(env)

        self.assertEqual(env["{{ENV_PREFIX}}_PGHOST"], "localhost")
        self.assertEqual(env["{{ENV_PREFIX}}_PGPORT"], "5435")
        self.assertEqual(env["{{ENV_PREFIX}}_PGUSER"], "test_user")
        self.assertEqual(env["{{ENV_PREFIX}}_PGPASSWORD"], "test_pw")
        self.assertEqual(env["{{ENV_PREFIX}}_PGDATABASE"], "test_db")
        self.assertEqual(env["{{ENV_PREFIX}}_HTTP_PORT"], "12")
        self.assertEqual(env["PGHOST"], "localhost")
        self.assertEqual(env["PGPORT"], "5435")
        self.assertEqual(env["PGUSER"], "test_user")
        self.assertEqual(env["PGPASSWORD"], "test_pw")
        self.assertEqual(env["PGDATABASE"], "test_db")

    @unittest.skipUnless(POSTGRES_INSTALLED, "postgres server not installed by this preset")
    def test_postgres_wrapper_prefers_codex_env_before_cursor_env(self):
        module_path = ROOT / ".codex" / "start_postgres_mcp.py"
        module = load_module(module_path, "test_start_postgres_mcp")
        expected_target = ROOT / ".codex" / "mcp_servers" / "postgres_server.py"
        codex_env = ROOT / ".codex" / "mcp.local.env"
        cursor_env = ROOT / ".cursor" / "mcp.local.env"
        calls = []

        def fake_load_env_file(path, env):
            calls.append(path)
            env["LOADED_FROM"] = path.name
            return path == codex_env

        with patch.object(module, "load_env_file", side_effect=fake_load_env_file):
            with patch.object(module.os, "chdir") as chdir_mock:
                with patch.object(module.runpy, "run_path", side_effect=SystemExit(0)) as run_mock:
                    with self.assertRaises(SystemExit) as exc:
                        module.main()

        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(calls, [codex_env])
        chdir_mock.assert_called_once_with(str(ROOT))
        run_mock.assert_called_once_with(str(expected_target), run_name="__main__")
        self.assertEqual(module.sys.argv, [str(expected_target)])
        self.assertEqual(module.os.environ["{{ENV_PREFIX}}_WORKSPACE"], str(ROOT))
        self.assertEqual(module.os.environ["LOADED_FROM"], "mcp.local.env")

    @unittest.skipUnless(POSTGRES_INSTALLED, "postgres server not installed by this preset")
    def test_postgres_wrapper_falls_back_to_cursor_env(self):
        module_path = ROOT / ".codex" / "start_postgres_mcp.py"
        module = load_module(module_path, "test_start_postgres_mcp_fallback")
        codex_env = ROOT / ".codex" / "mcp.local.env"
        cursor_env = ROOT / ".cursor" / "mcp.local.env"
        calls = []

        def fake_load_env_file(path, env):
            calls.append(path)
            return path == cursor_env

        with patch.object(module, "load_env_file", side_effect=fake_load_env_file):
            with patch.object(module.os, "chdir") as chdir_mock:
                with patch.object(module.runpy, "run_path", side_effect=SystemExit(0)):
                    with self.assertRaises(SystemExit):
                        module.main()

        chdir_mock.assert_called_once_with(str(ROOT))
        self.assertEqual(calls, [codex_env, cursor_env])

    @unittest.skipUnless(REALDATA_INSTALLED, "realdata_test server not installed by this preset")
    def test_realdata_test_wrapper_prefers_codex_env_before_cursor_env(self):
        module_path = ROOT / ".codex" / "start_realdata_test_mcp.py"
        module = load_module(module_path, "test_start_realdata_test_mcp")
        expected_target = ROOT / ".codex" / "mcp_servers" / "realdata_test_server.py"
        codex_env = ROOT / ".codex" / "mcp.local.env"
        calls = []

        def fake_load_env_file(path, env):
            calls.append(path)
            env["LOADED_FROM"] = path.name
            return path == codex_env

        with patch.object(module, "load_env_file", side_effect=fake_load_env_file):
            with patch.object(module.os, "chdir") as chdir_mock:
                with patch.object(module.runpy, "run_path", side_effect=SystemExit(0)) as run_mock:
                    with self.assertRaises(SystemExit) as exc:
                        module.main()

        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(calls, [codex_env])
        chdir_mock.assert_called_once_with(str(ROOT))
        run_mock.assert_called_once_with(str(expected_target), run_name="__main__")
        self.assertEqual(module.sys.argv, [str(expected_target)])
        self.assertEqual(module.os.environ["{{ENV_PREFIX}}_WORKSPACE"], str(ROOT))
        self.assertEqual(module.os.environ["LOADED_FROM"], "mcp.local.env")

    @unittest.skipUnless(JIRA_INSTALLED, "JIRA server not installed by this preset")
    def test_jira_wrapper_prefers_codex_env_before_cursor_env(self):
        module_path = ROOT / ".codex" / "start_jira_production_mcp.py"
        module = load_module(module_path, "test_start_jira_production_mcp")
        expected_target = ROOT / ".codex" / "mcp_servers" / "jira_server.py"
        codex_env = ROOT / ".codex" / "mcp.local.env"
        cursor_env = ROOT / ".cursor" / "mcp.local.env"
        calls = []

        def fake_load_env_file(path, env):
            calls.append(path)
            env["LOADED_FROM"] = path.name
            return path == codex_env

        with patch.object(module, "load_env_file", side_effect=fake_load_env_file):
            with patch.object(module.os, "chdir") as chdir_mock:
                with patch.object(module.runpy, "run_path", side_effect=SystemExit(0)) as run_mock:
                    with self.assertRaises(SystemExit) as exc:
                        module.main()

        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(calls, [codex_env])
        chdir_mock.assert_called_once_with(str(ROOT))
        run_mock.assert_called_once_with(str(expected_target), run_name="__main__")
        self.assertEqual(module.sys.argv, [str(expected_target)])
        self.assertEqual(module.os.environ["{{ENV_PREFIX}}_WORKSPACE"], str(ROOT))
        self.assertEqual(module.os.environ["LOADED_FROM"], "mcp.local.env")

    def test_codebase_resolve_path_supports_python38(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"
        module = load_module(module_path, "test_codebase_server")

        inside = module.resolve_path("nakivo")
        self.assertTrue(str(inside).startswith(str(ROOT)))

        with self.assertRaises(ValueError):
            module.resolve_path("..")

    @unittest.skipUnless(REALDATA_INSTALLED, "realdata_test server not installed by this preset")
    def test_realdata_test_builds_guarded_module_test_command(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "realdata_test_server.py"
        module = load_module(module_path, "test_realdata_test_server")

        command = module.module_test_command(
            {
                "database": "Nakivo01_staging",
                "module_name": "sale",
                "module_action": "update",
                "test_tag": "/sale",
            }
        )

        self.assertIn("--test-enable", command)
        self.assertIn("--stop-after-init", command)
        self.assertIn("-u", command)
        self.assertIn("sale", command)

        with self.assertRaises(ValueError):
            module.run_module_test(
                {"database": "Nakivo01_staging", "module_name": "sale"}
            )

    # --- New: JIRA multi-profile wrapper ----------------------------------

    @unittest.skipUnless(JIRA_INSTALLED, "JIRA server not installed by this preset")
    def test_jira_production_wrapper_maps_profile_env_to_generic_keys(self):
        module_path = ROOT / ".codex" / "start_jira_production_mcp.py"
        module = load_module(module_path, "test_start_jira_production_profile")

        env = {
            "{{ENV_PREFIX}}_JIRA_PRODUCTION_BASE_URL": "https://jira.example.test/",
            "{{ENV_PREFIX}}_JIRA_PRODUCTION_USER": "test.user",
            "{{ENV_PREFIX}}_JIRA_PRODUCTION_PASSWORD": "secret",
        }
        module.apply_profile(env)

        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_BASE_URL"], "https://jira.example.test/")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_USER"], "test.user")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_PASSWORD"], "secret")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_PROFILE"], "production")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_SERVER_NAME"], "jira_production")

    @unittest.skipUnless(JIRA_INSTALLED, "JIRA server not installed by this preset")
    def test_jira_preproduction_wrapper_maps_profile_env_to_generic_keys(self):
        module_path = ROOT / ".codex" / "start_jira_preproduction_mcp.py"
        module = load_module(module_path, "test_start_jira_preproduction_profile")

        env = {
            "{{ENV_PREFIX}}_JIRA_PREPRODUCTION_BASE_URL": "https://jira-staging.example.test/",
            "{{ENV_PREFIX}}_JIRA_PREPRODUCTION_USER": "test.user",
            "{{ENV_PREFIX}}_JIRA_PREPRODUCTION_PASSWORD": "secret",
        }
        module.apply_profile(env)

        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_BASE_URL"], "https://jira-staging.example.test/")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_USER"], "test.user")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_PASSWORD"], "secret")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_PROFILE"], "preproduction")
        self.assertEqual(env["{{ENV_PREFIX}}_JIRA_SERVER_NAME"], "jira_preproduction")

    @unittest.skipUnless(JIRA_INSTALLED, "JIRA server not installed by this preset")
    def test_jira_preproduction_wrapper_invokes_shared_jira_server(self):
        module_path = ROOT / ".codex" / "start_jira_preproduction_mcp.py"
        module = load_module(module_path, "test_start_jira_preproduction_run")
        expected_target = ROOT / ".codex" / "mcp_servers" / "jira_server.py"
        codex_env = ROOT / ".codex" / "mcp.local.env"
        calls = []

        def fake_load_env_file(path, env):
            calls.append(path)
            return path == codex_env

        with patch.object(module, "load_env_file", side_effect=fake_load_env_file):
            with patch.object(module.os, "chdir") as chdir_mock:
                with patch.object(module.runpy, "run_path", side_effect=SystemExit(0)) as run_mock:
                    with self.assertRaises(SystemExit):
                        module.main()

        self.assertEqual(calls, [codex_env])
        chdir_mock.assert_called_once_with(str(ROOT))
        run_mock.assert_called_once_with(str(expected_target), run_name="__main__")

    @unittest.skipUnless(JIRA_INSTALLED, "JIRA server not installed by this preset")
    def test_config_example_registers_preproduction_jira_server(self):
        config_path = ROOT / ".codex" / "config.toml.example"
        raw_config = config_path.read_text(encoding="utf-8")
        server_names = re.findall(r"^\[mcp_servers\.([^\]]+)\]", raw_config, re.MULTILINE)
        self.assertIn("jira_production", server_names)
        self.assertIn("jira_preproduction", server_names)

    @unittest.skipUnless(JIRA_INSTALLED, "JIRA server not installed by this preset")
    def test_jira_server_uses_profile_aware_name(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "jira_server.py"
        previous = {key: os.environ.get(key) for key in (
            "{{ENV_PREFIX}}_JIRA_PROFILE",
            "{{ENV_PREFIX}}_JIRA_SERVER_NAME",
            "{{ENV_PREFIX}}_JIRA_BASE_URL",
            "{{ENV_PREFIX}}_JIRA_USER",
            "{{ENV_PREFIX}}_JIRA_PASSWORD",
        )}
        try:
            os.environ["{{ENV_PREFIX}}_JIRA_PROFILE"] = "preproduction"
            os.environ.pop("{{ENV_PREFIX}}_JIRA_SERVER_NAME", None)
            os.environ["{{ENV_PREFIX}}_JIRA_BASE_URL"] = "https://jira-staging.example.test/"
            os.environ["{{ENV_PREFIX}}_JIRA_USER"] = "test.user"
            os.environ["{{ENV_PREFIX}}_JIRA_PASSWORD"] = "stub"
            module = load_module(module_path, "test_jira_server_profile_aware")
            self.assertEqual(module.SERVER.name, "jira_preproduction")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    # --- New: ORM eval sandbox (read-only guarantee) -----------------------

    @unittest.skipUnless(REALDATA_INSTALLED, "realdata_test server not installed by this preset")
    def test_realdata_test_orm_eval_rejects_mutation_tokens(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "realdata_test_server.py"
        module = load_module(module_path, "test_realdata_orm_sandbox")

        forbidden_examples = [
            "env['sale.order'].create({})",
            "env['sale.order'].search([]).write({'name': 'x'})",
            "env['sale.order'].browse(1).unlink()",
            "env.cr.execute('SELECT 1')",
            "x = env['sale.order']",
            "import os",
            "env['sale.order'].sudo().search_count([])",
            "env['sale.order'].search([])\nenv.cr.commit()",
            "env.__dict__",
        ]
        for expression in forbidden_examples:
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    module.ensure_readonly_expression(expression)

    @unittest.skipUnless(REALDATA_INSTALLED, "realdata_test server not installed by this preset")
    def test_realdata_test_orm_eval_accepts_readonly_expression(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "realdata_test_server.py"
        module = load_module(module_path, "test_realdata_orm_sandbox_ok")

        accepted = "env['sale.order'].search_count([('state','in',['sale','done'])])"
        self.assertEqual(module.ensure_readonly_expression(accepted), accepted)

    @unittest.skipUnless(REALDATA_INSTALLED, "realdata_test server not installed by this preset")
    def test_realdata_test_orm_fingerprint_is_stable(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "realdata_test_server.py"
        module = load_module(module_path, "test_realdata_fingerprint")

        a = module.fingerprint([{"id": 1, "x": 2}, {"id": 2, "x": 3}])
        b = module.fingerprint([{"x": 2, "id": 1}, {"x": 3, "id": 2}])
        self.assertEqual(a, b)
        self.assertNotEqual(a, module.fingerprint([{"id": 1, "x": 999}]))

    # --- New: Canonical decisions registry ---------------------------------

    def test_codebase_canonical_registry_loads_required_topics(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"
        module = load_module(module_path, "test_codebase_canonical")

        registry = module.load_canonical_registry()
        topics = {decision.get("topic") for decision in registry.get("decisions") or []}
        # Stack-agnostic topics required for every preset.
        required_always = {
            "stack",
            "addon roots",
            "verification",
            "mcp routing",
            "determinism",
            "module agnostic",
            "response language",
        }
        # Odoo-specific topics only when the postgres+realdata pair is installed
        # (proxy for an Odoo-like stack — they ship together in odoo-* presets).
        if POSTGRES_INSTALLED and REALDATA_INSTALLED:
            required_always |= {"api decorators", "loop anti-patterns", "sudo"}
        # JIRA topic only when the JIRA server is installed.
        if JIRA_INSTALLED:
            required_always |= {"jira"}
        for required in required_always:
            self.assertIn(required, topics, f"missing canonical topic: {required}")

    def test_codebase_lookup_canonical_decision_finds_match_by_alias(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"
        module = load_module(module_path, "test_codebase_lookup_alias")

        # "consistency" is an alias of the `determinism` decision.
        result = module.lookup_canonical_decision({"topic": "consistency"})
        self.assertGreaterEqual(result["match_count"], 1)
        self.assertTrue(any("determinism" == m.get("topic") for m in result["matches"]))

    def test_codebase_lookup_canonical_decision_requires_topic(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"
        module = load_module(module_path, "test_codebase_lookup_required")
        with self.assertRaises(ValueError):
            module.lookup_canonical_decision({})

    def test_codebase_canonical_decisions_are_deterministic_across_calls(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"
        module = load_module(module_path, "test_codebase_lookup_determinism")

        first = module.lookup_canonical_decision({"topic": "verification"})
        second = module.lookup_canonical_decision({"topic": "verification"})
        self.assertEqual(first, second)

    # --- New: Module-agnostic helpers --------------------------------------

    def test_codebase_module_dependencies_rejects_unknown_module(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"
        module = load_module(module_path, "test_codebase_module_deps")
        with self.assertRaises(ValueError):
            module.module_dependencies({"module": "definitely_not_a_real_module_xyz"})

    def test_codebase_find_inheritance_chain_requires_model(self):
        module_path = ROOT / ".codex" / "mcp_servers" / "codebase_server.py"
        module = load_module(module_path, "test_codebase_inherit_required")
        with self.assertRaises(ValueError):
            module.find_inheritance_chain({"model": ""})


if __name__ == "__main__":
    unittest.main()
