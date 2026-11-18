"""Unit tests for orbit/orbit/core/security_guard_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.security_guard_bp import security_guard_bp


class GuardBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(security_guard_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(security_guard_bp.name, "security_guard")
        self.assertEqual(security_guard_bp.url_prefix, "/api/security-guard")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/security-guard/scan", "/api/security-guard/defenses",
                  "/api/security-guard/report", "/api/security-guard/incidents",
                  "/api/security-guard/status", "/api/security-guard/fix",
                  "/api/security-guard/monitor/start", "/api/security-guard/monitor/stop",
                  "/api/security-guard/heal"]:
            self.assertIn(p, rules)


class TestScan(GuardBpBase):
    def test_scan_get_default_deep_true(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.scan_codebase.return_value = {"findings": 0}
            r = self.client.get("/api/security-guard/scan")
        self.assertEqual(r.status_code, 200)
        gg.return_value.scan_codebase.assert_called_once_with(deep=True)

    def test_scan_get_deep_false(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.scan_codebase.return_value = {}
            r = self.client.get("/api/security-guard/scan?deep=false")
        gg.return_value.scan_codebase.assert_called_once_with(deep=False)

    def test_scan_post_body_deep(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.scan_codebase.return_value = {}
            r = self.client.post("/api/security-guard/scan", json={"deep": False})
        gg.return_value.scan_codebase.assert_called_once_with(deep=False)

    def test_scan_post_body_wins_over_args(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.scan_codebase.return_value = {}
            r = self.client.post("/api/security-guard/scan?deep=true", json={"deep": False})
        gg.return_value.scan_codebase.assert_called_once_with(deep=False)

    def test_scan_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("boom")):
            r = self.client.get("/api/security-guard/scan")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")


class TestDefenses(GuardBpBase):
    def test_defenses(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.check_defenses.return_value = {"ok": True}
            r = self.client.get("/api/security-guard/defenses")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_defenses_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.get("/api/security-guard/defenses")
        self.assertEqual(r.status_code, 500)


class TestReport(GuardBpBase):
    def test_report_default(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.run_full_check.return_value = {"score": 90}
            r = self.client.get("/api/security-guard/report")
        gg.return_value.run_full_check.assert_called_once_with(deep=True)

    def test_report_deep_false(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.run_full_check.return_value = {}
            r = self.client.get("/api/security-guard/report?deep=false")
        gg.return_value.run_full_check.assert_called_once_with(deep=False)

    def test_report_post_body(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.run_full_check.return_value = {}
            r = self.client.post("/api/security-guard/report", json={"deep": False})
        gg.return_value.run_full_check.assert_called_once_with(deep=False)

    def test_report_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.get("/api/security-guard/report")
        self.assertEqual(r.status_code, 500)


class TestIncidents(GuardBpBase):
    def test_incidents_default_limit(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.incidents.return_value = []
            r = self.client.get("/api/security-guard/incidents")
        self.assertEqual(r.status_code, 200)
        gg.return_value.incidents.assert_called_once_with(limit=50)

    def test_incidents_custom_limit(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.incidents.return_value = []
            r = self.client.get("/api/security-guard/incidents?limit=10")
        gg.return_value.incidents.assert_called_once_with(limit=10)

    def test_incidents_bad_limit_fallback(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.incidents.return_value = []
            r = self.client.get("/api/security-guard/incidents?limit=abc")
        gg.return_value.incidents.assert_called_once_with(limit=50)

    def test_incidents_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.get("/api/security-guard/incidents")
        self.assertEqual(r.status_code, 500)


class TestStatus(GuardBpBase):
    def test_status(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.get_status.return_value = {"monitoring": False, "scans": 3}
            r = self.client.get("/api/security-guard/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["scans"], 3)

    def test_status_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.get("/api/security-guard/status")
        self.assertEqual(r.status_code, 500)


class TestFix(GuardBpBase):
    def test_fix(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.auto_fix.return_value = {"fixed": ["gitignore"]}
            r = self.client.post("/api/security-guard/fix")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["fixed"], ["gitignore"])

    def test_fix_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.post("/api/security-guard/fix")
        self.assertEqual(r.status_code, 500)


class TestMonitor(GuardBpBase):
    def test_monitor_start_default_interval(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.start_monitor.return_value = True
            r = self.client.post("/api/security-guard/monitor/start", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["started"])
        self.assertTrue(body["monitoring"])
        gg.return_value.start_monitor.assert_called_once_with(interval=300)

    def test_monitor_start_custom_interval(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.start_monitor.return_value = True
            r = self.client.post("/api/security-guard/monitor/start", json={"interval": 600})
        gg.return_value.start_monitor.assert_called_once_with(interval=600)

    def test_monitor_start_clamp_low(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.start_monitor.return_value = True
            r = self.client.post("/api/security-guard/monitor/start", json={"interval": 1})
        gg.return_value.start_monitor.assert_called_once_with(interval=60)

    def test_monitor_start_clamp_high(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.start_monitor.return_value = True
            r = self.client.post("/api/security-guard/monitor/start", json={"interval": 999999})
        gg.return_value.start_monitor.assert_called_once_with(interval=3600)

    def test_monitor_start_bad_interval_fallback(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.start_monitor.return_value = True
            r = self.client.post("/api/security-guard/monitor/start", json={"interval": "abc"})
        gg.return_value.start_monitor.assert_called_once_with(interval=300)

    def test_monitor_start_negative_clamped(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.start_monitor.return_value = True
            r = self.client.post("/api/security-guard/monitor/start", json={"interval": -100})
        gg.return_value.start_monitor.assert_called_once_with(interval=60)

    def test_monitor_start_no_body(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.start_monitor.return_value = True
            r = self.client.post("/api/security-guard/monitor/start")
        self.assertEqual(r.status_code, 200)

    def test_monitor_start_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.post("/api/security-guard/monitor/start", json={})
        self.assertEqual(r.status_code, 500)

    def test_monitor_stop(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            r = self.client.post("/api/security-guard/monitor/stop")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["monitoring"])
        gg.return_value.stop_monitor.assert_called_once()

    def test_monitor_stop_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.post("/api/security-guard/monitor/stop")
        self.assertEqual(r.status_code, 500)


class TestHeal(GuardBpBase):
    def test_heal(self):
        with patch("orbit.core.security_guard_bp.get_security_guard") as gg:
            gg.return_value.run_full_check.return_value = {"score": 95}
            gg.return_value.auto_fix.return_value = {"fixed": []}
            r = self.client.post("/api/security-guard/heal")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["healed"])
        self.assertEqual(body["report"], {"score": 95})
        self.assertEqual(body["fix"], {"fixed": []})
        gg.return_value.run_full_check.assert_called_once_with(deep=True)

    def test_heal_exception_500(self):
        with patch("orbit.core.security_guard_bp.get_security_guard", side_effect=RuntimeError("x")):
            r = self.client.post("/api/security-guard/heal")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
