"""Unit tests for orbit/orbit/core/code_reviewer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.code_reviewer_bp import code_reviewer_bp


class TestCodeReviewerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(code_reviewer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(code_reviewer_bp.name, "code_reviewer")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/code-review/review", "/api/code-review/report/<project_name>",
                  "/api/code-review/list", "/api/code-review/save", "/api/code-review/reset",
                  "/api/code-review/status"]:
            self.assertIn(p, rules)

    def test_review_missing_files_400(self):
        r = self.client.post("/api/code-review/review", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_review_success(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            gr.return_value.review.return_value = {"score": 90}
            r = self.client.post("/api/code-review/review", json={"files": ["a.py"], "project_name": "proj"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["score"], 90)
        gr.return_value.review.assert_called_once_with(["a.py"], "proj")

    def test_review_default_project(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            gr.return_value.review.return_value = {"score": 0}
            r = self.client.post("/api/code-review/review", json={"files": ["a.py"]})
        gr.return_value.review.assert_called_once_with(["a.py"], "unnamed")

    def test_review_exception_500(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            gr.return_value.review.side_effect = RuntimeError("boom")
            r = self.client.post("/api/code-review/review", json={"files": ["a.py"]})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_review_no_body(self):
        r = self.client.post("/api/code-review/review")
        self.assertEqual(r.status_code, 400)

    def test_get_report_found(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            gr.return_value.get_report.return_value = {"project": "p"}
            r = self.client.get("/api/code-review/report/proj")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["project"], "p")
        gr.return_value.get_report.assert_called_once_with("proj")

    def test_get_report_not_found_404(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            gr.return_value.get_report.return_value = None
            r = self.client.get("/api/code-review/report/proj")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_list_reports(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            gr.return_value.list_reports.return_value = ["p1", "p2"]
            r = self.client.get("/api/code-review/list")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["reports"], ["p1", "p2"])
        self.assertEqual(body["count"], 2)

    def test_save_missing_filepath_400(self):
        r = self.client.post("/api/code-review/save", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_invalid_filepath_400(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value=None):
            r = self.client.post("/api/code-review/save", json={"filepath": "../etc/passwd"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_path_not_allowed_403(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value="x.py"), \
             patch("orbit.core._security_utils.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/code-review/save", json={"filepath": "x.py"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_save_success(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value="x.py"), \
             patch("orbit.core._security_utils.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            r = self.client.post("/api/code-review/save", json={"filepath": "x.py"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gr.return_value.save.assert_called_once_with("x.py")

    def test_save_no_body(self):
        r = self.client.post("/api/code-review/save")
        self.assertEqual(r.status_code, 400)

    def test_reset(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            r = self.client.post("/api/code-review/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gr.return_value.reset.assert_called_once()

    def test_status(self):
        with patch("orbit.core.code_reviewer_bp.get_code_reviewer") as gr:
            gr.return_value.list_reports.return_value = ["p1"]
            r = self.client.get("/api/code-review/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["reviewed_projects"], 1)
        self.assertEqual(body["projects"], ["p1"])


if __name__ == "__main__":
    unittest.main()
