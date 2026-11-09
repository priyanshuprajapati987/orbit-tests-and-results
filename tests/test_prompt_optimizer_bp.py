"""Unit tests for orbit/orbit/core/prompt_optimizer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.prompt_optimizer_bp import prompt_optimizer_bp


class TestPromptOptimizerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(prompt_optimizer_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(prompt_optimizer_bp.name, "prompt_optimizer_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/prompt-optimizer/analyze", "/api/prompt-optimizer/optimize",
                  "/api/prompt-optimizer/detect", "/api/prompt-optimizer/templates",
                  "/api/prompt-optimizer/stats"]:
            self.assertIn(p, rules)

    def _result(self):
        r = MagicMock()
        r.task_type = "code"
        r.task_confidence = 0.9
        r.structure_score = 0.8
        r.clarity_score = 0.7
        r.specificity_score = 0.6
        r.context_score = 0.5
        r.overall_score = 0.7
        r.suggestions = ["s1"]
        r.optimized = "opt prompt"
        r.template_applied = True
        return r

    def test_analyze_missing_prompt_400(self):
        r = self.client.post("/api/prompt-optimizer/analyze", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_analyze_success(self):
        with patch("orbit.core.prompt_optimizer_bp.get_optimizer") as go:
            go.return_value.analyze.return_value = self._result()
            r = self.client.post("/api/prompt-optimizer/analyze", json={"prompt": "write code"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["task_type"], "code")
        self.assertEqual(body["task_confidence"], 0.9)
        self.assertEqual(body["scores"]["overall"], 0.7)
        self.assertEqual(body["suggestions"], ["s1"])
        go.return_value.analyze.assert_called_once_with("write code")

    def test_analyze_no_body(self):
        r = self.client.post("/api/prompt-optimizer/analyze")
        self.assertEqual(r.status_code, 400)

    def test_optimize_missing_prompt_400(self):
        r = self.client.post("/api/prompt-optimizer/optimize", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_optimize_success(self):
        with patch("orbit.core.prompt_optimizer_bp.get_optimizer") as go:
            go.return_value.optimize.return_value = self._result()
            r = self.client.post("/api/prompt-optimizer/optimize", json={"prompt": "write code", "apply_template": False})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["task_type"], "code")
        self.assertEqual(body["optimized"], "opt prompt")
        self.assertTrue(body["template_applied"])
        go.return_value.optimize.assert_called_once_with("write code", False)

    def test_optimize_default_apply_template(self):
        with patch("orbit.core.prompt_optimizer_bp.get_optimizer") as go:
            go.return_value.optimize.return_value = self._result()
            r = self.client.post("/api/prompt-optimizer/optimize", json={"prompt": "write code"})
        go.return_value.optimize.assert_called_once_with("write code", True)

    def test_optimize_no_body(self):
        r = self.client.post("/api/prompt-optimizer/optimize")
        self.assertEqual(r.status_code, 400)

    def test_detect_missing_prompt_400(self):
        r = self.client.post("/api/prompt-optimizer/detect", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_detect_success(self):
        with patch("orbit.core.prompt_optimizer_bp.get_optimizer") as go:
            go.return_value.detect_task_type.return_value = ("code", 0.9)
            r = self.client.post("/api/prompt-optimizer/detect", json={"prompt": "write code"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["task_type"], "code")
        self.assertEqual(body["confidence"], 0.9)
        go.return_value.detect_task_type.assert_called_once_with("write code")

    def test_detect_no_body(self):
        r = self.client.post("/api/prompt-optimizer/detect")
        self.assertEqual(r.status_code, 400)

    def test_templates(self):
        with patch("orbit.core.prompt_optimizer_bp.get_optimizer") as go:
            go.return_value.get_templates.return_value = {"t": 1}
            r = self.client.get("/api/prompt-optimizer/templates")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"t": 1})

    def test_stats(self):
        with patch("orbit.core.prompt_optimizer_bp.get_optimizer") as go:
            go.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/prompt-optimizer/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
