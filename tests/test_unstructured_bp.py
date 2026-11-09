"""Unit tests for orbit/orbit/core/unstructured_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.unstructured_bp import unstructured_bp


class TestUnstructuredBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(unstructured_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(unstructured_bp.name, "unstructured_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/unstructured/status", "/api/unstructured/process",
                  "/api/unstructured/tables", "/api/unstructured/elements",
                  "/api/unstructured/stats"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/unstructured/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_process_missing_400(self):
        r = self.client.post("/api/unstructured/process", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_process_text(self):
        result = MagicMock()
        result.to_dict.return_value = {"chunks": 3}
        with patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.process_text.return_value = result
            r = self.client.post("/api/unstructured/process", json={"text": "hello", "strategy": "auto", "chunk_size": 100, "chunk_overlap": 10})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["chunks"], 3)
        gu.return_value.process_text.assert_called_once_with("hello", strategy="auto", chunk_size=100, chunk_overlap=10)

    def test_process_text_no_optional(self):
        result = MagicMock()
        result.to_dict.return_value = {"chunks": 1}
        with patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.process_text.return_value = result
            r = self.client.post("/api/unstructured/process", json={"text": "hello"})
        gu.return_value.process_text.assert_called_once_with("hello", strategy="auto", chunk_size=None, chunk_overlap=None)

    def test_process_file_blocked_403(self):
        with patch("orbit.core.unstructured_bp.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/unstructured/process", json={"file_path": "/etc/x"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("path not allowed", r.get_json()["error"])

    def test_process_file_success(self):
        result = MagicMock()
        result.to_dict.return_value = {"chunks": 2}
        with patch("orbit.core.unstructured_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.process_file.return_value = result
            r = self.client.post("/api/unstructured/process", json={"file_path": "doc.txt", "strategy": "auto"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["chunks"], 2)
        gu.return_value.process_file.assert_called_once_with("doc.txt", strategy="auto", chunk_size=None, chunk_overlap=None)

    def test_process_no_body(self):
        r = self.client.post("/api/unstructured/process")
        self.assertEqual(r.status_code, 400)

    def test_tables_missing_file_400(self):
        r = self.client.post("/api/unstructured/tables", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_tables_blocked_403(self):
        with patch("orbit.core.unstructured_bp.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/unstructured/tables", json={"file_path": "/etc/x"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("path not allowed", r.get_json()["error"])

    def test_tables_success(self):
        with patch("orbit.core.unstructured_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.extract_tables.return_value = [{"t": 1}, {"t": 2}]
            r = self.client.post("/api/unstructured/tables", json={"file_path": "doc.txt"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["tables"]), 2)
        gu.return_value.extract_tables.assert_called_once_with("doc.txt")

    def test_tables_no_body(self):
        r = self.client.post("/api/unstructured/tables")
        self.assertEqual(r.status_code, 400)

    def test_elements_missing_400(self):
        r = self.client.post("/api/unstructured/elements", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_elements_text(self):
        result = MagicMock()
        result.elements = ["e1", "e2"]
        with patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.process_text.return_value = result
            r = self.client.post("/api/unstructured/elements", json={"text": "hi", "strategy": "fast"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["elements"], ["e1", "e2"])
        gu.return_value.process_text.assert_called_once_with("hi", strategy="fast")

    def test_elements_file_blocked_403(self):
        with patch("orbit.core.unstructured_bp.validate_path", return_value=(False, "nope")):
            r = self.client.post("/api/unstructured/elements", json={"file_path": "/etc/x"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("path not allowed", r.get_json()["error"])

    def test_elements_file_success(self):
        result = MagicMock()
        result.elements = ["e1"]
        with patch("orbit.core.unstructured_bp.validate_path", return_value=(True, "ok")), \
             patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.process_file.return_value = result
            r = self.client.post("/api/unstructured/elements", json={"file_path": "doc.txt", "strategy": "auto"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 1)
        gu.return_value.process_file.assert_called_once_with("doc.txt", strategy="auto")

    def test_elements_no_body(self):
        r = self.client.post("/api/unstructured/elements")
        self.assertEqual(r.status_code, 400)

    def test_stats(self):
        with patch("orbit.core.unstructured_bp._get_up") as gu:
            gu.return_value.get_stats.return_value = {"total": 5}
            r = self.client.get("/api/unstructured/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["total"], 5)


if __name__ == "__main__":
    unittest.main()
