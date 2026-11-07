"""Unit tests for orbit/orbit/core/timemachine_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.timemachine_bp import timemachine_bp


class TestTimemachineBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(timemachine_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(timemachine_bp.name, "timemachine")

    def test_url_prefix(self):
        self.assertEqual(timemachine_bp.url_prefix, "/api/timemachine")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/timemachine/log", rules)
        self.assertIn("/api/timemachine/restore", rules)

    def test_log(self):
        with patch("orbit.core.timemachine_bp.get_time_machine") as gt:
            gt.return_value.log.return_value = [{"snap": 1}]
            r = self.client.get("/api/timemachine/log?n=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [{"snap": 1}])
        gt.return_value.log.assert_called_once_with(5)

    def test_log_default(self):
        with patch("orbit.core.timemachine_bp.get_time_machine") as gt:
            gt.return_value.log.return_value = []
            r = self.client.get("/api/timemachine/log")
        gt.return_value.log.assert_called_once_with(20)

    def test_log_invalid_n(self):
        with patch("orbit.core.timemachine_bp.get_time_machine") as gt:
            gt.return_value.log.return_value = []
            r = self.client.get("/api/timemachine/log?n=abc")
        gt.return_value.log.assert_called_once_with(20)

    def test_restore_success(self):
        with patch("orbit.core.timemachine_bp.get_time_machine") as gt:
            gt.return_value.restore.return_value = {"snapshot": 1}
            r = self.client.post("/api/timemachine/restore", json={"index": 2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["snapshot"], 1)
        gt.return_value.restore.assert_called_once_with(2)

    def test_restore_not_found_404(self):
        with patch("orbit.core.timemachine_bp.get_time_machine") as gt:
            gt.return_value.restore.return_value = None
            r = self.client.post("/api/timemachine/restore", json={"index": 99})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_restore_invalid_index(self):
        with patch("orbit.core.timemachine_bp.get_time_machine") as gt:
            gt.return_value.restore.return_value = None
            r = self.client.post("/api/timemachine/restore", json={"index": "abc"})
        gt.return_value.restore.assert_called_once_with(-1)

    def test_restore_no_body(self):
        with patch("orbit.core.timemachine_bp.get_time_machine") as gt:
            gt.return_value.restore.return_value = None
            r = self.client.post("/api/timemachine/restore")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
