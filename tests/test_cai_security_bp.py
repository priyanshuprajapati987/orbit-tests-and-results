"""Unit tests for orbit/orbit/core/cai_security_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.cai_security_bp import cai_security_bp


class TestCaiSecurityBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(cai_security_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(cai_security_bp.name, "cai_security_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/cai/scan", "/api/cai/audit", "/api/cai/threats", "/api/cai/status"]:
            self.assertIn(p, rules)

    def test_scan(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_analysis.return_value = "analysis result"
            r = self.client.post("/api/cai/scan", json={"query": "audit"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], "analysis result")
        cs.run_analysis.assert_called_once_with("audit")

    def test_scan_default_query(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_analysis.return_value = "r"
            r = self.client.post("/api/cai/scan", json={})
        cs.run_analysis.assert_called_once_with("Perform a full security audit")

    def test_scan_no_body(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_analysis.return_value = "r"
            r = self.client.post("/api/cai/scan")
        cs.run_analysis.assert_called_once_with("Perform a full security audit")

    def test_scan_error(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_analysis.side_effect = RuntimeError("boom")
            r = self.client.post("/api/cai/scan", json={"query": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_audit(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_audit.return_value = "audit result"
            r = self.client.post("/api/cai/audit")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], "audit result")

    def test_audit_error(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_audit.side_effect = RuntimeError("boom")
            r = self.client.post("/api/cai/audit")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_threats(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_threat_analysis.return_value = "threats"
            r = self.client.post("/api/cai/threats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["result"], "threats")

    def test_threats_error(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs.run_threat_analysis.side_effect = RuntimeError("boom")
            r = self.client.post("/api/cai/threats")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_status(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs._CAI_AVAILABLE = True
            cs._cai_agent = object()
            r = self.client.get("/api/cai/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["available"])
        self.assertTrue(body["has_agent"])

    def test_status_unavailable(self):
        with patch("orbit.tools.cai_security", create=True) as cs:
            cs._CAI_AVAILABLE = False
            cs._cai_agent = None
            r = self.client.get("/api/cai/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertFalse(body["available"])
        self.assertFalse(body["has_agent"])

    def test_status_error(self):
        class Boom:
            def __getattr__(self, name):
                raise RuntimeError("boom")

        with patch("orbit.tools.cai_security", Boom(), create=True):
            r = self.client.get("/api/cai/status")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
