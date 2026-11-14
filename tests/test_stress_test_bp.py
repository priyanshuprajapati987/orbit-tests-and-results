"""Unit tests for orbit/orbit/core/stress_test_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.stress_test_bp import stress_test_bp


def make_result(**kw):
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class TestStressTestBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(stress_test_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(stress_test_bp.name, "stress_test_bp")

    def test_status(self):
        r = self.client.get("/api/stress/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("concurrent_conversations", body["available_tests"])
        self.assertIn("rate_limiter_load", body["available_tests"])

    def test_run_unknown_400(self):
        r = self.client.post("/api/stress/run", json={"test": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_run_no_body_runs_all(self):
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.run_all.return_value = {"summary": "ok"}
            r = self.client.post("/api/stress/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"summary": "ok"})

    def test_run_all_empty_test_name_runs_all(self):
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.run_all.return_value = {"summary": "ok"}
            r = self.client.post("/api/stress/run", json={"test": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"summary": "ok"})

    def test_run_concurrent_conversations(self):
        result = make_result(test_name="concurrent_conversations", status="pass", total_operations=100,
                            successful=99, failed=1, avg_latency_ms=5.0, max_latency_ms=10.0,
                            p95_latency_ms=8.0, duration_seconds=1.5, errors=[], details={})
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.test_concurrent_conversations.return_value = result
            r = self.client.post("/api/stress/run", json={"test": "concurrent_conversations", "threads": 5, "ops": 3})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["test"], "concurrent_conversations")
        self.assertEqual(body["status"], "pass")
        self.assertEqual(body["total_operations"], 100)
        self.assertEqual(body["successful"], 99)
        self.assertEqual(body["failed"], 1)
        self.assertEqual(body["avg_latency_ms"], 5.0)
        self.assertEqual(body["max_latency_ms"], 10.0)
        self.assertEqual(body["p95_latency_ms"], 8.0)
        self.assertEqual(body["duration_seconds"], 1.5)
        self.assertEqual(body["errors"], [])
        self.assertEqual(body["details"], {})
        gs.return_value.test_concurrent_conversations.assert_called_once_with(num_threads=5, ops_per_thread=3)

    def test_run_parallel_agents(self):
        result = make_result(test_name="parallel_agents", status="pass", total_operations=10,
                            successful=10, failed=0, avg_latency_ms=1.0, max_latency_ms=2.0,
                            p95_latency_ms=1.5, duration_seconds=0.5, errors=[], details={})
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.test_parallel_agents.return_value = result
            r = self.client.post("/api/stress/run", json={"test": "parallel_agents", "agents": 4, "ops": 2})
        self.assertEqual(r.status_code, 200)
        gs.return_value.test_parallel_agents.assert_called_once_with(num_agents=4, ops_per_agent=2)

    def test_run_memory_router_operations(self):
        result = make_result(test_name="memory_router_operations", status="pass", total_operations=10,
                            successful=10, failed=0, avg_latency_ms=1.0, max_latency_ms=2.0,
                            p95_latency_ms=1.5, duration_seconds=0.5, errors=[], details={})
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.test_memory_router_operations.return_value = result
            r = self.client.post("/api/stress/run", json={"test": "memory_router_operations", "ops": 7})
        self.assertEqual(r.status_code, 200)
        gs.return_value.test_memory_router_operations.assert_called_once_with(num_operations=7)

    def test_run_file_contention(self):
        result = make_result(test_name="file_contention", status="pass", total_operations=10,
                            successful=10, failed=0, avg_latency_ms=1.0, max_latency_ms=2.0,
                            p95_latency_ms=1.5, duration_seconds=0.5, errors=[], details={})
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.test_file_contention.return_value = result
            r = self.client.post("/api/stress/run", json={"test": "file_contention", "threads": 3, "ops": 4})
        self.assertEqual(r.status_code, 200)
        gs.return_value.test_file_contention.assert_called_once_with(num_threads=3, ops_per_thread=4)

    def test_run_singleton_dcl_safety(self):
        result = make_result(test_name="singleton_dcl_safety", status="pass", total_operations=10,
                            successful=10, failed=0, avg_latency_ms=1.0, max_latency_ms=2.0,
                            p95_latency_ms=1.5, duration_seconds=0.5, errors=[], details={})
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.test_singleton_safety.return_value = result
            r = self.client.post("/api/stress/run", json={"test": "singleton_dcl_safety", "threads": 6})
        self.assertEqual(r.status_code, 200)
        gs.return_value.test_singleton_safety.assert_called_once_with(num_threads=6)

    def test_run_rate_limiter_load(self):
        result = make_result(test_name="rate_limiter_load", status="pass", total_operations=10,
                            successful=10, failed=0, avg_latency_ms=1.0, max_latency_ms=2.0,
                            p95_latency_ms=1.5, duration_seconds=0.5, errors=[], details={})
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.test_rate_limiter_load.return_value = result
            r = self.client.post("/api/stress/run", json={"test": "rate_limiter_load", "threads": 2, "burst": 10})
        self.assertEqual(r.status_code, 200)
        gs.return_value.test_rate_limiter_load.assert_called_once_with(num_threads=2, burst=10)

    def test_run_clamping(self):
        result = make_result(test_name="concurrent_conversations", status="pass", total_operations=1,
                            successful=1, failed=0, avg_latency_ms=1.0, max_latency_ms=2.0,
                            p95_latency_ms=1.5, duration_seconds=0.5, errors=[], details={})
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.test_concurrent_conversations.return_value = result
            r = self.client.post("/api/stress/run", json={"test": "concurrent_conversations", "threads": 0, "ops": 100})
        gs.return_value.test_concurrent_conversations.assert_called_once_with(num_threads=1, ops_per_thread=50)

    def test_run_no_body_runs_all(self):
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.run_all.return_value = {"summary": "ok"}
            r = self.client.post("/api/stress/run")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"summary": "ok"})

    def test_run_all_endpoint(self):
        with patch("orbit.core.stress_test_bp.get_stress_suite") as gs:
            gs.return_value.run_all.return_value = {"summary": "all"}
            r = self.client.post("/api/stress/run-all")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"summary": "all"})


if __name__ == "__main__":
    unittest.main()
