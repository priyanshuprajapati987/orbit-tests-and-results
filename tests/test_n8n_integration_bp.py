"""Unit tests for orbit/orbit/core/n8n_integration_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.n8n_integration_bp import n8n_integration_bp


class TestN8nIntegrationBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(n8n_integration_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(n8n_integration_bp.name, "n8n_integration")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/n8n/status", "/api/n8n/templates", "/api/n8n/trigger",
                  "/api/n8n/trigger/<template_id>", "/api/n8n/template/new",
                  "/api/n8n/template/<tid>/toggle", "/api/n8n/template/<tid>",
                  "/api/n8n/runs"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.get_status.return_value = {"online": True}
            r = self.client.get("/api/n8n/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["online"])

    def test_status_error(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.get_status.side_effect = RuntimeError("boom")
            r = self.client.get("/api/n8n/status")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_templates(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.list_templates.return_value = ["t1"]
            r = self.client.get("/api/n8n/templates")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["templates"], ["t1"])

    def test_templates_error(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.list_templates.side_effect = RuntimeError("boom")
            r = self.client.get("/api/n8n/templates")
        self.assertEqual(r.status_code, 500)

    def test_trigger_missing_tid_400(self):
        r = self.client.post("/api/n8n/trigger", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_trigger_success(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.trigger_workflow.return_value = {"triggered": True}
            r = self.client.post("/api/n8n/trigger", json={"template_id": "t1", "payload": {"x": 1}})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["triggered"])
        gn.return_value.trigger_workflow.assert_called_once_with("t1", {"x": 1})

    def test_trigger_via_path(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.trigger_workflow.return_value = {"triggered": True}
            r = self.client.post("/api/n8n/trigger/t2", json={"payload": {"y": 2}})
        self.assertEqual(r.status_code, 200)
        gn.return_value.trigger_workflow.assert_called_once_with("t2", {"y": 2})

    def test_trigger_no_body(self):
        r = self.client.post("/api/n8n/trigger")
        self.assertEqual(r.status_code, 400)

    def test_trigger_error(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.trigger_workflow.side_effect = RuntimeError("boom")
            r = self.client.post("/api/n8n/trigger", json={"template_id": "t1"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_new_template(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.create_template.return_value = {"id": "t1"}
            r = self.client.post("/api/n8n/template/new", json={
                "name": "n", "description": "d", "trigger": "webhook", "nodes": [1, 2]
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "t1")
        gn.return_value.create_template.assert_called_once_with(name="n", description="d", trigger="webhook", nodes=[1, 2])

    def test_new_template_defaults(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.create_template.return_value = {"id": "t2"}
            r = self.client.post("/api/n8n/template/new", json={})
        gn.return_value.create_template.assert_called_once_with(name="", description="", trigger="webhook", nodes=None)

    def test_new_template_no_body(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.create_template.return_value = {"id": "t3"}
            r = self.client.post("/api/n8n/template/new")
        gn.return_value.create_template.assert_called_once_with(name="", description="", trigger="webhook", nodes=None)

    def test_new_template_error(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.create_template.side_effect = RuntimeError("boom")
            r = self.client.post("/api/n8n/template/new", json={"name": "n"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_toggle_found(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.toggle_template.return_value = True
            r = self.client.post("/api/n8n/template/t1/toggle")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertTrue(r.get_json()["active"])
        gn.return_value.toggle_template.assert_called_once_with("t1")

    def test_toggle_not_found_404(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.toggle_template.return_value = None
            r = self.client.post("/api/n8n/template/t1/toggle")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_toggle_error(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.toggle_template.side_effect = RuntimeError("boom")
            r = self.client.post("/api/n8n/template/t1/toggle")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_delete_found(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.delete_template.return_value = True
            r = self.client.delete("/api/n8n/template/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gn.return_value.delete_template.assert_called_once_with("t1")

    def test_delete_not_found_404(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.delete_template.return_value = False
            r = self.client.delete("/api/n8n/template/t1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_delete_error(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.delete_template.side_effect = RuntimeError("boom")
            r = self.client.delete("/api/n8n/template/t1")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_runs(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.get_run_log.return_value = [{"id": 1}]
            r = self.client.get("/api/n8n/runs")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["runs"], [{"id": 1}])

    def test_runs_error(self):
        with patch("orbit.core.n8n_integration_bp.get_n8n_integration") as gn:
            gn.return_value.get_run_log.side_effect = RuntimeError("boom")
            r = self.client.get("/api/n8n/runs")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
