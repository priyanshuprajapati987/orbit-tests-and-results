"""Unit tests for orbit/orbit/core/conv_analytics_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.conv_analytics_bp import conv_analytics_bp


class TestConvAnalyticsBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(conv_analytics_bp)
        self.client = self.app.test_client()
        self.fake_ca = MagicMock()
        sys.modules["orbit.orbit.core.conversation_analytics"] = self.fake_ca

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.conversation_analytics", None)

    def test_blueprint_name(self):
        self.assertEqual(conv_analytics_bp.name, "conv_analytics")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/conv-analytics/track", "/api/conv-analytics/end",
                  "/api/conv-analytics/conversation/<cid>", "/api/conv-analytics/overview",
                  "/api/conv-analytics/hourly", "/api/conv-analytics/daily",
                  "/api/conv-analytics/stats"]:
            self.assertIn(p, rules)

    def test_track_missing_fields_400(self):
        r = self.client.post("/api/conv-analytics/track", json={"conversation_id": "c1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_track_success(self):
        r = self.client.post("/api/conv-analytics/track", json={"conversation_id": "c1", "role": "user", "content": "hi", "title": "T"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "tracked")
        self.fake_ca.get_conversation_analytics.return_value.track_turn.assert_called_once_with("c1", "user", "hi", "T")

    def test_track_no_body(self):
        r = self.client.post("/api/conv-analytics/track")
        self.assertEqual(r.status_code, 400)

    def test_end_missing_cid_400(self):
        r = self.client.post("/api/conv-analytics/end", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_end_success(self):
        r = self.client.post("/api/conv-analytics/end", json={"conversation_id": "c1", "resolution": "resolved"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ended")
        self.fake_ca.get_conversation_analytics.return_value.end_conversation.assert_called_once_with("c1", "resolved")

    def test_end_default_resolution(self):
        r = self.client.post("/api/conv-analytics/end", json={"conversation_id": "c1"})
        self.fake_ca.get_conversation_analytics.return_value.end_conversation.assert_called_once_with("c1", "resolved")

    def test_end_no_body(self):
        r = self.client.post("/api/conv-analytics/end")
        self.assertEqual(r.status_code, 400)

    def test_conversation_found(self):
        self.fake_ca.get_conversation_analytics.return_value.get_conversation.return_value = {"id": "c1"}
        r = self.client.get("/api/conv-analytics/conversation/c1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "c1")

    def test_conversation_not_found_404(self):
        self.fake_ca.get_conversation_analytics.return_value.get_conversation.return_value = None
        r = self.client.get("/api/conv-analytics/conversation/c1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_overview(self):
        self.fake_ca.get_conversation_analytics.return_value.get_overview.return_value = {"total": 5}
        r = self.client.get("/api/conv-analytics/overview")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)

    def test_hourly(self):
        self.fake_ca.get_conversation_analytics.return_value.get_hourly_pattern.return_value = [1, 2]
        r = self.client.get("/api/conv-analytics/hourly")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["hourly"], [1, 2])

    def test_daily(self):
        self.fake_ca.get_conversation_analytics.return_value.get_daily_pattern.return_value = [3, 4]
        r = self.client.get("/api/conv-analytics/daily?days=14")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["daily"], [3, 4])
        self.fake_ca.get_conversation_analytics.return_value.get_daily_pattern.assert_called_once_with(14)

    def test_daily_default(self):
        self.fake_ca.get_conversation_analytics.return_value.get_daily_pattern.return_value = []
        r = self.client.get("/api/conv-analytics/daily")
        self.fake_ca.get_conversation_analytics.return_value.get_daily_pattern.assert_called_once_with(7)

    def test_stats(self):
        self.fake_ca.get_conversation_analytics.return_value.get_stats.return_value = {"count": 9}
        r = self.client.get("/api/conv-analytics/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 9)


if __name__ == "__main__":
    unittest.main()
