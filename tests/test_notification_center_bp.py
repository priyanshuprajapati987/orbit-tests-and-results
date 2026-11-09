"""Unit tests for orbit/orbit/core/notification_center_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.notification_center_bp import notification_center_bp


class TestNotificationCenterBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(notification_center_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(notification_center_bp.name, "notification_center")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/notifications", "/api/notifications/add", "/api/notifications/read/<notification_id>",
                  "/api/notifications/<notification_id>/read", "/api/notifications/read-all",
                  "/api/notifications/clear", "/api/notifications/<notification_id>",
                  "/api/notifications/unread-count"]:
            self.assertIn(p, rules)

    def test_list_notifications(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.get_notifications.return_value = [{"id": "n1"}]
            r = self.client.get("/api/notifications?limit=5&unread_only=true")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["notifications"], [{"id": "n1"}])
        gc.return_value.get_notifications.assert_called_once_with(limit=5, unread_only=True)

    def test_list_notifications_defaults(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.get_notifications.return_value = []
            r = self.client.get("/api/notifications")
        gc.return_value.get_notifications.assert_called_once_with(limit=50, unread_only=False)

    def test_list_notifications_invalid_limit(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.get_notifications.return_value = []
            r = self.client.get("/api/notifications?limit=abc")
        self.assertEqual(r.status_code, 200)
        gc.return_value.get_notifications.assert_called_once_with(limit=50, unread_only=False)

    def test_list_notifications_clamped(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.get_notifications.return_value = []
            r = self.client.get("/api/notifications?limit=1000")
        gc.return_value.get_notifications.assert_called_once_with(limit=500, unread_only=False)

    def test_add_notification(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.add_notification.return_value = {"id": "n1"}
            r = self.client.post("/api/notifications/add", json={"type": "info", "title": "t", "message": "m", "source": "s"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], "n1")
        gc.return_value.add_notification.assert_called_once_with(notif_type="info", title="t", message="m", source="s")

    def test_add_notification_defaults(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.add_notification.return_value = {"id": "n2"}
            r = self.client.post("/api/notifications/add", json={})
        gc.return_value.add_notification.assert_called_once_with(notif_type="info", title="", message="", source="system")

    def test_add_notification_no_body(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.add_notification.return_value = {"id": "n3"}
            r = self.client.post("/api/notifications/add")
        gc.return_value.add_notification.assert_called_once_with(notif_type="info", title="", message="", source="system")

    def test_add_notification_error(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.add_notification.side_effect = RuntimeError("boom")
            r = self.client.post("/api/notifications/add", json={"title": "t"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_mark_read(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.mark_read.return_value = True
            r = self.client.post("/api/notifications/read/n1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gc.return_value.mark_read.assert_called_once_with("n1")

    def test_mark_read_alt_route(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.mark_read.return_value = True
            r = self.client.post("/api/notifications/n1/read")
        self.assertEqual(r.status_code, 200)
        gc.return_value.mark_read.assert_called_once_with("n1")

    def test_mark_read_not_found_404(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.mark_read.return_value = False
            r = self.client.post("/api/notifications/read/n1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_mark_read_error(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.mark_read.side_effect = RuntimeError("boom")
            r = self.client.post("/api/notifications/read/n1")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_mark_all_read(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.mark_all_read.return_value = 3
            r = self.client.post("/api/notifications/read-all")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["marked"], 3)

    def test_mark_all_read_error(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.mark_all_read.side_effect = RuntimeError("boom")
            r = self.client.post("/api/notifications/read-all")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_clear_via_post(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.clear_all.return_value = 2
            r = self.client.post("/api/notifications/clear")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cleared"], 2)

    def test_clear_via_delete(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.clear_all.return_value = 1
            r = self.client.delete("/api/notifications")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cleared"], 1)

    def test_clear_error(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.clear_all.side_effect = RuntimeError("boom")
            r = self.client.post("/api/notifications/clear")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_dismiss_success(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.dismiss.return_value = True
            r = self.client.delete("/api/notifications/n1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")
        gc.return_value.dismiss.assert_called_once_with("n1")

    def test_dismiss_not_found_404(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.dismiss.return_value = False
            r = self.client.delete("/api/notifications/n1")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_dismiss_error(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.dismiss.side_effect = RuntimeError("boom")
            r = self.client.delete("/api/notifications/n1")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_unread_count(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.get_unread_count.return_value = 3
            r = self.client.get("/api/notifications/unread-count")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 3)

    def test_unread_count_error(self):
        with patch("orbit.core.notification_center_bp.get_notification_center") as gc:
            gc.return_value.get_unread_count.side_effect = RuntimeError("boom")
            r = self.client.get("/api/notifications/unread-count")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
