"""Unit tests for orbit/orbit/core/prompt_evolver_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.prompt_evolver_bp import prompt_evolver_bp


class TestPromptEvolverBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(prompt_evolver_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(prompt_evolver_bp.name, "prompt_evolver_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/prompts/variations", "/api/prompts/variations/<variation_id>",
                  "/api/prompts/variations/<variation_id>/results", "/api/prompts/trials/record",
                  "/api/prompts/decide", "/api/prompts/stats"]:
            self.assertIn(p, rules)

    def test_variations_list(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_variations.return_value = [{"id": "v1"}]
            r = self.client.get("/api/prompts/variations?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["variations"], [{"id": "v1"}])
        gp.return_value.get_variations.assert_called_once_with(5)

    def test_variations_list_default(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_variations.return_value = []
            r = self.client.get("/api/prompts/variations")
        gp.return_value.get_variations.assert_called_once_with(50)

    def test_variations_list_invalid_limit(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_variations.return_value = []
            r = self.client.get("/api/prompts/variations?limit=abc")
        self.assertEqual(r.status_code, 200)
        gp.return_value.get_variations.assert_called_once_with(50)

    def test_variations_list_clamped(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_variations.return_value = []
            r = self.client.get("/api/prompts/variations?limit=1000")
        gp.return_value.get_variations.assert_called_once_with(500)

    def test_variations_create(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.register_variation.return_value = {"id": "v1"}
            r = self.client.post("/api/prompts/variations", json={
                "task": "t", "prompt_a": "a", "prompt_b": "b", "tags": ["x"]
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "v1")
        gp.return_value.register_variation.assert_called_once_with(task="t", prompt_a="a", prompt_b="b", tags=["x"])

    def test_variations_create_defaults(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.register_variation.return_value = {"id": "v2"}
            r = self.client.post("/api/prompts/variations", json={})
        gp.return_value.register_variation.assert_called_once_with(task="", prompt_a="", prompt_b="", tags=None)

    def test_variations_create_no_body(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.register_variation.return_value = {"id": "v3"}
            r = self.client.post("/api/prompts/variations")
        gp.return_value.register_variation.assert_called_once_with(task="", prompt_a="", prompt_b="", tags=None)

    def test_variation_detail_found(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_variation.return_value = {"id": "v1"}
            r = self.client.get("/api/prompts/variations/v1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "v1")
        gp.return_value.get_variation.assert_called_once_with("v1")

    def test_variation_detail_not_found_404(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_variation.return_value = None
            r = self.client.get("/api/prompts/variations/v1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_variation_results_found(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_results.return_value = {"results": [1]}
            r = self.client.get("/api/prompts/variations/v1/results")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["results"], [1])
        gp.return_value.get_results.assert_called_once_with("v1")

    def test_variation_results_not_found_404(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_results.return_value = None
            r = self.client.get("/api/prompts/variations/v1/results")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_trial_record_success(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.record_trial.return_value = {"trial": 1}
            r = self.client.post("/api/prompts/trials/record", json={
                "variation_id": "v1", "version": "A", "score": "0.9", "latency_ms": "100", "metadata": {"k": "v"}
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["trial"], 1)
        gp.return_value.record_trial.assert_called_once_with(variation_id="v1", version="A", score=0.9, latency_ms=100.0, metadata={"k": "v"})

    def test_trial_record_bad_score_400(self):
        r = self.client.post("/api/prompts/trials/record", json={"variation_id": "v1", "score": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_trial_record_bad_latency_400(self):
        r = self.client.post("/api/prompts/trials/record", json={"variation_id": "v1", "latency_ms": "xyz"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_trial_record_not_found_404(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.record_trial.return_value = None
            r = self.client.post("/api/prompts/trials/record", json={"variation_id": "v1"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_trial_record_no_body(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.record_trial.return_value = {"trial": 1}
            r = self.client.post("/api/prompts/trials/record")
        gp.return_value.record_trial.assert_called_once_with(variation_id="", version="A", score=0.0, latency_ms=0.0, metadata=None)

    def test_decide(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.decide_variation.return_value = "A"
            r = self.client.get("/api/prompts/decide?task=t")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["decision"], "A")
        gp.return_value.decide_variation.assert_called_once_with("t")

    def test_decide_default_task(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.decide_variation.return_value = None
            r = self.client.get("/api/prompts/decide")
        gp.return_value.decide_variation.assert_called_once_with("")

    def test_stats(self):
        with patch("orbit.core.prompt_evolver_bp.get_prompt_evolver") as gp:
            gp.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/prompts/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
