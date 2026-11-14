"""Unit tests for orbit/orbit/core/code_integrator_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.code_integrator_bp import code_integrator_bp


class TestCodeIntegratorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(code_integrator_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(code_integrator_bp.name, "code_integrator")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/code-integrate/integrate", "/api/code-integrate/report/<project_name>",
                  "/api/code-integrate/list", "/api/code-integrate/save", "/api/code-integrate/reset",
                  "/api/code-integrate/status"]:
            self.assertIn(p, rules)

    def test_integrate_missing_files_400(self):
        r = self.client.post("/api/code-integrate/integrate", json={"target_dir": "/tmp"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_integrate_missing_target_dir_400(self):
        r = self.client.post("/api/code-integrate/integrate", json={"files": ["a.py"]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_integrate_blocked_path_403(self):
        with patch("orbit.core.code_integrator_bp.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/code-integrate/integrate", json={"files": ["a.py"], "target_dir": "/etc"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_integrate_success(self):
        with patch("orbit.core.code_integrator_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.integrate.return_value = {"integrated": 1}
            r = self.client.post("/api/code-integrate/integrate", json={
                "files": ["a.py"], "target_dir": "/tmp", "project_name": "proj",
                "skip_existing": False, "run_tests": True
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["integrated"], 1)
        gi.return_value.integrate.assert_called_once_with(["a.py"], "/tmp", "proj", False, True)

    def test_integrate_defaults(self):
        with patch("orbit.core.code_integrator_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.integrate.return_value = {"integrated": 0}
            r = self.client.post("/api/code-integrate/integrate", json={"files": ["a.py"], "target_dir": "/tmp"})
        gi.return_value.integrate.assert_called_once_with(["a.py"], "/tmp", "unnamed", True, False)

    def test_integrate_exception_500(self):
        with patch("orbit.core.code_integrator_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.integrate.side_effect = RuntimeError("boom")
            r = self.client.post("/api/code-integrate/integrate", json={"files": ["a.py"], "target_dir": "/tmp"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_integrate_no_body(self):
        r = self.client.post("/api/code-integrate/integrate")
        self.assertEqual(r.status_code, 400)

    def test_get_report_found(self):
        with patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.get_report.return_value = {"project": "p"}
            r = self.client.get("/api/code-integrate/report/proj")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["project"], "p")
        gi.return_value.get_report.assert_called_once_with("proj")

    def test_get_report_not_found_404(self):
        with patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.get_report.return_value = None
            r = self.client.get("/api/code-integrate/report/proj")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_list_reports(self):
        with patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.list_reports.return_value = ["p1", "p2"]
            r = self.client.get("/api/code-integrate/list")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["reports"], ["p1", "p2"])
        self.assertEqual(body["count"], 2)

    def test_save_missing_filepath_400(self):
        r = self.client.post("/api/code-integrate/save", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_invalid_filepath_400(self):
        with patch("orbit.core.code_integrator_bp.sanitize_filepath", return_value=None):
            r = self.client.post("/api/code-integrate/save", json={"filepath": "../etc/passwd"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_path_not_allowed_403(self):
        with patch("orbit.core.code_integrator_bp.sanitize_filepath", return_value="x.py"), \
             patch("orbit.core.code_integrator_bp.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/code-integrate/save", json={"filepath": "x.py"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_save_success(self):
        with patch("orbit.core.code_integrator_bp.sanitize_filepath", return_value="x.py"), \
             patch("orbit.core.code_integrator_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            r = self.client.post("/api/code-integrate/save", json={"filepath": "x.py"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gi.return_value.save.assert_called_once_with("x.py")

    def test_save_exception_500(self):
        with patch("orbit.core.code_integrator_bp.sanitize_filepath", return_value="x.py"), \
             patch("orbit.core.code_integrator_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.save.side_effect = RuntimeError("boom")
            r = self.client.post("/api/code-integrate/save", json={"filepath": "x.py"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_save_no_body(self):
        r = self.client.post("/api/code-integrate/save")
        self.assertEqual(r.status_code, 400)

    def test_reset(self):
        with patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            r = self.client.post("/api/code-integrate/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gi.return_value.reset.assert_called_once()

    def test_status(self):
        with patch("orbit.core.code_integrator_bp.get_code_integrator") as gi:
            gi.return_value.list_reports.return_value = ["p1"]
            r = self.client.get("/api/code-integrate/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["integrated_projects"], 1)
        self.assertEqual(body["projects"], ["p1"])


if __name__ == "__main__":
    unittest.main()
