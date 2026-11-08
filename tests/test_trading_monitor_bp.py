"""Unit tests for orbit/orbit/core/trading_monitor_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.trading_monitor_bp import trading_monitor_bp


class TestTradingMonitorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(trading_monitor_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(trading_monitor_bp.name, "trading_monitor_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/trading/status", "/api/trading/watchlist", "/api/trading/add",
                  "/api/trading/remove", "/api/trading/alert", "/api/trading/start",
                  "/api/trading/stop"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.get_stats.return_value = {"running": True}
            r = self.client.get("/api/trading/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["running"])

    def test_watchlist(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.get_watchlist.return_value = ["AAPL"]
            r = self.client.get("/api/trading/watchlist")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["watchlist"], ["AAPL"])

    def test_add_missing_symbol_400(self):
        r = self.client.post("/api/trading/add", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_add_success(self):
        item = MagicMock()
        item.symbol = "AAPL"
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.add_symbol.return_value = item
            r = self.client.post("/api/trading/add", json={"symbol": "AAPL", "name": "Apple", "asset_type": "stock"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["status"], "added")
        self.assertEqual(r.get_json()["symbol"], "AAPL")
        gt.return_value.add_symbol.assert_called_once_with("AAPL", "Apple", "stock")

    def test_add_defaults(self):
        item = MagicMock()
        item.symbol = "MSFT"
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.add_symbol.return_value = item
            r = self.client.post("/api/trading/add", json={"symbol": "MSFT"})
        gt.return_value.add_symbol.assert_called_once_with("MSFT", None, "stock")

    def test_add_no_body(self):
        r = self.client.post("/api/trading/add")
        self.assertEqual(r.status_code, 400)

    def test_remove_success(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.remove_symbol.return_value = True
            r = self.client.post("/api/trading/remove", json={"symbol": "AAPL"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "removed")

    def test_remove_not_found_404(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.remove_symbol.return_value = False
            r = self.client.post("/api/trading/remove", json={"symbol": "AAPL"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_remove_no_body(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.remove_symbol.return_value = False
            r = self.client.post("/api/trading/remove")
        self.assertEqual(r.status_code, 404)

    def test_alert_missing_fields_400(self):
        r = self.client.post("/api/trading/alert", json={"symbol": "AAPL"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_alert_bad_target_400(self):
        r = self.client.post("/api/trading/alert", json={"symbol": "AAPL", "target_price": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_alert_success(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.add_alert.return_value = {"alert_id": "a1"}
            r = self.client.post("/api/trading/alert", json={"symbol": "AAPL", "target_price": 150.0, "direction": "above"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["alert_id"], "a1")
        gt.return_value.add_alert.assert_called_once_with("AAPL", 150.0, "above")

    def test_alert_default_direction(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.add_alert.return_value = {"alert_id": "a2"}
            r = self.client.post("/api/trading/alert", json={"symbol": "AAPL", "target_price": 150.0})
        gt.return_value.add_alert.assert_called_once_with("AAPL", 150.0, "above")

    def test_alert_error_in_result_400(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            gt.return_value.add_alert.return_value = {"error": "bad"}
            r = self.client.post("/api/trading/alert", json={"symbol": "AAPL", "target_price": 150.0})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_alert_no_body(self):
        r = self.client.post("/api/trading/alert")
        self.assertEqual(r.status_code, 400)

    def test_start(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            r = self.client.post("/api/trading/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "started")
        gt.return_value.start_monitoring.assert_called_once()

    def test_stop(self):
        with patch("orbit.core.trading_monitor_bp.get_trading_monitor") as gt:
            r = self.client.post("/api/trading/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "stopped")
        gt.return_value.stop_monitoring.assert_called_once()


if __name__ == "__main__":
    unittest.main()
