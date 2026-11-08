"""Unit tests for orbit/orbit/core/file_organizer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.file_organizer_bp import file_organizer_bp


class TestFileOrganizerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(file_organizer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(file_organizer_bp.name, "file_organizer_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/file-organizer/organize", "/api/file-organizer/duplicates", "/api/file-organizer/stats"]:
            self.assertIn(p, rules)

    def test_organize_blocked_path(self):
        with patch("orbit.core.file_organizer_bp.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/file-organizer/organize", json={"source_dir": "/etc"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_organize_success(self):
        org = MagicMock()
        r1 = MagicMock(); r1.action = "moved"; r1.__dict__ = {"action": "moved"}
        r2 = MagicMock(); r2.action = "skipped"; r2.__dict__ = {"action": "skipped"}
        org.organize.return_value = [r1, r2]
        with patch("orbit.core.file_organizer_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.file_organizer_bp.get_organizer", return_value=org):
            r = self.client.post("/api/file-organizer/organize", json={"source_dir": "/tmp/x", "by_date": True, "dry_run": True})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["moved"], 1)
        self.assertEqual(body["skipped"], 1)
        self.assertTrue(body["dry_run"])
        org.set_base_dir.assert_called_once_with("/tmp/x")
        org.set_dry_run.assert_called_once_with(True)
        org.organize.assert_called_once_with(by_date=True)

    def test_organize_no_source(self):
        org = MagicMock()
        org.organize.return_value = []
        with patch("orbit.core.file_organizer_bp.get_organizer", return_value=org):
            r = self.client.post("/api/file-organizer/organize", json={"by_date": False, "dry_run": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["moved"], 0)
        org.set_base_dir.assert_not_called()
        org.set_dry_run.assert_called_once_with(False)

    def test_organize_exception(self):
        org = MagicMock()
        org.organize.side_effect = RuntimeError("boom")
        with patch("orbit.core.file_organizer_bp.get_organizer", return_value=org):
            r = self.client.post("/api/file-organizer/organize", json={})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_organize_no_body(self):
        org = MagicMock()
        org.organize.return_value = []
        with patch("orbit.core.file_organizer_bp.get_organizer", return_value=org):
            r = self.client.post("/api/file-organizer/organize")
        self.assertEqual(r.status_code, 200)

    def test_duplicates(self):
        org = MagicMock()
        org.find_duplicates.return_value = [{"dup": 1}, {"dup": 2}]
        with patch("orbit.core.file_organizer_bp.get_organizer", return_value=org):
            r = self.client.get("/api/file-organizer/duplicates", json={"source_dir": "/tmp"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["duplicates"]), 2)
        org.find_duplicates.assert_called_once_with("/tmp")

    def test_duplicates_no_source(self):
        org = MagicMock()
        org.find_duplicates.return_value = []
        with patch("orbit.core.file_organizer_bp.get_organizer", return_value=org):
            r = self.client.get("/api/file-organizer/duplicates")
        org.find_duplicates.assert_called_once_with(None)

    def test_stats(self):
        org = MagicMock()
        org.get_stats.return_value = {"total": 5}
        with patch("orbit.core.file_organizer_bp.get_organizer", return_value=org):
            r = self.client.get("/api/file-organizer/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
