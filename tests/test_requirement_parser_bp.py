"""Unit tests for orbit/orbit/core/requirement_parser_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.requirement_parser_bp import requirement_parser_bp


class TestRequirementParserBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(requirement_parser_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(requirement_parser_bp.name, "requirement_parser")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/requirements/parse", "/api/requirements/parsed/<project_name>",
                  "/api/requirements/list", "/api/requirements/save", "/api/requirements/load",
                  "/api/requirements/tech-stack", "/api/requirements/reset", "/api/requirements/status"]:
            self.assertIn(p, rules)

    def test_parse_missing_spec_400(self):
        r = self.client.post("/api/requirements/parse", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_parse_success(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.parse_specification.return_value = {"parsed": True}
            r = self.client.post("/api/requirements/parse", json={"spec": "build app", "project_name": "proj"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["parsed"], True)
        gp.return_value.parse_specification.assert_called_once_with("build app", "proj")

    def test_parse_default_project_name(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.parse_specification.return_value = {"parsed": True}
            r = self.client.post("/api/requirements/parse", json={"spec": "build app"})
        gp.return_value.parse_specification.assert_called_once_with("build app", "unnamed_project")

    def test_parse_no_body(self):
        r = self.client.post("/api/requirements/parse")
        self.assertEqual(r.status_code, 400)

    def test_get_parsed_found(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.get_parsed.return_value = {"project": "p"}
            r = self.client.get("/api/requirements/parsed/proj")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["project"], "p")
        gp.return_value.get_parsed.assert_called_once_with("proj")

    def test_get_parsed_not_found_404(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.get_parsed.return_value = None
            r = self.client.get("/api/requirements/parsed/proj")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_list_parsed(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.list_parsed.return_value = ["p1", "p2"]
            r = self.client.get("/api/requirements/list")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["projects"], ["p1", "p2"])
        self.assertEqual(body["count"], 2)

    def test_save_invalid_filepath_400(self):
        r = self.client.post("/api/requirements/save", json={"filepath": "../etc/passwd"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_invalid_chars_400(self):
        r = self.client.post("/api/requirements/save", json={"filepath": "a/b.txt"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_save_success(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            r = self.client.post("/api/requirements/save", json={"filepath": "out.json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gp.return_value.save.assert_called_once_with("out.json")

    def test_save_no_filepath(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            r = self.client.post("/api/requirements/save", json={})
        gp.return_value.save.assert_called_once_with(None)

    def test_save_no_body(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            r = self.client.post("/api/requirements/save")
        gp.return_value.save.assert_called_once_with(None)

    def test_load_invalid_filepath_400(self):
        r = self.client.post("/api/requirements/load", json={"filepath": "../x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_load_success(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            r = self.client.post("/api/requirements/load", json={"filepath": "in.json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gp.return_value.load.assert_called_once_with("in.json")

    def test_load_no_body(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            r = self.client.post("/api/requirements/load")
        gp.return_value.load.assert_called_once_with(None)

    def test_tech_stack(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.get_tech_stack_recommendation.return_value = {"stack": "flask"}
            r = self.client.post("/api/requirements/tech-stack", json={
                "features": ["auth"], "framework": "flask", "database": "sqlite", "auth": "jwt"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["stack"], "flask")
        gp.return_value.get_tech_stack_recommendation.assert_called_once_with(
            features=["auth"], framework="flask", database="sqlite", auth="jwt"
        )

    def test_tech_stack_defaults(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.get_tech_stack_recommendation.return_value = {}
            r = self.client.post("/api/requirements/tech-stack", json={})
        gp.return_value.get_tech_stack_recommendation.assert_called_once_with(
            features=[], framework="flask", database="sqlite", auth="none"
        )

    def test_tech_stack_no_body(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.get_tech_stack_recommendation.return_value = {}
            r = self.client.post("/api/requirements/tech-stack")
        gp.return_value.get_tech_stack_recommendation.assert_called_once_with(
            features=[], framework="flask", database="sqlite", auth="none"
        )

    def test_reset(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            r = self.client.post("/api/requirements/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gp.return_value.reset.assert_called_once()

    def test_status(self):
        with patch("orbit.core.requirement_parser_bp.get_requirement_parser") as gp:
            gp.return_value.list_parsed.return_value = ["p1", "p2"]
            r = self.client.get("/api/requirements/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["parsed_projects"], 2)
        self.assertEqual(body["projects"], ["p1", "p2"])


if __name__ == "__main__":
    unittest.main()
