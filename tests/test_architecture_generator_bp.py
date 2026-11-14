"""Unit tests for orbit/orbit/core/architecture_generator_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.architecture_generator_bp import architecture_generator_bp


class TestArchitectureGeneratorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(architecture_generator_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(architecture_generator_bp.name, "architecture_generator")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/architecture/generate", "/api/architecture/plan/<project_name>",
                  "/api/architecture/list", "/api/architecture/save", "/api/architecture/load",
                  "/api/architecture/reset", "/api/architecture/status"]:
            self.assertIn(p, rules)

    def test_generate_missing_spec_400(self):
        r = self.client.post("/api/architecture/generate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_generate_missing_project_name_400(self):
        r = self.client.post("/api/architecture/generate", json={"parsed_spec": {}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_generate_success(self):
        with patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            gg.return_value.generate.return_value = {"plan": "x"}
            r = self.client.post("/api/architecture/generate", json={"parsed_spec": {"project_name": "p"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["plan"], "x")
        gg.return_value.generate.assert_called_once_with({"project_name": "p"})

    def test_generate_exception_500(self):
        with patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            gg.return_value.generate.side_effect = RuntimeError("boom")
            r = self.client.post("/api/architecture/generate", json={"parsed_spec": {"project_name": "p"}})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_generate_no_body(self):
        r = self.client.post("/api/architecture/generate")
        self.assertEqual(r.status_code, 400)

    def test_get_plan_found(self):
        with patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            gg.return_value.get_plan.return_value = {"plan": "p"}
            r = self.client.get("/api/architecture/plan/proj")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["plan"], "p")
        gg.return_value.get_plan.assert_called_once_with("proj")

    def test_get_plan_not_found_404(self):
        with patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            gg.return_value.get_plan.return_value = None
            r = self.client.get("/api/architecture/plan/proj")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_list_plans(self):
        with patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            gg.return_value.list_plans.return_value = ["p1", "p2"]
            r = self.client.get("/api/architecture/list")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["plans"], ["p1", "p2"])
        self.assertEqual(body["count"], 2)

    def test_save_missing_filepath_400(self):
        r = self.client.post("/api/architecture/save", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_invalid_filepath_400(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value=None):
            r = self.client.post("/api/architecture/save", json={"filepath": "../etc/passwd"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_path_not_allowed_403(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value="x.json"), \
             patch("orbit.core._security_utils.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/architecture/save", json={"filepath": "x.json"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_save_success(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value="x.json"), \
             patch("orbit.core._security_utils.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            r = self.client.post("/api/architecture/save", json={"filepath": "x.json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gg.return_value.save.assert_called_once_with("x.json")

    def test_save_no_body(self):
        r = self.client.post("/api/architecture/save")
        self.assertEqual(r.status_code, 400)

    def test_load_missing_filepath_400(self):
        r = self.client.post("/api/architecture/load", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_load_invalid_filepath_400(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value=None):
            r = self.client.post("/api/architecture/load", json={"filepath": "../x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_load_path_not_allowed_403(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value="x.json"), \
             patch("orbit.core._security_utils.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/architecture/load", json={"filepath": "x.json"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())

    def test_load_success(self):
        with patch("orbit.core._security_utils.sanitize_filepath", return_value="x.json"), \
             patch("orbit.core._security_utils.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            r = self.client.post("/api/architecture/load", json={"filepath": "x.json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gg.return_value.load.assert_called_once_with("x.json")

    def test_load_no_body(self):
        r = self.client.post("/api/architecture/load")
        self.assertEqual(r.status_code, 400)

    def test_reset(self):
        with patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            r = self.client.post("/api/architecture/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gg.return_value.reset.assert_called_once()

    def test_status(self):
        with patch("orbit.core.architecture_generator_bp.get_architecture_generator") as gg:
            gg.return_value.list_plans.return_value = ["p1", "p2"]
            r = self.client.get("/api/architecture/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["planned_projects"], 2)
        self.assertEqual(body["plans"], ["p1", "p2"])


if __name__ == "__main__":
    unittest.main()
