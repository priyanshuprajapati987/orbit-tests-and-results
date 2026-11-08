"""Unit tests for orbit/orbit/core/team_restructurer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.team_restructurer_bp import team_restructurer_bp


class TestTeamRestucturerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(team_restructurer_bp)
        self.client = self.app.test_client()
        self.fake_tr = MagicMock()
        sys.modules["orbit.orbit.core.team_restructurer"] = self.fake_tr

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.team_restructurer", None)

    def test_blueprint_name(self):
        self.assertEqual(team_restructurer_bp.name, "team_restructurer")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/team/analyze-load", "/api/team/restructure", "/api/team/history",
                  "/api/team/current", "/api/team/stats", "/api/team/reset"]:
            self.assertIn(p, rules)

    def test_analyze_load(self):
        self.fake_tr.get_team_restructurer.return_value.analyze_load.return_value = "high"
        r = self.client.post("/api/team/analyze-load", json={"pending_tasks": 5, "agents": ["a"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["load_level"], "high")
        self.fake_tr.get_team_restructurer.return_value.analyze_load.assert_called_once_with(5)

    def test_analyze_load_default_pending(self):
        self.fake_tr.get_team_restructurer.return_value.analyze_load.return_value = "low"
        r = self.client.post("/api/team/analyze-load", json={"agents": ["a", "b"]})
        self.fake_tr.get_team_restructurer.return_value.analyze_load.assert_called_once_with(2)

    def test_analyze_load_bad_pending_400(self):
        r = self.client.post("/api/team/analyze-load", json={"pending_tasks": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_load_no_body(self):
        self.fake_tr.get_team_restructurer.return_value.analyze_load.return_value = "low"
        r = self.client.post("/api/team/analyze-load")
        self.fake_tr.get_team_restructurer.return_value.analyze_load.assert_called_once_with(0)

    def test_analyze_load_clamped(self):
        self.fake_tr.get_team_restructurer.return_value.analyze_load.return_value = "high"
        r = self.client.post("/api/team/analyze-load", json={"pending_tasks": 999999})
        self.fake_tr.get_team_restructurer.return_value.analyze_load.assert_called_once_with(100000)

    def test_restructure(self):
        self.fake_tr.get_team_restructurer.return_value.restructure.return_value = {"restructured": True}
        r = self.client.post("/api/team/restructure", json={"agents": ["a"], "load_level": "high"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["restructured"])
        self.fake_tr.get_team_restructurer.return_value.restructure.assert_called_once_with(["a"], "high")

    def test_restructure_no_body(self):
        self.fake_tr.get_team_restructurer.return_value.restructure.return_value = {"ok": True}
        r = self.client.post("/api/team/restructure")
        self.fake_tr.get_team_restructurer.return_value.restructure.assert_called_once_with([], None)

    def test_history(self):
        self.fake_tr.get_team_restructurer.return_value.get_history.return_value = [{"h": 1}]
        r = self.client.get("/api/team/history?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["restructures"], [{"h": 1}])
        self.fake_tr.get_team_restructurer.return_value.get_history.assert_called_once_with(5)

    def test_history_default(self):
        self.fake_tr.get_team_restructurer.return_value.get_history.return_value = []
        r = self.client.get("/api/team/history")
        self.fake_tr.get_team_restructurer.return_value.get_history.assert_called_once_with(20)

    def test_history_invalid_limit(self):
        self.fake_tr.get_team_restructurer.return_value.get_history.return_value = []
        r = self.client.get("/api/team/history?limit=abc")
        self.assertEqual(r.status_code, 200)
        self.fake_tr.get_team_restructurer.return_value.get_history.assert_called_once_with(20)

    def test_history_clamped(self):
        self.fake_tr.get_team_restructurer.return_value.get_history.return_value = []
        r = self.client.get("/api/team/history?limit=500")
        self.fake_tr.get_team_restructurer.return_value.get_history.assert_called_once_with(200)

    def test_current_found(self):
        self.fake_tr.get_team_restructurer.return_value.get_current_structure.return_value = {"structure": "x"}
        r = self.client.get("/api/team/current")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["structure"], "x")

    def test_current_not_found_404(self):
        self.fake_tr.get_team_restructurer.return_value.get_current_structure.return_value = None
        r = self.client.get("/api/team/current")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_stats(self):
        self.fake_tr.get_team_restructurer.return_value.get_stats.return_value = {"total": 3}
        r = self.client.get("/api/team/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 3)

    def test_reset(self):
        r = self.client.post("/api/team/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "reset")
        self.fake_tr.get_team_restructurer.return_value.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
