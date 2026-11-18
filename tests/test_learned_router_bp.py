"""Unit tests for orbit/orbit/core/learned_router_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.learned_router_bp import learned_router_bp


def _mock_router():
    router = MagicMock()
    router.router_type = "routellm"
    router.threshold = 0.5
    router.strong_model = "gpt-4o"
    router.weak_model = "llama"
    router.get_status.return_value = {"router_type": "routellm", "threshold": 0.5}
    decision = MagicMock()
    decision.to_dict.return_value = {"use_strong": True, "confidence": 0.9}
    router.route.return_value = decision
    router.calibrate.return_value = 0.42
    return router


class LearnedRouterBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(learned_router_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(learned_router_bp.name, "learned_router_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/learned-router/status", "/api/learned-router/route",
                  "/api/learned-router/calibrate", "/api/learned-router/config",
                  "/api/learned-router/batch"]:
            self.assertIn(p, rules)


class TestStatus(LearnedRouterBpBase):
    def test_status(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.get("/api/learned-router/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["router_type"], "routellm")

    def test_status_exception_500(self):
        with patch("orbit.core.learned_router.get_learned_router", side_effect=RuntimeError("x")):
            r = self.client.get("/api/learned-router/status")
        self.assertEqual(r.status_code, 500)


class TestRoute(LearnedRouterBpBase):
    def test_route_success(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/route", json={"query": "hello"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["use_strong"])
        router.route.assert_called_once_with("hello", threshold=None)

    def test_route_with_threshold(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/route", json={"query": "x", "threshold": 0.7})
        router.route.assert_called_once_with("x", threshold=0.7)

    def test_route_missing_query_400(self):
        r = self.client.post("/api/learned-router/route", json={"threshold": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("query is required", r.get_json()["error"])

    def test_route_no_body_400(self):
        r = self.client.post("/api/learned-router/route")
        self.assertEqual(r.status_code, 400)


class TestCalibrate(LearnedRouterBpBase):
    def test_calibrate_default(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/calibrate", json={})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["threshold"], 0.42)
        self.assertEqual(body["strong_model_pct"], 0.5)
        self.assertEqual(body["router_type"], "routellm")
        router.calibrate.assert_called_once_with(0.5)

    def test_calibrate_explicit(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/calibrate", json={"strong_model_pct": 0.8})
        router.calibrate.assert_called_once_with(0.8)

    def test_calibrate_string_number(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/calibrate", json={"strong_model_pct": "0.3"})
        router.calibrate.assert_called_once_with(0.3)

    def test_calibrate_bad_number_400(self):
        r = self.client.post("/api/learned-router/calibrate", json={"strong_model_pct": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("must be a number", r.get_json()["error"])

    def test_calibrate_none_400(self):
        r = self.client.post("/api/learned-router/calibrate", json={"strong_model_pct": None})
        self.assertEqual(r.status_code, 400)

    def test_calibrate_out_of_range_low_400(self):
        r = self.client.post("/api/learned-router/calibrate", json={"strong_model_pct": -0.1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("0.0-1.0", r.get_json()["error"])

    def test_calibrate_out_of_range_high_400(self):
        r = self.client.post("/api/learned-router/calibrate", json={"strong_model_pct": 1.5})
        self.assertEqual(r.status_code, 400)

    def test_calibrate_no_body(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/calibrate")
        self.assertEqual(r.status_code, 200)


class TestConfig(LearnedRouterBpBase):
    def test_config_full(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/config", json={
                "router_type": "simple", "threshold": 0.6,
                "strong_model": "gpt-5", "weak_model": "mistral",
            })
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "updated")
        self.assertEqual(router.router_type, "simple")
        self.assertEqual(router.threshold, 0.6)
        self.assertEqual(router.strong_model, "gpt-5")
        self.assertEqual(router.weak_model, "mistral")
        self.assertIsNone(router._controller)

    def test_config_partial(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/config", json={"threshold": 0.9})
        self.assertEqual(router.threshold, 0.9)
        # untouched fields keep values
        self.assertEqual(router.router_type, "routellm")

    def test_config_bad_threshold_400(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/config", json={"threshold": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("threshold must be a number", r.get_json()["error"])

    def test_config_none_threshold_400(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/config", json={"threshold": None})
        self.assertEqual(r.status_code, 400)

    def test_config_empty_body(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/config", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "updated")
        self.assertIsNone(router._controller)


class TestBatch(LearnedRouterBpBase):
    def test_batch_success(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/batch", json={"queries": ["a", "b", "c"]})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["summary"]["total"], 3)
        self.assertEqual(body["summary"]["strong"], 3)  # mock always True
        self.assertEqual(body["summary"]["weak"], 0)
        self.assertEqual(body["summary"]["strong_pct"], 100.0)
        self.assertEqual(router.route.call_count, 3)

    def test_batch_threshold_propagated(self):
        router = _mock_router()
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/batch", json={"queries": ["a"], "threshold": 0.3})
        router.route.assert_called_once_with("a", threshold=0.3)

    def test_batch_caps_at_50(self):
        router = _mock_router()
        queries = [f"q{i}" for i in range(60)]
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/batch", json={"queries": queries})
        self.assertEqual(r.get_json()["summary"]["total"], 50)
        self.assertEqual(router.route.call_count, 50)

    def test_batch_empty_400(self):
        r = self.client.post("/api/learned-router/batch", json={"queries": []})
        self.assertEqual(r.status_code, 400)
        self.assertIn("queries list is required", r.get_json()["error"])

    def test_batch_no_body_400(self):
        r = self.client.post("/api/learned-router/batch")
        self.assertEqual(r.status_code, 400)

    def test_batch_mixed_strong_weak(self):
        router = _mock_router()
        # alternate strong True/False
        outs = [{"use_strong": True}, {"use_strong": False}, {"use_strong": True}, {"use_strong": False}]
        decision_mocks = []
        for o in outs:
            d = MagicMock()
            d.to_dict.return_value = o
            decision_mocks.append(d)
        router.route.side_effect = decision_mocks
        with patch("orbit.core.learned_router.get_learned_router", return_value=router):
            r = self.client.post("/api/learned-router/batch", json={"queries": ["a", "b", "c", "d"]})
        s = r.get_json()["summary"]
        self.assertEqual(s["strong"], 2)
        self.assertEqual(s["weak"], 2)
        self.assertEqual(s["strong_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
