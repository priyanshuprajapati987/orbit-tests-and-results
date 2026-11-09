"""Unit tests for orbit/orbit/core/failure_learner_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.failure_learner_bp import failure_learner_bp


class TestFailureLearnerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(failure_learner_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(failure_learner_bp.name, "failure_learner_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/failures", "/api/failures/log", "/api/failures/search",
                  "/api/failures/solutions", "/api/failures/solutions/add",
                  "/api/failures/solutions/<solution_id>/apply",
                  "/api/failures/solutions/<solution_id>/rate",
                  "/api/failures/solutions/<solution_id>/share", "/api/failures/stats"]:
            self.assertIn(p, rules)

    def test_failures_list(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_failures.return_value = [{"id": 1}]
            r = self.client.get("/api/failures?agent=a&severity=high&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["failures"], [{"id": 1}])
        gf.return_value.get_failures.assert_called_once_with("a", "high", 5)

    def test_failures_list_defaults(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_failures.return_value = []
            r = self.client.get("/api/failures")
        gf.return_value.get_failures.assert_called_once_with(None, None, 50)

    def test_failures_list_invalid_limit(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_failures.return_value = []
            r = self.client.get("/api/failures?limit=abc")
        self.assertEqual(r.status_code, 200)
        gf.return_value.get_failures.assert_called_once_with(None, None, 50)

    def test_failures_list_clamped(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_failures.return_value = []
            r = self.client.get("/api/failures?limit=1000")
        gf.return_value.get_failures.assert_called_once_with(None, None, 500)

    def test_failure_log(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.log_failure.return_value = {"id": "f1"}
            r = self.client.post("/api/failures/log", json={
                "agent": "TAS", "task": "t", "error": "e", "context": {"k": "v"}, "severity": "high"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "f1")
        gf.return_value.log_failure.assert_called_once_with(agent="TAS", task="t", error="e", context={"k": "v"}, severity="high")

    def test_failure_log_defaults(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.log_failure.return_value = {"id": "f2"}
            r = self.client.post("/api/failures/log", json={})
        gf.return_value.log_failure.assert_called_once_with(agent="", task="", error="", context=None, severity="medium")

    def test_failure_log_no_body(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.log_failure.return_value = {"id": "f3"}
            r = self.client.post("/api/failures/log")
        gf.return_value.log_failure.assert_called_once_with(agent="", task="", error="", context=None, severity="medium")

    def test_failure_search(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.find_similar_failures.return_value = [{"id": "f1"}]
            r = self.client.get("/api/failures/search?q=boom&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["matches"], [{"id": "f1"}])
        gf.return_value.find_similar_failures.assert_called_once_with("boom", 5)

    def test_failure_search_defaults(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.find_similar_failures.return_value = []
            r = self.client.get("/api/failures/search")
        gf.return_value.find_similar_failures.assert_called_once_with("", 10)

    def test_failure_search_invalid_limit(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.find_similar_failures.return_value = []
            r = self.client.get("/api/failures/search?limit=abc")
        self.assertEqual(r.status_code, 200)
        gf.return_value.find_similar_failures.assert_called_once_with("", 10)

    def test_failure_search_clamped(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.find_similar_failures.return_value = []
            r = self.client.get("/api/failures/search?limit=1000")
        gf.return_value.find_similar_failures.assert_called_once_with("", 500)

    def test_solutions_list(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_solutions.return_value = [{"id": "s1"}]
            r = self.client.get("/api/failures/solutions?agent=a&limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["solutions"], [{"id": "s1"}])
        gf.return_value.get_solutions.assert_called_once_with("a", 5)

    def test_solutions_list_defaults(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_solutions.return_value = []
            r = self.client.get("/api/failures/solutions")
        gf.return_value.get_solutions.assert_called_once_with(None, 50)

    def test_solutions_list_invalid_limit(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_solutions.return_value = []
            r = self.client.get("/api/failures/solutions?limit=abc")
        self.assertEqual(r.status_code, 200)
        gf.return_value.get_solutions.assert_called_once_with(None, 50)

    def test_solutions_list_clamped(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_solutions.return_value = []
            r = self.client.get("/api/failures/solutions?limit=1000")
        gf.return_value.get_solutions.assert_called_once_with(None, 500)

    def test_solution_add(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.add_solution.return_value = {"id": "s1"}
            r = self.client.post("/api/failures/solutions/add", json={
                "failure_id": "f1", "description": "d", "fix": "fix", "author": "me"
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "s1")
        gf.return_value.add_solution.assert_called_once_with(failure_id="f1", description="d", fix="fix", author="me")

    def test_solution_add_defaults(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.add_solution.return_value = {"id": "s2"}
            r = self.client.post("/api/failures/solutions/add", json={})
        gf.return_value.add_solution.assert_called_once_with(failure_id="", description="", fix="", author="system")

    def test_solution_add_no_body(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.add_solution.return_value = {"id": "s3"}
            r = self.client.post("/api/failures/solutions/add")
        gf.return_value.add_solution.assert_called_once_with(failure_id="", description="", fix="", author="system")

    def test_solution_add_not_found_404(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.add_solution.return_value = None
            r = self.client.post("/api/failures/solutions/add", json={"failure_id": "f1"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_solution_apply(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.apply_solution.return_value = True
            r = self.client.post("/api/failures/solutions/s1/apply")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gf.return_value.apply_solution.assert_called_once_with("s1")

    def test_solution_rate(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.rate_solution.return_value = True
            r = self.client.post("/api/failures/solutions/s1/rate", json={"rating": 4.5})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gf.return_value.rate_solution.assert_called_once_with("s1", 4.5)

    def test_solution_rate_bad_400(self):
        r = self.client.post("/api/failures/solutions/s1/rate", json={"rating": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_solution_rate_no_body(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.rate_solution.return_value = True
            r = self.client.post("/api/failures/solutions/s1/rate")
        gf.return_value.rate_solution.assert_called_once_with("s1", 0.0)

    def test_solution_share(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.share_solution.return_value = {"shared": True}
            r = self.client.post("/api/failures/solutions/s1/share")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["shared"])
        gf.return_value.share_solution.assert_called_once_with("s1")

    def test_solution_share_not_found_404(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.share_solution.return_value = None
            r = self.client.post("/api/failures/solutions/s1/share")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_stats(self):
        with patch("orbit.core.failure_learner_bp.get_failure_learner") as gf:
            gf.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/failures/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
