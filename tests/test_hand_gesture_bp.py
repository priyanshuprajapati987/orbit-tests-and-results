"""Unit tests for orbit/orbit/core/hand_gesture_bp.py."""

import os
import queue
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.hand_gesture_bp import hand_gesture_bp

P = "orbit.core.hand_gesture_bp.get_hand_gesture"


class GestureBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(hand_gesture_bp)
        self.client = self.app.test_client()
        self.g = MagicMock()
        patcher = patch(P, return_value=self.g)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_blueprint_name(self):
        self.assertEqual(hand_gesture_bp.name, "hand_gesture")
        self.assertEqual(hand_gesture_bp.url_prefix, "/api/gestures")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/gestures/start", "/api/gestures/stop",
                  "/api/gestures/status", "/api/gestures/config",
                  "/api/gestures/config/schema", "/api/gestures/reset",
                  "/api/gestures/frame", "/api/gestures/frame/jpeg",
                  "/api/gestures/cursor/toggle",
                  "/api/gestures/cursor/status",
                  "/api/gestures/custom/record", "/api/gestures/custom/stop",
                  "/api/gestures/custom/list", "/api/gestures/custom/delete",
                  "/api/gestures/sequences", "/api/gestures/sequences/add",
                  "/api/gestures/sequences/remove",
                  "/api/gestures/stream"]:
            self.assertIn(p, rules)


class TestLifecycle(GestureBpBase):
    def test_start(self):
        self.g.start.return_value = {"running": True}
        r = self.client.post("/api/gestures/start")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"running": True})

    def test_start_exception_500(self):
        self.g.start.side_effect = RuntimeError("cam busy")
        r = self.client.post("/api/gestures/start")
        self.assertEqual(r.status_code, 500)
        self.assertIn("cam busy", r.get_json()["error"])

    def test_stop(self):
        self.g.stop.return_value = {"running": False}
        r = self.client.post("/api/gestures/stop")
        self.assertEqual(r.get_json(), {"running": False})

    def test_stop_exception_500(self):
        self.g.stop.side_effect = RuntimeError("st")
        r = self.client.post("/api/gestures/stop")
        self.assertEqual(r.status_code, 500)

    def test_status(self):
        self.g.get_stats.return_value = {"fps": 30}
        r = self.client.get("/api/gestures/status")
        self.assertEqual(r.get_json(), {"fps": 30})

    def test_status_exception_500(self):
        self.g.get_stats.side_effect = RuntimeError("s")
        r = self.client.get("/api/gestures/status")
        self.assertEqual(r.status_code, 500)

    def test_reset(self):
        r = self.client.post("/api/gestures/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"success": True})
        self.g.reset.assert_called_once()

    def test_reset_exception_500(self):
        self.g.reset.side_effect = RuntimeError("r")
        r = self.client.post("/api/gestures/reset")
        self.assertEqual(r.status_code, 500)


class TestConfig(GestureBpBase):
    def test_get_config(self):
        self.g.get_config.return_value = {"min_confidence": 0.7}
        r = self.client.get("/api/gestures/config")
        self.assertEqual(r.get_json(), {"min_confidence": 0.7})

    def test_get_config_exception_500(self):
        self.g.get_config.side_effect = RuntimeError("gc")
        r = self.client.get("/api/gestures/config")
        self.assertEqual(r.status_code, 500)

    def test_set_config(self):
        self.g.set_config.return_value = {"updated": True}
        r = self.client.post("/api/gestures/config",
                             json={"min_confidence": 0.8})
        self.assertEqual(r.status_code, 200)
        self.g.set_config.assert_called_once_with({"min_confidence": 0.8})

    def test_set_config_no_body_sends_empty_dict(self):
        self.g.set_config.return_value = {}
        r = self.client.post("/api/gestures/config")
        self.g.set_config.assert_called_once_with({})

    def test_set_config_exception_500(self):
        self.g.set_config.side_effect = RuntimeError("sc")
        r = self.client.post("/api/gestures/config", json={})
        self.assertEqual(r.status_code, 500)

    def test_schema(self):
        self.g.get_config_schema.return_value = {"fields": ["a"]}
        r = self.client.get("/api/gestures/config/schema")
        self.assertEqual(r.get_json(), {"fields": ["a"]})

    def test_schema_exception_500(self):
        self.g.get_config_schema.side_effect = RuntimeError("sh")
        r = self.client.get("/api/gestures/config/schema")
        self.assertEqual(r.status_code, 500)


class TestFrames(GestureBpBase):
    def test_frame_ok(self):
        self.g.latest_frame.return_value = "b64data"
        r = self.client.get("/api/gestures/frame")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ok": True, "image": "b64data"})
        self.g.latest_frame.assert_called_once_with(as_base64=True)

    def test_frame_missing_404(self):
        self.g.latest_frame.return_value = None
        r = self.client.get("/api/gestures/frame")
        self.assertEqual(r.status_code, 404)
        body = r.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["message"], "No frame yet")

    def test_frame_empty_bytes_404(self):
        self.g.latest_frame.return_value = b""
        r = self.client.get("/api/gestures/frame")
        self.assertEqual(r.status_code, 404)

    def test_frame_exception_500(self):
        self.g.latest_frame.side_effect = RuntimeError("f")
        r = self.client.get("/api/gestures/frame")
        self.assertEqual(r.status_code, 500)

    def test_frame_jpeg_ok(self):
        jpeg = b"\xff\xd8\xff\xe0payload"
        self.g.latest_frame.return_value = jpeg
        r = self.client.get("/api/gestures/frame/jpeg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/jpeg")
        self.assertEqual(r.data, jpeg)
        self.g.latest_frame.assert_called_once_with(as_base64=False)

    def test_frame_jpeg_missing_404(self):
        self.g.latest_frame.return_value = None
        r = self.client.get("/api/gestures/frame/jpeg")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.data, b"")

    def test_frame_jpeg_exception_500(self):
        self.g.latest_frame.side_effect = RuntimeError("jf")
        r = self.client.get("/api/gestures/frame/jpeg")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "jf")


class TestCursor(GestureBpBase):
    def test_toggle_enabled(self):
        self.g.cursor_toggle.return_value = {"cursor": True}
        r = self.client.post("/api/gestures/cursor/toggle",
                             json={"enabled": True})
        self.assertEqual(r.status_code, 200)
        self.g.cursor_toggle.assert_called_once_with(True)

    def test_toggle_disabled(self):
        self.g.cursor_toggle.return_value = {"cursor": False}
        self.client.post("/api/gestures/cursor/toggle",
                         json={"enabled": False})
        self.g.cursor_toggle.assert_called_once_with(False)

    def test_toggle_no_body_passes_none(self):
        self.g.cursor_toggle.return_value = {}
        self.client.post("/api/gestures/cursor/toggle")
        self.g.cursor_toggle.assert_called_once_with(None)

    def test_toggle_exception_500(self):
        self.g.cursor_toggle.side_effect = RuntimeError("ct")
        r = self.client.post("/api/gestures/cursor/toggle", json={})
        self.assertEqual(r.status_code, 500)

    def test_cursor_status(self):
        self.g.cursor_state.return_value = {"enabled": False}
        r = self.client.get("/api/gestures/cursor/status")
        self.assertEqual(r.get_json(), {"enabled": False})

    def test_cursor_status_exception_500(self):
        self.g.cursor_state.side_effect = RuntimeError("cs")
        r = self.client.get("/api/gestures/cursor/status")
        self.assertEqual(r.status_code, 500)


class TestCustomGestures(GestureBpBase):
    def test_record_success(self):
        self.g.record_custom_gesture.return_value = {"recording": True}
        r = self.client.post("/api/gestures/custom/record",
                             json={"name": "  thumbsup  "})
        self.assertEqual(r.status_code, 200)
        self.g.record_custom_gesture.assert_called_once_with("thumbsup")

    def test_record_missing_name_400(self):
        r = self.client.post("/api/gestures/custom/record", json={})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "name_required")
        self.g.record_custom_gesture.assert_not_called()

    def test_record_blank_name_400(self):
        r = self.client.post("/api/gestures/custom/record",
                             json={"name": "   "})
        self.assertEqual(r.status_code, 400)

    def test_record_no_body_400(self):
        r = self.client.post("/api/gestures/custom/record")
        self.assertEqual(r.status_code, 400)

    def test_record_non_string_name_500(self):
        # .strip() on int -> AttributeError -> 500
        r = self.client.post("/api/gestures/custom/record",
                             json={"name": 123})
        self.assertEqual(r.status_code, 500)

    def test_record_exception_500(self):
        self.g.record_custom_gesture.side_effect = RuntimeError("rec")
        r = self.client.post("/api/gestures/custom/record",
                             json={"name": "x"})
        self.assertEqual(r.status_code, 500)

    def test_stop_recording(self):
        self.g.stop_recording.return_value = {"saved": "g1"}
        r = self.client.post("/api/gestures/custom/stop")
        self.assertEqual(r.get_json(), {"saved": "g1"})

    def test_stop_recording_exception_500(self):
        self.g.stop_recording.side_effect = RuntimeError("sr")
        r = self.client.post("/api/gestures/custom/stop")
        self.assertEqual(r.status_code, 500)

    def test_list(self):
        self.g.list_custom_gestures.return_value = ["wave"]
        r = self.client.get("/api/gestures/custom/list")
        self.assertEqual(r.get_json(), ["wave"])

    def test_list_exception_500(self):
        self.g.list_custom_gestures.side_effect = RuntimeError("l")
        r = self.client.get("/api/gestures/custom/list")
        self.assertEqual(r.status_code, 500)

    def test_delete(self):
        self.g.delete_custom_gesture.return_value = {"deleted": True}
        r = self.client.post("/api/gestures/custom/delete",
                             json={"name": "wave"})
        self.assertEqual(r.status_code, 200)
        self.g.delete_custom_gesture.assert_called_once_with("wave")

    def test_delete_missing_name_passes_empty(self):
        self.g.delete_custom_gesture.return_value = {"deleted": False}
        self.client.post("/api/gestures/custom/delete", json={})
        self.g.delete_custom_gesture.assert_called_once_with("")

    def test_delete_exception_500(self):
        self.g.delete_custom_gesture.side_effect = RuntimeError("d")
        r = self.client.post("/api/gestures/custom/delete",
                             json={"name": "x"})
        self.assertEqual(r.status_code, 500)


class TestSequences(GestureBpBase):
    def test_state(self):
        self.g.sequence_state.return_value = {"active": None}
        r = self.client.get("/api/gestures/sequences")
        self.assertEqual(r.get_json(), {"active": None})

    def test_state_exception_500(self):
        self.g.sequence_state.side_effect = RuntimeError("ss")
        r = self.client.get("/api/gestures/sequences")
        self.assertEqual(r.status_code, 500)

    def test_add_success(self):
        self.g.add_sequence.return_value = {"added": True}
        r = self.client.post("/api/gestures/sequences/add", json={
            "name": "  combo  ", "gestures": ["a", "b"],
            "action": "open_app", "timeout": 5.0})
        self.assertEqual(r.status_code, 200)
        self.g.add_sequence.assert_called_once_with(
            "combo", ["a", "b"], "open_app", 5.0)

    def test_add_defaults(self):
        self.g.add_sequence.return_value = {}
        r = self.client.post("/api/gestures/sequences/add", json={
            "name": "n", "gestures": ["a"], "action": "act"})
        self.g.add_sequence.assert_called_once_with(
            "n", ["a"], "act", 3.0)

    def test_add_missing_name_400(self):
        r = self.client.post("/api/gestures/sequences/add", json={
            "gestures": ["a"], "action": "act"})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "name_gestures_action_required")
        self.g.add_sequence.assert_not_called()

    def test_add_missing_gestures_400(self):
        r = self.client.post("/api/gestures/sequences/add", json={
            "name": "n", "gestures": [], "action": "act"})
        self.assertEqual(r.status_code, 400)

    def test_add_missing_action_400(self):
        r = self.client.post("/api/gestures/sequences/add", json={
            "name": "n", "gestures": ["a"]})
        self.assertEqual(r.status_code, 400)

    def test_add_no_body_400(self):
        r = self.client.post("/api/gestures/sequences/add")
        self.assertEqual(r.status_code, 400)

    def test_add_non_string_name_500(self):
        r = self.client.post("/api/gestures/sequences/add", json={
            "name": 42, "gestures": ["a"], "action": "act"})
        self.assertEqual(r.status_code, 500)

    def test_add_exception_500(self):
        self.g.add_sequence.side_effect = RuntimeError("add")
        r = self.client.post("/api/gestures/sequences/add", json={
            "name": "n", "gestures": ["a"], "action": "act"})
        self.assertEqual(r.status_code, 500)

    def test_remove(self):
        self.g.remove_sequence.return_value = {"removed": True}
        r = self.client.post("/api/gestures/sequences/remove",
                             json={"name": "combo"})
        self.assertEqual(r.get_json(), {"removed": True})
        self.g.remove_sequence.assert_called_once_with("combo")

    def test_remove_no_body_passes_empty(self):
        self.g.remove_sequence.return_value = {}
        self.client.post("/api/gestures/sequences/remove")
        self.g.remove_sequence.assert_called_once_with("")

    def test_remove_exception_500(self):
        self.g.remove_sequence.side_effect = RuntimeError("rm")
        r = self.client.post("/api/gestures/sequences/remove",
                             json={"name": "x"})
        self.assertEqual(r.status_code, 500)


class TestSSEStream(GestureBpBase):
    def test_stream_headers(self):
        r = self.client.get("/api/gestures/stream")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "text/event-stream")
        self.assertEqual(r.headers.get("Cache-Control"), "no-cache")
        self.assertEqual(r.headers.get("X-Accel-Buffering"), "no")

    def test_subscriber_registered_with_bounded_queue(self):
        r = self.client.get("/api/gestures/stream")
        self.g.add_sse_subscriber.assert_called_once()
        q = self.g.add_sse_subscriber.call_args.args[0]
        self.assertIsInstance(q, queue.Queue)
        self.assertEqual(q.maxsize, 100)
        r.response.close()

    def test_stream_delivers_message(self):
        r = self.client.get("/api/gestures/stream")
        q = self.g.add_sse_subscriber.call_args.args[0]
        q.put(b"data: gesture-wave\n\n")
        got = ""
        for _ in range(3):
            chunk = next(r.response)
            got += chunk.decode() if isinstance(chunk, bytes) else chunk
            if "gesture-wave" in got:
                break
        self.assertIn("gesture-wave", got)
        r.response.close()

    def test_close_unsubscribes(self):
        r = self.client.get("/api/gestures/stream")
        q = self.g.add_sse_subscriber.call_args.args[0]
        r.response.close()
        self.g.remove_sse_subscriber.assert_called_once_with(q)

    def test_keepalive_when_idle(self):
        # no messages pushed -> first chunk(s) are keepalive comments
        r = self.client.get("/api/gestures/stream")
        got = ""
        for _ in range(2):
            chunk = next(r.response)
            got += chunk.decode() if isinstance(chunk, bytes) else chunk
        self.assertIn("keepalive", got)
        r.response.close()


if __name__ == "__main__":
    unittest.main()
