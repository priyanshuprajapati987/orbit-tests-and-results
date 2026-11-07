"""Unit tests for orbit/orbit/core/color_picker_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.color_picker_bp import color_picker_bp


class TestColorPickerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(color_picker_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(color_picker_bp.name, "color_picker_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/color/pixel", "/api/color/mouse", "/api/color/convert"]:
            self.assertIn(p, rules)

    def test_pixel(self):
        with patch("orbit.core.color_picker_bp.get_color_picker") as gc:
            gc.return_value.get_pixel_color.return_value = {"r": 1, "g": 2, "b": 3}
            r = self.client.post("/api/color/pixel", json={"x": 5, "y": 7})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["r"], 1)
        gc.return_value.get_pixel_color.assert_called_once_with(5, 7)

    def test_pixel_defaults(self):
        with patch("orbit.core.color_picker_bp.get_color_picker") as gc:
            gc.return_value.get_pixel_color.return_value = {"r": 0}
            r = self.client.post("/api/color/pixel", json={})
        gc.return_value.get_pixel_color.assert_called_once_with(0, 0)

    def test_mouse(self):
        with patch("orbit.core.color_picker_bp.get_color_picker") as gc:
            gc.return_value.get_mouse_color.return_value = {"r": 9}
            r = self.client.get("/api/color/mouse")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["r"], 9)

    def test_convert_success(self):
        with patch("orbit.core.color_picker_bp.get_color_picker") as gc:
            gc.return_value.hex_to_rgb.return_value = {"r": 255, "g": 0, "b": 0}
            r = self.client.post("/api/color/convert", json={"hex": "#ff0000"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["r"], 255)
        gc.return_value.hex_to_rgb.assert_called_once_with("#ff0000")

    def test_convert_missing_hex_400(self):
        r = self.client.post("/api/color/convert", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_no_body(self):
        r = self.client.post("/api/color/convert")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
