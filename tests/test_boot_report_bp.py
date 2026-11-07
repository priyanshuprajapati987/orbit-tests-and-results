"""Unit tests for orbit/orbit/core/boot_report_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.boot_report_bp import boot_report_bp


class TestBootReportBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(boot_report_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(boot_report_bp.name, "boot_report")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/boot/latest", rules)
        self.assertIn("/api/boot/history", rules)

    def test_latest_from_boot_report(self):
        with patch("orbit.core.boot_report_bp.get_boot_report") as gb, \
             patch("orbit.core.boot_report_bp.get_startup"):
            gb.return_value.get_latest_report.return_value = {"boot": "ok"}
            r = self.client.get("/api/boot/latest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["boot"], "ok")

    def test_latest_fallback_startup(self):
        with patch("orbit.core.boot_report_bp.get_boot_report") as gb, \
             patch("orbit.core.boot_report_bp.get_startup") as gs, \
             patch("orbit.core.boot_report_bp.adapt_startup_report", return_value={"adapted": True}):
            gb.return_value.get_latest_report.return_value = None
            gs.return_value.get_latest.return_value = {"raw": "x"}
            r = self.client.get("/api/boot/latest")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["adapted"])

    def test_latest_none_404(self):
        with patch("orbit.core.boot_report_bp.get_boot_report") as gb, \
             patch("orbit.core.boot_report_bp.get_startup") as gs, \
             patch("orbit.core.boot_report_bp.adapt_startup_report", return_value=None):
            gb.return_value.get_latest_report.return_value = None
            gs.return_value.get_latest.return_value = None
            r = self.client.get("/api/boot/latest")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_latest_exception_500(self):
        with patch("orbit.core.boot_report_bp.get_boot_report", side_effect=RuntimeError("boom")):
            r = self.client.get("/api/boot/latest")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_history_from_boot_report(self):
        with patch("orbit.core.boot_report_bp.get_boot_report") as gb, \
             patch("orbit.core.boot_report_bp.get_startup"):
            gb.return_value.get_history.return_value = [{"h": 1}]
            r = self.client.get("/api/boot/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"h": 1}])
        gb.return_value.get_history.assert_called_once_with(limit=5)

    def test_history_fallback_startup(self):
        with patch("orbit.core.boot_report_bp.get_boot_report") as gb, \
             patch("orbit.core.boot_report_bp.get_startup") as gs, \
             patch("orbit.core.boot_report_bp.adapt_startup_report", side_effect=lambda x: {"adapted": x}):
            gb.return_value.get_history.return_value = []
            gs.return_value.get_history.return_value = [{"raw": "x"}]
            r = self.client.get("/api/boot/history")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"adapted": {"raw": "x"}}])

    def test_history_exception_500(self):
        with patch("orbit.core.boot_report_bp.get_boot_report", side_effect=RuntimeError("boom")):
            r = self.client.get("/api/boot/history")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
