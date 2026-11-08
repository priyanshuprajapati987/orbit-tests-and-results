"""Unit tests for orbit/orbit/core/anomaly_detector_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.anomaly_detector_bp import anomaly_detector_bp


class TestAnomalyDetectorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(anomaly_detector_bp)
        self.client = self.app.test_client()
        self.fake = MagicMock()
        sys.modules["orbit.orbit.core.anomaly_detector"] = self.fake

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.anomaly_detector", None)

    def test_blueprint_name(self):
        self.assertEqual(anomaly_detector_bp.name, "anomaly_detector")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/anomaly/record", "/api/anomaly/batch", "/api/anomaly/anomalies",
                  "/api/anomaly/acknowledge", "/api/anomaly/baselines", "/api/anomaly/stats"]:
            self.assertIn(p, rules)

    def test_record_missing_400(self):
        r = self.client.post("/api/anomaly/record", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_record_no_anomaly(self):
        self.fake.get_anomaly_detector.return_value.record.return_value = None
        r = self.client.post("/api/anomaly/record", json={"metric": "cpu", "value": 50.0})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["anomaly"])
        self.assertEqual(r.get_json()["metric"], "cpu")
        self.fake.get_anomaly_detector.return_value.record.assert_called_once_with("cpu", 50.0)

    def test_record_anomaly(self):
        anomaly = MagicMock()
        anomaly.anomaly_id = "a1"
        anomaly.severity = "high"
        anomaly.deviation_score = 3.5
        anomaly.description = "spike"
        self.fake.get_anomaly_detector.return_value.record.return_value = anomaly
        r = self.client.post("/api/anomaly/record", json={"metric": "cpu", "value": "50"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["anomaly"])
        self.assertEqual(body["anomaly_id"], "a1")
        self.assertEqual(body["severity"], "high")
        self.assertEqual(body["z_score"], 3.5)
        self.assertEqual(body["description"], "spike")
        self.fake.get_anomaly_detector.return_value.record.assert_called_once_with("cpu", 50.0)

    def test_record_no_body(self):
        r = self.client.post("/api/anomaly/record")
        self.assertEqual(r.status_code, 400)

    def test_batch_missing_400(self):
        r = self.client.post("/api/anomaly/batch", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_batch_success(self):
        a = MagicMock()
        a.metric_name = "cpu"
        a.severity = "high"
        a.deviation_score = 2.0
        self.fake.get_anomaly_detector.return_value.record_batch.return_value = [a]
        r = self.client.post("/api/anomaly/batch", json={"metrics": {"cpu": 90, "mem": 50}})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["anomalies_found"], 1)
        self.assertEqual(body["details"], [{"metric": "cpu", "severity": "high", "z_score": 2.0}])
        self.fake.get_anomaly_detector.return_value.record_batch.assert_called_once_with({"cpu": 90.0, "mem": 50.0})

    def test_batch_no_body(self):
        r = self.client.post("/api/anomaly/batch")
        self.assertEqual(r.status_code, 400)

    def test_anomalies(self):
        self.fake.get_anomaly_detector.return_value.get_anomalies.return_value = [{"id": "a1"}]
        r = self.client.get("/api/anomaly/anomalies?severity=high&limit=10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["anomalies"], [{"id": "a1"}])
        self.fake.get_anomaly_detector.return_value.get_anomalies.assert_called_once_with("high", 10)

    def test_anomalies_defaults(self):
        self.fake.get_anomaly_detector.return_value.get_anomalies.return_value = []
        r = self.client.get("/api/anomaly/anomalies")
        self.fake.get_anomaly_detector.return_value.get_anomalies.assert_called_once_with(None, 50)

    def test_ack_missing_400(self):
        r = self.client.post("/api/anomaly/acknowledge", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_ack_success(self):
        self.fake.get_anomaly_detector.return_value.acknowledge.return_value = True
        r = self.client.post("/api/anomaly/acknowledge", json={"anomaly_id": "a1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["acknowledged"])
        self.fake.get_anomaly_detector.return_value.acknowledge.assert_called_once_with("a1")

    def test_ack_no_body(self):
        r = self.client.post("/api/anomaly/acknowledge")
        self.assertEqual(r.status_code, 400)

    def test_baselines(self):
        self.fake.get_anomaly_detector.return_value.get_baselines.return_value = {"cpu": 50}
        r = self.client.get("/api/anomaly/baselines")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["baselines"], {"cpu": 50})

    def test_stats(self):
        self.fake.get_anomaly_detector.return_value.get_stats.return_value = {"total": 3}
        r = self.client.get("/api/anomaly/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 3)


if __name__ == "__main__":
    unittest.main()
