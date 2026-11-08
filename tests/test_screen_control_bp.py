"""Unit tests for orbit/orbit/core/screen_control_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.screen_control_bp import screen_control_bp


class TestScreenControlBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(screen_control_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(screen_control_bp.name, "screen_control_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/screen-control/status", "/api/screen-control/click",
                  "/api/screen-control/double-click", "/api/screen-control/right-click",
                  "/api/screen-control/type", "/api/screen-control/hotkey",
                  "/api/screen-control/scroll", "/api/screen-control/move",
                  "/api/screen-control/screenshot", "/api/screen-control/screen-size",
                  "/api/screen-control/mouse-pos"]:
            self.assertIn(p, rules)

    def test_status(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.get_status.return_value = {"ok": True}
            r = self.client.get("/api/screen-control/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_click(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.click.return_value = {"clicked": True}
            r = self.client.post("/api/screen-control/click", json={"x": 10, "y": 20, "button": "right"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["clicked"])
        gc.return_value.click.assert_called_once_with(10, 20, "right")

    def test_click_defaults(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.click.return_value = {"clicked": True}
            r = self.client.post("/api/screen-control/click", json={})
        gc.return_value.click.assert_called_once_with(None, None, "left")

    def test_double_click(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.double_click.return_value = {"done": True}
            r = self.client.post("/api/screen-control/double-click", json={"x": 1, "y": 2})
        gc.return_value.double_click.assert_called_once_with(1, 2)

    def test_right_click(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.right_click.return_value = {"done": True}
            r = self.client.post("/api/screen-control/right-click", json={"x": 1, "y": 2})
        gc.return_value.right_click.assert_called_once_with(1, 2)

    def test_type_missing_text_400(self):
        r = self.client.post("/api/screen-control/type", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_type_success(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.type_text.return_value = {"typed": True}
            r = self.client.post("/api/screen-control/type", json={"text": "hi", "interval": 0.05})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["typed"])
        gc.return_value.type_text.assert_called_once_with("hi", 0.05)

    def test_type_default_interval(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.type_text.return_value = {"typed": True}
            r = self.client.post("/api/screen-control/type", json={"text": "hi"})
        gc.return_value.type_text.assert_called_once_with("hi", 0.02)

    def test_type_no_body(self):
        r = self.client.post("/api/screen-control/type")
        self.assertEqual(r.status_code, 400)

    def test_hotkey_missing_keys_400(self):
        r = self.client.post("/api/screen-control/hotkey", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_hotkey_success(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.hotkey.return_value = {"pressed": True}
            r = self.client.post("/api/screen-control/hotkey", json={"keys": ["ctrl", "c"]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["pressed"])
        gc.return_value.hotkey.assert_called_once_with("ctrl", "c")

    def test_hotkey_no_body(self):
        r = self.client.post("/api/screen-control/hotkey")
        self.assertEqual(r.status_code, 400)

    def test_scroll(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.scroll.return_value = {"scrolled": True}
            r = self.client.post("/api/screen-control/scroll", json={"clicks": 5})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["scrolled"])
        gc.return_value.scroll.assert_called_once_with(5)

    def test_scroll_default(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.scroll.return_value = {"scrolled": True}
            r = self.client.post("/api/screen-control/scroll", json={})
        gc.return_value.scroll.assert_called_once_with(3)

    def test_scroll_no_body(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.scroll.return_value = {"scrolled": True}
            r = self.client.post("/api/screen-control/scroll")
        gc.return_value.scroll.assert_called_once_with(3)

    def test_move(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.move.return_value = {"moved": True}
            r = self.client.post("/api/screen-control/move", json={"x": 5, "y": 6})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["moved"])
        gc.return_value.move.assert_called_once_with(5, 6)

    def test_move_defaults(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.move.return_value = {"moved": True}
            r = self.client.post("/api/screen-control/move", json={})
        gc.return_value.move.assert_called_once_with(0, 0)

    def test_screenshot(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.screenshot.return_value = {"path": "s.png"}
            r = self.client.post("/api/screen-control/screenshot")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["path"], "s.png")

    def test_screen_size(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.get_screen_size.return_value = {"w": 1920, "h": 1080}
            r = self.client.get("/api/screen-control/screen-size")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["w"], 1920)

    def test_mouse_pos(self):
        with patch("orbit.core.screen_control_bp.get_screen_controller") as gc:
            gc.return_value.get_mouse_position.return_value = {"x": 10, "y": 20}
            r = self.client.get("/api/screen-control/mouse-pos")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["x"], 10)


if __name__ == "__main__":
    unittest.main()
