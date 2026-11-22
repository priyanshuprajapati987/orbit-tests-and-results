"""Deep coverage tests for orbit/orbit/tools/mcp_tool.py (652 lines).

Targets the uncovered lines: MCPClient start/send/call/stop paths,
MCPManager config loading (env/cwd/app_root fallbacks, validation,
parse errors, partial start), _TokenBucket refill, _NonceTracker replay
window, ORBITMCPServer policy checks, request validation dispatch, and a
real localhost HTTP integration pass over the MCP endpoint (auth, rate
limit, CORS, body limits, OPTIONS).
"""

import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.orbit.tools import mcp_tool as mt  # noqa: E402


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class McpBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def make_client(self, **kw):
        return mt.MCPClient(kw.pop("name", "srv"), kw.pop("command", "cmd"),
                            kw.pop("args", []), **kw)


# ---------------------------------------------------------------------------
# MCPClient (47-165)
# ---------------------------------------------------------------------------


class TestMCPClient(McpBase):
    def test_init_defaults(self):
        c = self.make_client(cwd=None, env={"FOO": "bar"})
        self.assertEqual(c.name, "srv")
        self.assertEqual(c.cwd, str(Path.cwd()))
        self.assertIn("FOO", c.env)
        self.assertIn("PATH", c.env)  # inherits os.environ
        self.assertFalse(c.available)
        self.assertEqual(c.list_tools(), [])

    def test_start_success(self):
        c = self.make_client()
        fake_proc = MagicMock(name="proc")
        with patch.object(mt.subprocess, "Popen",
                          return_value=fake_proc) as popen, \
             patch.object(c, "_discover_tools") as disc, \
             self.assertLogs(mt.logger, level="INFO") as cm:
            ok = c.start()
        self.assertTrue(ok)
        self.assertTrue(c.available)
        disc.assert_called_once()
        popen.assert_called_once()
        self.assertTrue(any("started" in l for l in cm.output))

    def test_start_command_not_found(self):
        c = self.make_client(command="definitely-not-a-real-bin-xyz")
        with self.assertLogs(mt.logger, level="WARNING") as cm:
            ok = c.start()
        self.assertFalse(ok)
        self.assertFalse(c.available)
        self.assertTrue(any("not found" in l for l in cm.output))

    def test_start_generic_failure(self):
        c = self.make_client()
        with patch.object(mt.subprocess, "Popen",
                          side_effect=RuntimeError("spawn denied")), \
             self.assertLogs(mt.logger, level="ERROR") as cm:
            ok = c.start()
        self.assertFalse(ok)
        self.assertTrue(any("failed to start" in l for l in cm.output))

    def test_discover_tools_populates_cache(self):
        c = self.make_client()
        resp = {"result": {"tools": [{"name": "a"}, {"name": "b"}]}}
        with patch.object(c, "_send", return_value=resp):
            c._discover_tools()
        self.assertEqual(len(c.list_tools()), 2)

    def test_discover_tools_no_result_leaves_cache(self):
        c = self.make_client()
        c._tools_cache = [{"name": "keep"}]
        with patch.object(c, "_send", return_value=None):
            c._discover_tools()
        self.assertEqual(c.list_tools(), [{"name": "keep"}])

    def test_send_no_process_returns_none(self):
        c = self.make_client()
        self.assertIsNone(c._send("{}"))

    def test_send_no_stdin_returns_none(self):
        c = self.make_client()
        c._process = SimpleNamespace(stdin=None)
        self.assertIsNone(c._send("{}"))

    def test_send_success_roundtrip(self):
        c = self.make_client()
        line = json.dumps({"result": {"ok": True}})
        c._process = SimpleNamespace(
            stdin=MagicMock(),
            stdout=SimpleNamespace(readline=lambda: line),
        )
        out = c._send('{"jsonrpc":"2.0"}')
        self.assertEqual(out, {"result": {"ok": True}})
        c._process.stdin.write.assert_called_once()
        self.assertTrue(c._process.stdin.write.call_args.args[0].endswith("\n"))
        c._process.stdin.flush.assert_called_once()

    def test_send_write_error_returns_none(self):
        c = self.make_client()
        stdin = MagicMock()
        stdin.write.side_effect = OSError("broken pipe")
        c._process = SimpleNamespace(stdin=stdin, stdout=MagicMock())
        with self.assertLogs(mt.logger, level="ERROR") as cm:
            self.assertIsNone(c._send("{}"))
        self.assertTrue(any("MCP send error" in l for l in cm.output))

    def test_send_read_error_returns_none(self):
        c = self.make_client()

        class BadOut:
            def readline(self):
                raise RuntimeError("stdout died")

        c._process = SimpleNamespace(stdin=MagicMock(),
                                     stdout=BadOut())
        # _read swallows the exception -> empty result -> None (no raise)
        self.assertIsNone(c._send("{}"))

    def test_send_empty_line_returns_none(self):
        c = self.make_client()
        c._process = SimpleNamespace(
            stdin=MagicMock(),
            stdout=SimpleNamespace(readline=lambda: ""),
        )
        self.assertIsNone(c._send("{}"))

    def test_send_read_timeout_returns_none(self):
        c = self.make_client()
        c._process = SimpleNamespace(stdin=MagicMock(),
                                     stdout=MagicMock())
        # Thread that never completes -> is_alive() True after join
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        with patch.object(mt.threading, "Thread", return_value=fake_thread), \
             self.assertLogs(mt.logger, level="ERROR") as cm:
            self.assertIsNone(c._send("{}"))
        fake_thread.join.assert_called_once_with(timeout=10)
        self.assertTrue(any("read timeout" in l for l in cm.output))

    def test_call_tool_success(self):
        c = self.make_client()
        with patch.object(c, "_send",
                          return_value={"result": {"content": []}}) as send:
            out = c.call_tool("do_thing", {"x": 1})
        self.assertEqual(out, {"content": []})
        payload = json.loads(send.call_args.args[0])
        self.assertEqual(payload["method"], "tools/call")
        self.assertEqual(payload["params"],
                         {"name": "do_thing", "arguments": {"x": 1}})

    def test_call_tool_error_response(self):
        c = self.make_client()
        with patch.object(c, "_send",
                          return_value={"error": {"message": "boom"}}):
            out = c.call_tool("do_thing")
        self.assertTrue(out["isError"])
        self.assertIn("boom", out["content"][0]["text"])

    def test_call_tool_no_response(self):
        c = self.make_client()
        with patch.object(c, "_send", return_value=None):
            out = c.call_tool("do_thing")
        self.assertTrue(out["isError"])
        self.assertEqual(out["content"][0]["text"],
                         "No response from MCP server")

    def test_stop_terminates(self):
        c = self.make_client()
        proc = MagicMock()
        c._process = proc
        c._available = True
        c.stop()
        self.assertFalse(c.available)
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5)
        self.assertIsNone(c._process)

    def test_stop_kill_fallback_when_terminate_fails(self):
        c = self.make_client()
        proc = MagicMock()
        proc.terminate.side_effect = OSError("already dead")
        c._process = proc
        c.stop()
        proc.kill.assert_called_once()
        self.assertIsNone(c._process)

    def test_stop_without_process(self):
        c = self.make_client()
        c._available = True
        c.stop()  # must not raise
        self.assertFalse(c.available)

    def test_get_status(self):
        c = self.make_client()
        c._tools_cache = [{"name": "alpha"}, {"name": "beta"}]
        c._available = True
        st = c.get_status()
        self.assertEqual(st["name"], "srv")
        self.assertTrue(st["available"])
        self.assertEqual(st["tools"], 2)
        self.assertEqual(st["tool_names"], ["alpha", "beta"])


# ---------------------------------------------------------------------------
# MCPManager (171-291)
# ---------------------------------------------------------------------------


class TestMCPManager(McpBase):
    def test_load_config_from_env(self):
        mgr = mt.MCPManager()
        cfg = self.dir / "env.json"
        cfg.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        with patch.dict(os.environ, {"MCP_CONFIG_PATH": str(cfg)}):
            self.assertEqual(mgr.load_config(), 0)

    def test_load_config_cwd_fallback(self):
        mgr = mt.MCPManager()
        (self.dir / ".mcp.json").write_text(
            json.dumps({"mcpServers": {}}), encoding="utf-8")
        with patch.dict(os.environ, {"MCP_CONFIG_PATH": ""}), \
             patch.object(mt.Path, "cwd", return_value=self.dir):
            self.assertEqual(mgr.load_config(), 0)

    def test_load_config_app_root_fallback(self):
        mgr = mt.MCPManager()
        empty = self.dir / "empty"
        empty.mkdir()
        root = self.dir / "root"
        root.mkdir()
        (root / ".mcp.json").write_text(
            json.dumps({"mcpServers": {}}), encoding="utf-8")
        with patch.dict(os.environ, {"MCP_CONFIG_PATH": ""}), \
             patch.object(mt.Path, "cwd", return_value=empty), \
             patch.object(mt, "app_root", return_value=root):
            self.assertEqual(mgr.load_config(), 0)

    def test_load_config_blocked_extension_returns_zero(self):
        mgr = mt.MCPManager()
        bad = self.dir / "config.txt"
        bad.write_text("{}", encoding="utf-8")
        self.assertEqual(mgr.load_config(str(bad)), 0)

    def test_load_config_system_dir_blocked(self):
        mgr = mt.MCPManager()
        if os.name == "nt":
            target = "C:/Windows/system32/evil.json"
        else:
            target = "/etc/evil.json"
        self.assertEqual(mgr.load_config(target), 0)

    def test_load_config_invalid_path_returns_zero(self):
        mgr = mt.MCPManager()
        with self.assertLogs(mt.logger, level="ERROR") as cm:
            out = mgr.load_config("\x00bad.json")
        self.assertEqual(out, 0)
        self.assertTrue(any("MCP-006" in l for l in cm.output))

    def test_load_config_missing_file(self):
        mgr = mt.MCPManager()
        with self.assertLogs(mt.logger, level="WARNING") as cm:
            out = mgr.load_config(str(self.dir / "nope.json"))
        self.assertEqual(out, 0)
        self.assertTrue(any("not found" in l for l in cm.output))

    def test_load_config_corrupt_json(self):
        cfg = self.dir / "bad.json"
        cfg.write_text("{oops", encoding="utf-8")
        mgr = mt.MCPManager()
        with self.assertLogs(mt.logger, level="ERROR") as cm:
            out = mgr.load_config(str(cfg))
        self.assertEqual(out, 0)
        self.assertTrue(any("Failed to load MCP config" in l
                            for l in cm.output))

    def test_load_config_partial_start(self):
        cfg = self.dir / "servers.json"
        cfg.write_text(json.dumps({"mcpServers": {
            "a": {"command": "python", "args": ["-V"]},
            "b": {"command": "python", "args": ["-V"]},
        }}), encoding="utf-8")
        mgr = mt.MCPManager()
        results = iter([True, False])
        # class-level patch: MagicMock doesn't bind self, so accept *args
        with patch.object(mt.MCPClient, "start",
                          side_effect=lambda *a: next(results)), \
             self.assertLogs(mt.logger, level="INFO") as cm:
            started = mgr.load_config(str(cfg))
        self.assertEqual(started, 1)
        self.assertIn("1/2 servers started", "\n".join(cm.output))
        self.assertEqual(len(mgr._clients), 1)

    def test_list_tools_aggregates_clients(self):
        mgr = mt.MCPManager()
        c1 = MagicMock()
        c1.name = "s1"
        c1.list_tools.return_value = [
            {"name": "t1", "description": "d1", "inputSchema": {"k": "v"}}]
        c2 = MagicMock()
        c2.name = "s2"
        c2.list_tools.return_value = [{"name": "t2"}]
        mgr._clients = {"s1": c1, "s2": c2}
        tools = mgr.list_tools()
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]["server"], "s1")
        self.assertEqual(tools[0]["description"], "d1")
        self.assertEqual(tools[1]["description"], "")  # default
        self.assertEqual(tools[1]["inputSchema"], {})

    def test_call_tool_found_routes_to_client(self):
        mgr = mt.MCPManager()
        c = MagicMock()
        c.list_tools.return_value = [{"name": "magic"}]
        c.call_tool.return_value = {"ok": True}
        mgr._clients = {"s": c}
        out = mgr.call_tool("magic", {"a": 1})
        self.assertEqual(out, {"ok": True})
        c.call_tool.assert_called_once_with("magic", {"a": 1})

    def test_call_tool_not_found(self):
        mgr = mt.MCPManager()
        c = MagicMock()
        c.list_tools.return_value = []
        mgr._clients = {"s": c}
        out = mgr.call_tool("ghost")
        self.assertTrue(out["isError"])
        self.assertIn("not found", out["content"][0]["text"])

    def test_get_status(self):
        mgr = mt.MCPManager()
        c = MagicMock()
        c.get_status.return_value = {"name": "s"}
        mgr._clients = {"s": c}
        self.assertEqual(mgr.get_status(), [{"name": "s"}])

    def test_stop_all_with_server(self):
        mgr = mt.MCPManager()
        c = MagicMock()
        mgr._clients = {"s": c}
        srv = MagicMock()
        mgr._server = srv
        mgr.stop_all()
        c.stop.assert_called_once()
        srv.stop.assert_called_once()
        self.assertEqual(mgr._clients, {})

    def test_stop_all_without_server(self):
        mgr = mt.MCPManager()
        c = MagicMock()
        mgr._clients = {"s": c}
        mgr._server = None
        mgr.stop_all()
        c.stop.assert_called_once()


# ---------------------------------------------------------------------------
# _TokenBucket (297-318) + _NonceTracker (324-348)
# ---------------------------------------------------------------------------


class TestRateLimitAndNonce(McpBase):
    def test_bucket_allows_up_to_max_then_denies(self):
        b = mt._TokenBucket(max_tokens=2, refill_interval=1000)
        self.assertTrue(b.allow("ip"))
        self.assertTrue(b.allow("ip"))
        self.assertFalse(b.allow("ip"))  # empty bucket

    def test_bucket_refills_over_time(self):
        b = mt._TokenBucket(max_tokens=2, refill_interval=100)
        b.allow("ip")
        b.allow("ip")
        self.assertFalse(b.allow("ip"))
        # 50s elapsed -> 50 * (2/100) = 1 token back
        b._last_refill["ip"] -= 50
        self.assertTrue(b.allow("ip"))

    def test_bucket_refill_caps_at_max(self):
        b = mt._TokenBucket(max_tokens=2, refill_interval=100)
        b.allow("ip")
        b._last_refill["ip"] -= 10_000  # huge elapsed
        self.assertTrue(b.allow("ip"))
        self.assertTrue(b.allow("ip"))
        self.assertLessEqual(b._tokens["ip"], b.max_tokens)

    def test_bucket_separate_keys(self):
        b = mt._TokenBucket(max_tokens=1, refill_interval=1000)
        self.assertTrue(b.allow("a"))
        self.assertFalse(b.allow("a"))
        self.assertTrue(b.allow("b"))  # independent bucket

    def test_nonce_valid(self):
        n = mt._NonceTracker(tolerance=300)
        import time
        self.assertTrue(n.validate("nonce-1", time.time(), "secret"))

    def test_nonce_stale_timestamp_rejected(self):
        n = mt._NonceTracker(tolerance=300)
        import time
        with self.assertLogs(mt.logger, level="WARNING") as cm:
            ok = n.validate("nonce-2", time.time() - 1000, "secret")
        self.assertFalse(ok)
        self.assertTrue(any("outside tolerance" in l for l in cm.output))

    def test_nonce_future_timestamp_rejected(self):
        n = mt._NonceTracker(tolerance=300)
        import time
        self.assertFalse(n.validate("nonce-3", time.time() + 1000, "secret"))

    def test_nonce_replay_rejected(self):
        n = mt._NonceTracker(tolerance=300)
        import time
        now = time.time()
        self.assertTrue(n.validate("replay-me", now, "secret"))
        with self.assertLogs(mt.logger, level="WARNING") as cm:
            self.assertFalse(n.validate("replay-me", now, "secret"))
        self.assertTrue(any("Replay detected" in l for l in cm.output))

    def test_nonce_prunes_old_entries(self):
        import time
        n = mt._NonceTracker(tolerance=300)
        now = time.time()
        n._seen["ancient"] = now - (300 * 2) - 100  # beyond prune cutoff
        self.assertTrue(n.validate("fresh", now, "secret"))
        self.assertNotIn("ancient", n._seen)
        self.assertIn("fresh", n._seen)


# ---------------------------------------------------------------------------
# ORBITMCPServer policy (377-437)
# ---------------------------------------------------------------------------


class TestPolicyChecks(McpBase):
    def make_server(self, **kw):
        kw.setdefault("require_auth", False)
        return mt.ORBITMCPServer(**kw)

    def test_get_policy_engine_success(self):
        srv = self.make_server()
        engine = MagicMock(name="engine")
        with patch("orbit.orbit.core.policy_engine.get_policy_engine",
                   return_value=engine):
            self.assertIs(srv._get_policy_engine(), engine)
            self.assertIs(srv._get_policy_engine(), engine)  # cached

    def test_get_policy_engine_failure(self):
        srv = self.make_server()
        with patch("orbit.orbit.core.policy_engine.get_policy_engine",
                   side_effect=ImportError("no policy")), \
             self.assertLogs(mt.logger, level="WARNING") as cm:
            self.assertIsNone(srv._get_policy_engine())
        self.assertTrue(any("PolicyEngine not available" in l
                            for l in cm.output))

    def test_check_policy_engine_unavailable_blocks(self):
        srv = self.make_server()
        with patch.object(srv, "_get_policy_engine", return_value=None), \
             self.assertLogs(mt.logger, level="WARNING") as cm:
            err = srv._check_policy("web_search", {})
        self.assertIsNotNone(err)
        self.assertIn("blocked", err)
        self.assertTrue(any("fail-closed" in l for l in cm.output))

    def test_check_policy_risk_tiers_all_reach_engine(self):
        srv = self.make_server()
        engine = MagicMock()
        engine.check_path.return_value = SimpleNamespace(allowed=True,
                                                         reason="")
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: False)):
            for tool in ("file_tools",   # high risk
                         "web_search",   # low risk
                         "n8n"):         # else branch
                with self.subTest(tool=tool):
                    args = {"path": "x.txt"} if tool == "file_tools" else {}
                    self.assertIsNone(srv._check_policy(tool, args))

    def test_check_policy_kill_switch_active(self):
        srv = self.make_server()
        engine = MagicMock()
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: True)):
            err = srv._check_policy("web_search", {})
        self.assertIn("Kill switch", err)

    def test_check_policy_kill_switch_import_failure_ignored(self):
        srv = self.make_server()
        engine = MagicMock()
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   side_effect=ImportError("missing")):
            self.assertIsNone(srv._check_policy("n8n", {}))  # pass-through

    def test_check_policy_file_path_blocked(self):
        srv = self.make_server()
        engine = MagicMock()
        engine.check_path.return_value = SimpleNamespace(
            allowed=False, reason="outside workspace")
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: False)):
            err = srv._check_policy("file_tools", {"path": "/etc/passwd"})
        self.assertIn("ToolGate blocked", err)

    def test_check_policy_file_path_check_exception_ignored(self):
        srv = self.make_server()
        engine = MagicMock()
        engine.check_path.side_effect = RuntimeError("checker crashed")
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: False)):
            self.assertIsNone(srv._check_policy("file_tools",
                                                {"path": "ok.txt"}))

    def test_check_policy_non_string_path_skipped(self):
        srv = self.make_server()
        engine = MagicMock()
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: False)):
            self.assertIsNone(srv._check_policy("file_tools",
                                                {"path": 12345}))
        engine.check_path.assert_not_called()

    def test_check_policy_dangerous_command_blocked(self):
        srv = self.make_server()
        engine = MagicMock()
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: False)):
            err = srv._check_policy("computer",
                                    {"action": "run_command",
                                     "command": "rm -rf /"})
        self.assertIn("dangerous command", err)

    def test_check_policy_safe_command_allowed(self):
        srv = self.make_server()
        engine = MagicMock()
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: False)):
            err = srv._check_policy("computer",
                                    {"action": "run_command",
                                     "command": "dir"})
        self.assertIsNone(err)

    def test_check_policy_non_string_command_skipped(self):
        srv = self.make_server()
        engine = MagicMock()
        with patch.object(srv, "_get_policy_engine", return_value=engine), \
             patch("orbit.orbit.core.kill_switch.get_kill_switch",
                   return_value=SimpleNamespace(is_active=lambda: False)):
            self.assertIsNone(srv._check_policy("computer",
                                                {"action": "run_command",
                                                 "command": 999}))


# ---------------------------------------------------------------------------
# ORBITMCPServer register/start/stop (439-462, 636-637)
# ---------------------------------------------------------------------------


class TestServerLifecycle(McpBase):
    def test_register_orbit_tools(self):
        srv = mt.ORBITMCPServer(require_auth=False)
        srv._register_orbit_tools()
        expected = {"web_search", "file_tools", "computer", "news",
                    "security", "n8n", "email", "calendar"}
        self.assertEqual(set(srv._tools), expected)

    def test_start_spawns_thread(self):
        srv = mt.ORBITMCPServer(require_auth=False)
        fake_thread = MagicMock(name="thread")
        with patch.object(srv, "_register_orbit_tools") as reg, \
             patch.object(mt.threading, "Thread",
                          return_value=fake_thread), \
             self.assertLogs(mt.logger, level="INFO") as cm:
            srv.start()
        reg.assert_called_once()
        self.assertTrue(srv._running)
        fake_thread.start.assert_called_once()
        self.assertTrue(any("listening" in l for l in cm.output))
        srv.stop()

    def test_stop_clears_running(self):
        srv = mt.ORBITMCPServer(require_auth=False)
        srv._running = True
        srv.stop()
        self.assertFalse(srv._running)


# ---------------------------------------------------------------------------
# _handle_request dispatch (560-634)
# ---------------------------------------------------------------------------


class TestHandleRequest(McpBase):
    def make_server(self):
        srv = mt.ORBITMCPServer(require_auth=False)
        srv._tools = {}
        return srv

    def test_non_dict_request_rejected(self):
        srv = self.make_server()
        out = srv._handle_request(["not", "a", "dict"])
        self.assertEqual(out["error"]["code"], -32600)
        self.assertIsNone(out["id"])

    def test_tools_list(self):
        srv = self.make_server()
        tool = SimpleNamespace(description="Does a thing")
        srv._tools = {"alpha": tool, "beta": object()}
        out = srv._handle_request({"method": "tools/list", "id": 7})
        self.assertEqual(out["id"], 7)
        names = [t["name"] for t in out["result"]["tools"]]
        self.assertEqual(names, ["alpha", "beta"])
        self.assertEqual(out["result"]["tools"][0]["description"],
                         "Does a thing")
        self.assertEqual(out["result"]["tools"][1]["description"], "beta")

    def test_resources_list(self):
        srv = self.make_server()
        out = srv._handle_request({"method": "resources/list", "id": 1})
        self.assertEqual(out["result"], {"resources": []})

    def test_unknown_method_returns_empty_result(self):
        srv = self.make_server()
        out = srv._handle_request({"method": "bogus/method", "id": 2})
        self.assertEqual(out["result"], {})
        self.assertEqual(out["id"], 2)

    def test_call_params_must_be_dict(self):
        srv = self.make_server()
        out = srv._handle_request({"method": "tools/call",
                                   "params": ["bad"], "id": 3})
        self.assertEqual(out["error"]["code"], -32602)

    def test_call_tool_name_invalid(self):
        srv = self.make_server()
        for bad in ("", 123, None):
            with self.subTest(name=bad):
                out = srv._handle_request({
                    "method": "tools/call",
                    "params": {"name": bad, "arguments": {}},
                    "id": 4,
                })
                self.assertEqual(out["error"]["code"], -32602)

    def test_call_tool_name_too_long(self):
        srv = self.make_server()
        out = srv._handle_request({
            "method": "tools/call",
            "params": {"name": "x" * 257, "arguments": {}},
            "id": 5,
        })
        self.assertEqual(out["error"]["code"], -32602)
        self.assertIn("too long", out["error"]["message"])

    def test_call_arguments_must_be_dict(self):
        srv = self.make_server()
        out = srv._handle_request({
            "method": "tools/call",
            "params": {"name": "t", "arguments": "not-a-dict"},
            "id": 6,
        })
        self.assertEqual(out["error"]["code"], -32602)

    def test_call_argument_string_too_long(self):
        srv = self.make_server()
        out = srv._handle_request({
            "method": "tools/call",
            "params": {"name": "t",
                       "arguments": {"blob": "x" * (mt.MAX_ARG_STRING_LEN + 1)}},
            "id": 7,
        })
        self.assertEqual(out["error"]["code"], -32602)
        self.assertIn("exceeds max length", out["error"]["message"])

    def test_call_policy_blocked(self):
        srv = self.make_server()
        srv._tools = {"t": MagicMock()}
        with patch.object(srv, "_check_policy",
                          return_value="nope — blocked") as cp:
            out = srv._handle_request({"method": "tools/call",
                                       "params": {"name": "t",
                                                  "arguments": {}},
                                       "id": 8})
        cp.assert_called_once_with("t", {})
        self.assertEqual(out["error"]["code"], -32001)

    def test_call_unknown_tool(self):
        srv = self.make_server()
        with patch.object(srv, "_check_policy", return_value=None):
            out = srv._handle_request({"method": "tools/call",
                                       "params": {"name": "ghost",
                                                  "arguments": {}},
                                       "id": 9})
        self.assertEqual(out["error"]["code"], -32601)

    def test_call_dispatches_to_search(self):
        srv = self.make_server()
        tool = MagicMock(spec=["search"])
        tool.search.return_value = {"hits": 1}
        srv._tools = {"s": tool}
        with patch.object(srv, "_check_policy", return_value=None):
            out = srv._handle_request({"method": "tools/call",
                                       "params": {"name": "s",
                                                  "arguments": {"q": "x"}},
                                       "id": 10})
        tool.search.assert_called_once_with(q="x")
        self.assertIn("hits", out["result"]["content"][0]["text"])

    def test_call_dispatches_to_handle_natural(self):
        srv = self.make_server()

        class NaturalTool:
            def handle_natural(self, text):
                return f"handled: {text}"

        srv._tools = {"n": NaturalTool()}
        with patch.object(srv, "_check_policy", return_value=None):
            out = srv._handle_request({"method": "tools/call",
                                       "params": {"name": "n",
                                                  "arguments": {
                                                      "text": "hello"}},
                                       "id": 11})
        self.assertEqual(out["result"]["content"][0]["text"],
                         "handled: hello")

    def test_call_dispatches_to_run(self):
        srv = self.make_server()

        class RunTool:
            def run(self, **kw):
                return {"ran": kw}

        srv._tools = {"r": RunTool()}
        with patch.object(srv, "_check_policy", return_value=None):
            out = srv._handle_request({"method": "tools/call",
                                       "params": {"name": "r",
                                                  "arguments": {"a": 1}},
                                       "id": 12})
        self.assertIn('"a": 1', out["result"]["content"][0]["text"])

    def test_call_tool_exception_maps_to_error(self):
        srv = self.make_server()

        class BoomTool:
            def run(self, **kw):
                raise ValueError("kaputt")

        srv._tools = {"b": BoomTool()}
        with patch.object(srv, "_check_policy", return_value=None):
            out = srv._handle_request({"method": "tools/call",
                                       "params": {"name": "b",
                                                  "arguments": {}},
                                       "id": 13})
        self.assertEqual(out["error"]["code"], -32000)
        self.assertEqual(out["error"]["message"], "kaputt")


# ---------------------------------------------------------------------------
# Real HTTP integration (465-558)
# ---------------------------------------------------------------------------


class TestMcpHttpEndpoint(unittest.TestCase):
    API_KEY = "test-mcp-key-123456"

    def _start_server(self, api_key=None, require_auth=True):
        env = dict(os.environ)
        if api_key is None:
            env.pop("MCP_SERVER_API_KEY", None)
        else:
            env["MCP_SERVER_API_KEY"] = api_key
        with patch.dict(os.environ, env, clear=True):
            srv = mt.ORBITMCPServer(host="127.0.0.1", port=_free_port(),
                                    require_auth=require_auth)
            srv.start()

        # wait for listener (Windows loopback can drop the first SYN for
        # ~0.5s while the server thread spins up — use a generous timeout)
        for _ in range(50):
            try:
                c = http.client.HTTPConnection("127.0.0.1", srv.port,
                                               timeout=2.0)
                c.connect()
                c.close()
                break
            except OSError:
                time.sleep(0.05)
        else:
            srv.stop()
            self.fail("MCP server did not start listening")
        self.addCleanup(self._teardown, srv)
        return srv

    @staticmethod
    def _teardown(srv):
        srv.stop()
        try:  # unblock handle_request() with a dummy connection
            s = socket.create_connection(("127.0.0.1", srv.port), timeout=1)
            s.close()
        except OSError:
            pass
        if srv._thread:
            srv._thread.join(timeout=3)

    @staticmethod
    def _post(port, body, headers=None, method="POST", path="/"):
        # The handler answers 401/429 WITHOUT draining the request body;
        # closing with unread data makes Windows reset the connection, which
        # can abort the client before it reads the response. Retry those.
        last = None
        for attempt in range(4):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request(method, path, body=body, headers=headers or {})
                resp = conn.getresponse()
                data = resp.read()
                headers_out = dict(resp.getheaders())
                conn.close()
                return resp.status, data, headers_out
            except (ConnectionAbortedError, ConnectionResetError,
                    http.client.RemoteDisconnected) as e:
                last = e
                time.sleep(0.1)
        raise last

    def test_unauthorized_without_key(self):
        srv = self._start_server(api_key=self.API_KEY)
        status, data, _ = self._post(
            srv.port, json.dumps({"method": "tools/list"}),
            {"Content-Type": "application/json"})
        self.assertEqual(status, 401)
        self.assertIn("Unauthorized", data.decode())

    def test_unauthorized_wrong_bearer(self):
        srv = self._start_server(api_key=self.API_KEY)
        status, _, _ = self._post(
            srv.port, json.dumps({"method": "tools/list"}),
            {"Content-Type": "application/json",
             "Authorization": "Bearer wrong-key"})
        self.assertEqual(status, 401)

    def test_server_not_configured_returns_503(self):
        srv = self._start_server(api_key=None)  # no key configured
        status, data, _ = self._post(
            srv.port, json.dumps({"method": "tools/list"}),
            {"Content-Type": "application/json",
             "X-API-Key": "anything"})
        self.assertEqual(status, 503)
        self.assertIn("MCP_SERVER_API_KEY", data.decode())

    def test_authorized_tools_list(self):
        srv = self._start_server(api_key=self.API_KEY)
        status, data, hdrs = self._post(
            srv.port, json.dumps({"method": "tools/list", "id": 1}),
            {"Content-Type": "application/json",
             "X-API-Key": self.API_KEY})
        self.assertEqual(status, 200)
        payload = json.loads(data)
        names = [t["name"] for t in payload["result"]["tools"]]
        self.assertIn("web_search", names)
        self.assertEqual(payload["id"], 1)
        self.assertEqual(hdrs.get("Content-Type"), "application/json")

    def test_authorized_bearer_header(self):
        srv = self._start_server(api_key=self.API_KEY)
        status, _, _ = self._post(
            srv.port, json.dumps({"method": "tools/list"}),
            {"Content-Type": "application/json",
             "Authorization": f"Bearer {self.API_KEY}"})
        self.assertEqual(status, 200)

    def test_unknown_tool_via_http(self):
        srv = self._start_server(api_key=self.API_KEY)
        body = json.dumps({"method": "tools/call",
                           "params": {"name": "ghost", "arguments": {}},
                           "id": 9})
        status, data, _ = self._post(
            srv.port, body,
            {"Content-Type": "application/json", "X-API-Key": self.API_KEY})
        self.assertEqual(status, 200)  # JSON-RPC error, HTTP 200
        self.assertEqual(json.loads(data)["error"]["code"], -32601)

    def test_cors_origin_allowed_for_dev_port(self):
        srv = self._start_server(api_key=self.API_KEY)
        _, _, hdrs = self._post(
            srv.port, json.dumps({"method": "tools/list"}),
            {"Content-Type": "application/json",
             "X-API-Key": self.API_KEY,
             "Origin": "http://127.0.0.1:5173"})
        self.assertEqual(hdrs.get("Access-Control-Allow-Origin"),
                         "http://127.0.0.1:5173")

    def test_cors_origin_rejected_for_unknown_host(self):
        srv = self._start_server(api_key=self.API_KEY)
        _, _, hdrs = self._post(
            srv.port, json.dumps({"method": "tools/list"}),
            {"Content-Type": "application/json",
             "X-API-Key": self.API_KEY,
             "Origin": "http://evil.example.com"})
        self.assertNotIn("Access-Control-Allow-Origin", hdrs)

    def _raw_request(self, port, raw_bytes, read_timeout=3.0):
        s = socket.create_connection(("127.0.0.1", port), timeout=read_timeout)
        try:
            s.sendall(raw_bytes)
            chunks = []
            try:
                while True:
                    d = s.recv(4096)
                    if not d:
                        break
                    chunks.append(d)
            except socket.timeout:
                pass
            return b"".join(chunks)
        finally:
            s.close()

    def test_invalid_content_length_returns_400(self):
        srv = self._start_server(api_key=self.API_KEY)
        raw = (f"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n"
               f"Content-Length: not-a-number\r\n"
               f"X-API-Key: {self.API_KEY}\r\n\r\n").encode()
        resp = self._raw_request(srv.port, raw)
        self.assertIn(b"400", resp.split(b"\r\n")[0])
        self.assertIn(b"Invalid Content-Length", resp)

    def test_oversized_body_returns_413(self):
        srv = self._start_server(api_key=self.API_KEY)
        raw = (f"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n"
               f"Content-Length: {mt.MAX_REQUEST_BODY + 1}\r\n"
               f"X-API-Key: {self.API_KEY}\r\n\r\n").encode()
        resp = self._raw_request(srv.port, raw)
        self.assertIn(b"413", resp.split(b"\r\n")[0])
        self.assertIn(b"Request too large", resp)

    def test_malformed_json_body_returns_internal_error(self):
        srv = self._start_server(api_key=self.API_KEY)
        body = b"{not json at all"
        raw = (f"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n"
               f"Content-Length: {len(body)}\r\n"
               f"X-API-Key: {self.API_KEY}\r\n\r\n").encode() + body
        resp = self._raw_request(srv.port, raw)
        self.assertIn(b"Internal error", resp)

    def test_options_preflight(self):
        srv = self._start_server(api_key=self.API_KEY)
        raw = (b"OPTIONS / HTTP/1.1\r\nHost: 127.0.0.1\r\n"
               b"Origin: http://localhost:5173\r\n\r\n")
        resp = self._raw_request(srv.port, raw)
        head = resp.split(b"\r\n")[0]
        self.assertIn(b"200", head)
        self.assertIn(b"Access-Control-Allow-Origin: http://localhost:5173",
                      resp)
        self.assertIn(b"Access-Control-Allow-Methods: POST, OPTIONS", resp)
        self.assertIn(b"X-API-Key", resp)

    def test_rate_limit_kicks_in_after_max_requests(self):
        srv = self._start_server(api_key=self.API_KEY)
        headers = {"Content-Type": "application/json",
                   "X-API-Key": self.API_KEY}
        body = json.dumps({"method": "tools/list"})
        statuses = []
        # bucket starts full (30); consume it entirely then expect 429
        for _ in range(mt.RATE_LIMIT_MAX_REQUESTS + 5):
            status, _, _ = self._post(srv.port, body, headers)
            statuses.append(status)
        self.assertIn(429, statuses)
        # first request of the run must NOT be rate limited
        self.assertNotEqual(statuses[0], 429)


if __name__ == "__main__":
    unittest.main()
