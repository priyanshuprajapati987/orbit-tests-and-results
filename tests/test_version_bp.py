"""Unit tests for orbit/orbit/core/version_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.version_bp import version_bp


class TestVersionBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(version_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(version_bp.name, "version")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/version", "/api/version/increment", "/api/version/changelog"]:
            self.assertIn(p, rules)

    def test_get_version(self):
        with patch("orbit.core.version_bp.get_version_system") as gv:
            gv.return_value.get_version.return_value = {"version": "1.0.0"}
            r = self.client.get("/api/version")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["version"], "1.0.0")

    def test_get_version_error(self):
        with patch("orbit.core.version_bp.get_version_system") as gv:
            gv.return_value.get_version.side_effect = RuntimeError("boom")
            r = self.client.get("/api/version")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_increment(self):
        with patch("orbit.core.version_bp.get_version_system") as gv:
            gv.return_value.increment_version.return_value = {"version": "1.0.1"}
            r = self.client.post("/api/version/increment", json={"bump_type": "patch"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["version"], "1.0.1")
        gv.return_value.increment_version.assert_called_once_with("patch")

    def test_increment_default(self):
        with patch("orbit.core.version_bp.get_version_system") as gv:
            gv.return_value.increment_version.return_value = {"version": "1.0.1"}
            r = self.client.post("/api/version/increment", json={})
        gv.return_value.increment_version.assert_called_once_with("patch")

    def test_increment_error(self):
        with patch("orbit.core.version_bp.get_version_system") as gv:
            gv.return_value.increment_version.side_effect = RuntimeError("boom")
            r = self.client.post("/api/version/increment", json={"bump_type": "major"})
        self.assertEqual(r.status_code, 500)

    def test_changelog(self):
        with patch("orbit.core.version_bp.get_version_system") as gv:
            gv.return_value.get_changelog.return_value = ["v1.0.0"]
            r = self.client.get("/api/version/changelog")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), ["v1.0.0"])

    def test_changelog_error(self):
        with patch("orbit.core.version_bp.get_version_system") as gv:
            gv.return_value.get_changelog.side_effect = RuntimeError("boom")
            r = self.client.get("/api/version/changelog")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
