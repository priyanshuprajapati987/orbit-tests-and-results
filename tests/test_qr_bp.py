"""Unit tests for orbit/orbit/core/qr_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.qr_bp import qr_bp


class TestQrBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(qr_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(qr_bp.name, "qr_bp")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/qr/generate", rules)

    def test_missing_text_400(self):
        r = self.client.post("/api/qr/generate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_generate_success(self):
        with patch("orbit.core.qr_bp.get_qr_generator") as gq:
            gq.return_value.generate.return_value = {"status": "generated", "image_base64": "abc"}
            r = self.client.post("/api/qr/generate", json={"text": "hello"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "generated")
        gq.return_value.generate.assert_called_once_with("hello")

    def test_no_body(self):
        r = self.client.post("/api/qr/generate")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
