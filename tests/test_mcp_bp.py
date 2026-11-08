"""Unit tests for orbit/orbit/core/mcp_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.mcp_bp as mcp_bp_mod
from flask import Flask
from orbit.core.mcp_bp import mcp_bp


class TestMcpBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(mcp_bp)
        self.client = self.app.test_client()
        mcp_bp_mod._mcp_server = None

    def tearDown(self):
        mcp_bp_mod._mcp_server = None

    def test_blueprint_name(self):
        self.assertEqual(mcp_bp.name, "mcp_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/mcp/status", "/api/mcp/start", "/api/mcp/call",
                  "/api/mcp/server/start", "/api/mcp/server/stop"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.mcp_bp.get_manager") as gm:
            mgr = gm.return_value
            mgr.get_status.return_value = [{"name": "s1"}]
            mgr.list_tools.return_value = ["t1", "t2"]
            r = self.client.get("/api/mcp/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["servers"], [{"name": "s1"}])
        self.assertEqual(body["total_tools"], 2)
        self.assertEqual(body["tools"], ["t1", "t2"])

    def test_status_error(self):
        with patch("orbit.core.mcp_bp.get_manager", side_effect=RuntimeError("boom")):
            r = self.client.get("/api/mcp/status")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_start_loaded(self):
        with patch("orbit.core.mcp_bp.get_manager") as gm:
            gm.return_value.load_config.return_value = 2
            r = self.client.post("/api/mcp/start", json={"config_path": "/p"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(r.get_json()["count"], 2)
        gm.return_value.load_config.assert_called_once_with("/p")

    def test_start_none_loaded(self):
        with patch("orbit.core.mcp_bp.get_manager") as gm:
            gm.return_value.load_config.return_value = 0
            r = self.client.post("/api/mcp/start", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "warning")

    def test_start_no_body(self):
        with patch("orbit.core.mcp_bp.get_manager") as gm:
            gm.return_value.load_config.return_value = 1
            r = self.client.post("/api/mcp/start")
        gm.return_value.load_config.assert_called_once_with(None)

    def test_start_error(self):
        with patch("orbit.core.mcp_bp.get_manager", side_effect=RuntimeError("boom")):
            r = self.client.post("/api/mcp/start")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_call_missing_tool_400(self):
        r = self.client.post("/api/mcp/call", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_call_success(self):
        with patch("orbit.core.mcp_bp.get_manager") as gm:
            gm.return_value.call_tool.return_value = "result"
            r = self.client.post("/api/mcp/call", json={"tool": "t1", "params": {"a": 1}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], "result")
        gm.return_value.call_tool.assert_called_once_with("t1", {"a": 1})

    def test_call_default_params(self):
        with patch("orbit.core.mcp_bp.get_manager") as gm:
            gm.return_value.call_tool.return_value = "r"
            r = self.client.post("/api/mcp/call", json={"tool": "t1"})
        gm.return_value.call_tool.assert_called_once_with("t1", {})

    def test_call_no_body(self):
        r = self.client.post("/api/mcp/call")
        self.assertEqual(r.status_code, 400)

    def test_call_error(self):
        with patch("orbit.core.mcp_bp.get_manager", side_effect=RuntimeError("boom")):
            r = self.client.post("/api/mcp/call", json={"tool": "t1"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_server_start(self):
        server = MagicMock()
        with patch("orbit.core.mcp_bp.ORBITMCPServer", return_value=server) as cls:
            r = self.client.post("/api/mcp/server/start", json={"port": 9000})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertIn("9000", r.get_json()["message"])
        cls.assert_called_once_with(port=9000)
        server.start.assert_called_once()

    def test_server_start_default_port(self):
        server = MagicMock()
        with patch("orbit.core.mcp_bp.ORBITMCPServer", return_value=server) as cls:
            r = self.client.post("/api/mcp/server/start", json={})
        cls.assert_called_once_with(port=8321)

    def test_server_start_already_running(self):
        mcp_bp_mod._mcp_server = MagicMock()
        r = self.client.post("/api/mcp/server/start", json={})
        self.assertEqual(r.status_code, 200)
        self.assertIn("already running", r.get_json()["message"])

    def test_server_start_no_body(self):
        server = MagicMock()
        with patch("orbit.core.mcp_bp.ORBITMCPServer", return_value=server) as cls:
            r = self.client.post("/api/mcp/server/start")
        cls.assert_called_once_with(port=8321)

    def test_server_start_error(self):
        with patch("orbit.core.mcp_bp.ORBITMCPServer", side_effect=RuntimeError("boom")):
            r = self.client.post("/api/mcp/server/start", json={})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_server_stop(self):
        server = MagicMock()
        mcp_bp_mod._mcp_server = server
        r = self.client.post("/api/mcp/server/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertIn("stopped", r.get_json()["message"])
        server.stop.assert_called_once()
        self.assertIsNone(mcp_bp_mod._mcp_server)

    def test_server_stop_not_running(self):
        mcp_bp_mod._mcp_server = None
        r = self.client.post("/api/mcp/server/stop")
        self.assertEqual(r.status_code, 200)
        self.assertIn("No MCP server running", r.get_json()["message"])

    def test_server_stop_error(self):
        server = MagicMock()
        server.stop.side_effect = RuntimeError("boom")
        mcp_bp_mod._mcp_server = server
        r = self.client.post("/api/mcp/server/stop")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
