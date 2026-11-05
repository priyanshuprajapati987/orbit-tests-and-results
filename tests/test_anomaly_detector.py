"""Tests for Anomaly Detector (System 10)"""

import os
import tempfile
import unittest


class TestAnomalyDetector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)  # noqa: SIM115
        self.path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def _get_ad(self):
        from orbit.orbit.core.anomaly_detector import AnomalyDetector

        return AnomalyDetector(storage_file=self.path)

    def test_import(self):
        from orbit.orbit.core.anomaly_detector import (
            get_anomaly_detector,
        )

        self.assertTrue(callable(get_anomaly_detector))

    def test_record_normal(self):
        ad = self._get_ad()
        for i in range(15):
            result = ad.record("latency", 50 + i)
        self.assertIsNone(result)

    def test_record_anomaly(self):
        ad = self._get_ad()
        for i in range(15):
            ad.record("latency", 50)
        a = ad.record("latency", 500)
        self.assertIsNotNone(a)
        self.assertIn(a.severity, ["low", "medium", "high", "critical"])

    def test_batch(self):
        ad = self._get_ad()
        for i in range(15):
            ad.record_batch({"cpu": 50, "mem": 60})
        anomalies = ad.record_batch({"cpu": 999, "mem": 5})
        self.assertEqual(len(anomalies), 2)

    def test_acknowledge(self):
        ad = self._get_ad()
        for i in range(15):
            ad.record("x", 10)
        a = ad.record("x", 999)
        self.assertTrue(ad.acknowledge(a.anomaly_id))
        self.assertFalse(ad.acknowledge("nonexistent"))

    def test_baselines(self):
        ad = self._get_ad()
        for i in range(15):
            ad.record("m", 10 + i)
        bl = ad.get_baselines()
        self.assertEqual(len(bl), 1)
        self.assertGreater(bl[0]["samples"], 0)

    def test_stats(self):
        ad = self._get_ad()
        ad.record("m", 10)
        s = ad.get_stats()
        self.assertEqual(s["total_baselines"], 1)

    def test_get_anomalies(self):
        ad = self._get_ad()
        for i in range(15):
            ad.record("m", 10)
        ad.record("m", 999)
        anomalies = ad.get_anomalies()
        self.assertGreaterEqual(len(anomalies), 1)

    def test_get_anomalies_filtered(self):
        ad = self._get_ad()
        for i in range(15):
            ad.record("m", 10)
        ad.record("m", 999)
        anomalies = ad.get_anomalies(severity="high")
        for a in anomalies:
            self.assertEqual(a["severity"], "high")

    def test_record_batch_empty(self):
        ad = self._get_ad()
        result = ad.record_batch({})
        self.assertEqual(result, [])

    def test_singleton(self):
        from orbit.orbit.core.anomaly_detector import get_anomaly_detector

        s1 = get_anomaly_detector()
        s2 = get_anomaly_detector()
        self.assertIs(s1, s2)


if __name__ == "__main__":
    unittest.main()
