"""Unit tests for orbit/orbit/core/proactive_assistant_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.proactive_assistant_bp as pabp
from flask import Flask
from orbit.core.proactive_assistant_bp import proactive_bp


class TestProactiveAssistantBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(proactive_bp)
        self.client = self.app.test_client()
        with pabp._reminder_lock:
            pabp._reminder_log.clear()

    def tearDown(self):
        with pabp._reminder_lock:
            pabp._reminder_log.clear()

    def test_blueprint_name(self):
        self.assertEqual(proactive_bp.name, "proactive_assistant")

    def test_url_prefix(self):
        self.assertEqual(proactive_bp.url_prefix, "/api/proactive")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/proactive/status", "/api/proactive/start", "/api/proactive/stop",
                  "/api/proactive/reset", "/api/proactive/reminders"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            ga.return_value.get_status.return_value = {"running": True}
            r = self.client.get("/api/proactive/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["running"])
        self.assertEqual(r.get_json()["recent_reminders"], [])

    def test_status_with_reminders(self):
        with pabp._reminder_lock:
            pabp._reminder_log.append({"id": "r1"})
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            ga.return_value.get_status.return_value = {"running": True}
            r = self.client.get("/api/proactive/status")
        self.assertEqual(r.get_json()["recent_reminders"], [{"id": "r1"}])

    def test_start(self):
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            r = self.client.post("/api/proactive/start")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        ga.return_value.start.assert_called_once()
        # callback registered
        cb = ga.return_value.start.call_args[0][0]
        self.assertTrue(callable(cb))

    def test_start_callback_filters_invalid(self):
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            r = self.client.post("/api/proactive/start")
        cb = ga.return_value.start.call_args[0][0]
        # invalid reminder (no id) should not be appended
        cb({"foo": "bar"})
        with pabp._reminder_lock:
            self.assertEqual(len(pabp._reminder_log), 0)
        # valid reminder appended
        cb({"id": "r2", "msg": "hi"})
        with pabp._reminder_lock:
            self.assertEqual(len(pabp._reminder_log), 1)
            self.assertEqual(pabp._reminder_log[0]["id"], "r2")

    def test_start_callback_caps_log(self):
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            r = self.client.post("/api/proactive/start")
        cb = ga.return_value.start.call_args[0][0]
        with pabp._reminder_lock:
            for i in range(100):
                pabp._reminder_log.append({"id": f"r{i}"})
        cb({"id": "new"})
        with pabp._reminder_lock:
            self.assertEqual(len(pabp._reminder_log), 100)
            self.assertEqual(pabp._reminder_log[-1]["id"], "new")

    def test_stop(self):
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            r = self.client.post("/api/proactive/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        ga.return_value.stop.assert_called_once()

    def test_reset(self):
        with pabp._reminder_lock:
            pabp._reminder_log.append({"id": "r1"})
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            r = self.client.post("/api/proactive/reset")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        ga.return_value.reset_session.assert_called_once()
        with pabp._reminder_lock:
            self.assertEqual(pabp._reminder_log, [])

    def test_reminders(self):
        with patch("orbit.core.proactive_assistant_bp.get_proactive_assistant") as ga:
            ga.return_value.get_reminders.return_value = [{"id": "r1"}, {"id": "r2"}]
            r = self.client.get("/api/proactive/reminders")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["reminders"], [{"id": "r1"}, {"id": "r2"}])
        self.assertEqual(body["total"], 2)


if __name__ == "__main__":
    unittest.main()
