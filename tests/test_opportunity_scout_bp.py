"""Unit tests for orbit/orbit/core/opportunity_scout_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.opportunity_scout_bp import opportunity_bp


def make_opp(d):
    m = MagicMock()
    m.to_dict.return_value = d
    return m


class TestOpportunityScoutBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(opportunity_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(opportunity_bp.name, "opportunity_scout")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/opportunities", "/api/opportunities/scan", "/api/opportunities/stats",
                  "/api/opportunities/<opp_id>", "/api/opportunities/<opp_id>/action"]:
            self.assertIn(p, rules)

    def test_get_opportunities(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.get_top_opportunities.return_value = [make_opp({"id": "o1"}), make_opp({"id": "o2"})]
            r = self.client.get("/api/opportunities?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["opportunities"], [{"id": "o1"}, {"id": "o2"}])
        scout.get_top_opportunities.assert_called_once_with(limit=5)

    def test_get_opportunities_default(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.get_top_opportunities.return_value = []
            r = self.client.get("/api/opportunities")
        scout.get_top_opportunities.assert_called_once_with(limit=20)

    def test_scan(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.analyze_all_opportunities.return_value = [make_opp({"id": "o1"}) for _ in range(7)]
            r = self.client.post("/api/opportunities/scan")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["scanned"], 7)
        self.assertEqual(len(body["opportunities"]), 5)

    def test_stats(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.get_stats.return_value = {"total": 3}
            r = self.client.get("/api/opportunities/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 3)

    def test_dismiss_success(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.dismiss_opportunity.return_value = True
            r = self.client.delete("/api/opportunities/o1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "dismissed")
        scout.dismiss_opportunity.assert_called_once_with("o1")

    def test_dismiss_not_found_404(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.dismiss_opportunity.return_value = False
            r = self.client.delete("/api/opportunities/o1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_record_action_missing_action_400(self):
        r = self.client.post("/api/opportunities/o1/action", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_action_success(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.record_action.return_value = True
            r = self.client.post("/api/opportunities/o1/action", json={"action": "done"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "recorded")
        scout.record_action.assert_called_once_with("o1", "done")

    def test_record_action_not_found_404(self):
        with patch("orbit.core.opportunity_scout_bp.get_opportunity_scout") as gs:
            scout = gs.return_value
            scout.record_action.return_value = False
            r = self.client.post("/api/opportunities/o1/action", json={"action": "done"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_record_action_no_body(self):
        r = self.client.post("/api/opportunities/o1/action")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
