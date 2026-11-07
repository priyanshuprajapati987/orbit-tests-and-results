"""Unit tests for orbit/orbit/core/annotator_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.annotator_bp import annotator_bp


class TestAnnotatorBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(annotator_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(annotator_bp.name, "annotator_bp")

    def test_route_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/annotate", rules)

    def test_missing_image_400(self):
        r = self.client.post("/api/annotate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_annotate_success(self):
        with patch("orbit.core.annotator_bp.get_annotator") as ga:
            ga.return_value.annotate.return_value = {"annotated": "img.png"}
            r = self.client.post("/api/annotate", json={"image": "img.png", "annotations": [{"x": 1}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["annotated"], "img.png")
        ga.return_value.annotate.assert_called_once_with("img.png", [{"x": 1}])

    def test_no_body(self):
        r = self.client.post("/api/annotate")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
