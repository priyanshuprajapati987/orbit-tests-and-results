"""Unit tests for orbit/orbit/core/learning_safety_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.learning_safety_bp import learning_safety_bp


class TestLearningSafetyBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(learning_safety_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(learning_safety_bp.name, "learning_safety_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/learning-safety/status", "/api/learning-safety/check",
                  "/api/learning-safety/record", "/api/learning-safety/split",
                  "/api/learning-safety/regression", "/api/learning-safety/rollback",
                  "/api/learning-safety/propose"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.learning_safety_bp.get_learning_safety") as gls:
            gls.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/learning-safety/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_check_missing_category_400(self):
        r = self.client.post("/api/learning-safety/check", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_check_success(self):
        with patch("orbit.core.learning_safety_bp.get_learning_safety") as gls:
            gls.return_value.can_adapt.return_value = {"allowed": True}
            r = self.client.post("/api/learning-safety/check", json={"category": "chat"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["allowed"])
        gls.return_value.can_adapt.assert_called_once_with("chat")

    def test_check_no_body(self):
        r = self.client.post("/api/learning-safety/check")
        self.assertEqual(r.status_code, 400)

    def test_record_missing_category_400(self):
        r = self.client.post("/api/learning-safety/record", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_success(self):
        with patch("orbit.core.learning_safety_bp.get_learning_safety") as gls:
            r = self.client.post("/api/learning-safety/record", json={
                "category": "chat", "query": "q", "result": "r", "success": False,
                "latency_ms": 10.5, "metadata": {"k": "v"}
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "recorded")
        gls.return_value.record_sample.assert_called_once_with(
            category="chat", query="q", result="r", success=False, latency_ms=10.5, metadata={"k": "v"}
        )

    def test_record_defaults(self):
        with patch("orbit.core.learning_safety_bp.get_learning_safety") as gls:
            r = self.client.post("/api/learning-safety/record", json={"category": "chat"})
        gls.return_value.record_sample.assert_called_once_with(
            category="chat", query="", result="", success=True, latency_ms=0, metadata=None
        )

    def test_record_no_body(self):
        r = self.client.post("/api/learning-safety/record")
        self.assertEqual(r.status_code, 400)

    def test_split_missing_category_400(self):
        r = self.client.get("/api/learning-safety/split")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_split_success(self):
        with patch("orbit.core.learning_safety_bp.get_learning_safety") as gls:
            gls.return_value.split_samples.return_value = {"train": 8, "test": 2}
            r = self.client.get("/api/learning-safety/split?category=chat")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["train"], 8)
        gls.return_value.split_samples.assert_called_once_with("chat")

    def test_regression_missing_category_400(self):
        r = self.client.get("/api/learning-safety/regression")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_regression_success(self):
        with patch("orbit.core.learning_safety_bp.get_learning_safety") as gls:
            gls.return_value.detect_regression.return_value = {"regressed": False}
            r = self.client.get("/api/learning-safety/regression?category=chat")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["regressed"])
        gls.return_value.detect_regression.assert_called_once_with("chat")

    def test_rollback_missing_id_400(self):
        r = self.client.post("/api/learning-safety/rollback", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_rollback_success(self):
        with patch("orbit.core.learning_safety_bp.get_learning_safety") as gls:
            gls.return_value.rollback_adaptation.return_value = True
            r = self.client.post("/api/learning-safety/rollback", json={"adaptation_id": "a1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        gls.return_value.rollback_adaptation.assert_called_once_with("a1")

    def test_rollback_no_body(self):
        r = self.client.post("/api/learning-safety/rollback")
        self.assertEqual(r.status_code, 400)

    def test_propose_missing_category_400(self):
        r = self.client.post("/api/learning-safety/propose", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_propose_success(self):
        record = patch("orbit.core.learning_safety_bp.get_learning_safety").start()
        rec = MagicMock()
        rec.adaptation_id = "a1"
        rec.status = MagicMock(value="pending")
        rec.risk_level = MagicMock(value="low")
        rec.confidence = 0.9
        record.return_value.propose_adaptation.return_value = rec
        r = self.client.post("/api/learning-safety/propose", json={
            "category": "chat", "description": "d", "before_state": {"x": 1}, "after_state": {"x": 2}
        })
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["adaptation_id"], "a1")
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["risk"], "low")
        self.assertEqual(body["confidence"], 0.9)
        record.return_value.propose_adaptation.assert_called_once_with(
            category="chat", description="d", before_state={"x": 1}, after_state={"x": 2}
        )
        patch.stopall()

    def test_propose_rejected_403(self):
        record = patch("orbit.core.learning_safety_bp.get_learning_safety").start()
        record.return_value.propose_adaptation.return_value = None
        r = self.client.post("/api/learning-safety/propose", json={"category": "chat"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.get_json())
        patch.stopall()

    def test_propose_defaults(self):
        record = patch("orbit.core.learning_safety_bp.get_learning_safety").start()
        record.return_value.propose_adaptation.return_value = None
        r = self.client.post("/api/learning-safety/propose", json={"category": "chat"})
        record.return_value.propose_adaptation.assert_called_once_with(
            category="chat", description="", before_state={}, after_state={}
        )
        patch.stopall()

    def test_propose_no_body(self):
        r = self.client.post("/api/learning-safety/propose")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
