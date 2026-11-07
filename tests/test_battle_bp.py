"""Unit tests for orbit/orbit/core/battle_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.battle_bp import battle_bp


class TestBattleBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(battle_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(battle_bp.name, "battle")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/battle/random-task", "/api/battle/random-skill", "/api/battle/ready"]:
            self.assertIn(p, rules)

    def test_random_task(self):
        with patch("orbit.core.battle_prep.pick_random_task", return_value="task1"):
            r = self.client.get("/api/battle/random-task")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["task"], "task1")

    def test_random_skill(self):
        with patch("orbit.core.battle_prep.pick_random_skill", return_value="skill1"):
            r = self.client.get("/api/battle/random-skill")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["skill"], "skill1")

    def test_ready(self):
        with patch("orbit.core.version.VERSION", "9.9.9"):
            r = self.client.get("/api/battle/ready")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["version"], "9.9.9")
        self.assertIn("battle-ready", body["message"])


if __name__ == "__main__":
    unittest.main()
