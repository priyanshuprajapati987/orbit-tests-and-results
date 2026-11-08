"""Unit tests for orbit/orbit/core/dep_scanner_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.dep_scanner_bp import dep_scanner_bp


class TestDepScannerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(dep_scanner_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(dep_scanner_bp.name, "dep_scanner_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/dep-scanner/scan", "/api/dep-scanner/status",
                  "/api/dep-scanner/python-vulns", "/api/dep-scanner/python-outdated",
                  "/api/dep-scanner/npm"]:
            self.assertIn(p, rules)

    def test_scan(self):
        result = MagicMock()
        result.to_dict.return_value = {"scanned": True}
        with patch("orbit.core.dep_scanner.run_scan", return_value=result) as rs:
            r = self.client.post("/api/dep-scanner/scan", json={"force": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"scanned": True})
        rs.assert_called_once_with(force=True)

    def test_scan_default_force(self):
        result = MagicMock()
        result.to_dict.return_value = {"scanned": True}
        with patch("orbit.core.dep_scanner.run_scan", return_value=result) as rs:
            r = self.client.post("/api/dep-scanner/scan", json={})
        rs.assert_called_once_with(force=False)

    def test_scan_no_body(self):
        result = MagicMock()
        result.to_dict.return_value = {"scanned": True}
        with patch("orbit.core.dep_scanner.run_scan", return_value=result) as rs:
            r = self.client.post("/api/dep-scanner/scan")
        rs.assert_called_once_with(force=False)

    def test_status(self):
        with patch("orbit.core.dep_scanner.get_status", return_value={"last": "ok"}):
            r = self.client.get("/api/dep-scanner/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"last": "ok"})

    def test_python_vulns(self):
        vuln = MagicMock()
        vuln.to_dict.return_value = {"pkg": "x"}
        result = MagicMock()
        result.python_vulns = [vuln]
        with patch("orbit.core.dep_scanner.run_scan", return_value=result):
            r = self.client.get("/api/dep-scanner/python-vulns")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["vulnerabilities"], [{"pkg": "x"}])

    def test_python_outdated(self):
        result = MagicMock()
        result.python_outdated = [{"name": "flask"}]
        with patch("orbit.core.dep_scanner.run_scan", return_value=result):
            r = self.client.get("/api/dep-scanner/python-outdated")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["outdated"], [{"name": "flask"}])

    def test_npm(self):
        result = MagicMock()
        result.npm_vulns = [{"v": 1}]
        result.npm_outdated = [{"o": 2}]
        with patch("orbit.core.dep_scanner.run_scan", return_value=result):
            r = self.client.get("/api/dep-scanner/npm")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["vulnerabilities"], [{"v": 1}])
        self.assertEqual(body["outdated"], [{"o": 2}])


if __name__ == "__main__":
    unittest.main()
