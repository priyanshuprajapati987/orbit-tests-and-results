"""Unit tests for orbit/orbit/core/mobile_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.mobile_bp import mobile_bp

P = "orbit.core.mobile_bp.get_mobile_api"
VC = "orbit.core.mobile_bp.validate_command"


class MobileBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(mobile_bp)
        self.client = self.app.test_client()
        self.api = MagicMock()
        p = patch(P, return_value=self.api)
        p.start()
        self.addCleanup(p.stop)

    def test_blueprint_name(self):
        self.assertEqual(mobile_bp.name, "mobile")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/mobile/register", "/api/mobile/auth",
                  "/api/mobile/status", "/api/mobile/devices/status",
                  "/api/mobile/heartbeat/<device_id>",
                  "/api/mobile/verify",
                  "/api/mobile/pairing-code/<device_id>",
                  "/api/mobile/find", "/api/mobile/chat",
                  "/api/mobile/agents", "/api/mobile/devices",
                  "/api/mobile/device/<device_id>/preferences",
                  "/api/mobile/cache", "/api/mobile/cache/<key>",
                  "/api/mobile/tasks/assign",
                  "/api/mobile/tasks/pending/<device_id>",
                  "/api/mobile/tasks/output/<task_id>",
                  "/api/mobile/preferences/platform",
                  "/api/mobile/notify",
                  "/api/mobile/command/<command>"]:
            self.assertIn(p, rules)


class TestRegisterAuth(MobileBpBase):
    def test_register_success(self):
        self.api.register_device.return_value = {"device_id": "d1"}
        r = self.client.post("/api/mobile/register", json={
            "name": "Pixel", "platform": "android"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"device_id": "d1"})
        self.api.register_device.assert_called_once_with(
            "Pixel", "android", "")

    def test_register_with_push_token(self):
        self.api.register_device.return_value = {}
        self.client.post("/api/mobile/register", json={
            "name": "iPhone", "platform": "ios", "push_token": "tok123"})
        self.api.register_device.assert_called_once_with(
            "iPhone", "ios", "tok123")

    def test_register_missing_name_400(self):
        r = self.client.post("/api/mobile/register",
                             json={"platform": "android"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"],
                         "name and platform required")
        self.api.register_device.assert_not_called()

    def test_register_missing_platform_400(self):
        r = self.client.post("/api/mobile/register", json={"name": "x"})
        self.assertEqual(r.status_code, 400)

    def test_register_no_body_400(self):
        r = self.client.post("/api/mobile/register")
        self.assertEqual(r.status_code, 400)

    def test_register_exception_500(self):
        self.api.register_device.side_effect = RuntimeError("reg fail")
        r = self.client.post("/api/mobile/register", json={
            "name": "n", "platform": "p"})
        self.assertEqual(r.status_code, 500)

    def test_auth_success(self):
        self.api.authenticate.return_value = {"id": "d1"}
        r = self.client.post("/api/mobile/auth",
                             json={"session_token": "abc"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"status": "ok", "device": {"id": "d1"}})
        self.api.authenticate.assert_called_once_with("abc")

    def test_auth_invalid_401(self):
        self.api.authenticate.return_value = None
        r = self.client.post("/api/mobile/auth",
                             json={"session_token": "bad"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.get_json()["error"], "Invalid token")

    def test_auth_missing_token_401(self):
        self.api.authenticate.return_value = None
        r = self.client.post("/api/mobile/auth", json={})
        self.assertEqual(r.status_code, 401)
        self.api.authenticate.assert_called_once_with("")

    def test_auth_exception_500(self):
        self.api.authenticate.side_effect = RuntimeError("auth fail")
        r = self.client.post("/api/mobile/auth", json={})
        self.assertEqual(r.status_code, 500)


class TestStatus(MobileBpBase):
    def test_status(self):
        self.api.get_status_lightweight.return_value = {"online": True}
        r = self.client.get("/api/mobile/status")
        self.assertEqual(r.get_json(), {"online": True})

    def test_status_exception_500(self):
        self.api.get_status_lightweight.side_effect = RuntimeError("s")
        r = self.client.get("/api/mobile/status")
        self.assertEqual(r.status_code, 500)

    def test_devices_status(self):
        self.api.get_connection_status.return_value = {"d1": "online"}
        r = self.client.get("/api/mobile/devices/status")
        self.assertEqual(r.get_json(), {"d1": "online"})

    def test_devices_status_exception_500(self):
        self.api.get_connection_status.side_effect = RuntimeError("c")
        r = self.client.get("/api/mobile/devices/status")
        self.assertEqual(r.status_code, 500)


class TestDevices(MobileBpBase):
    def test_heartbeat(self):
        r = self.client.post("/api/mobile/heartbeat/d1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok", "device_id": "d1"})
        self.api.heartbeat.assert_called_once_with("d1")

    def test_heartbeat_exception_500(self):
        self.api.heartbeat.side_effect = RuntimeError("hb")
        r = self.client.post("/api/mobile/heartbeat/d1")
        self.assertEqual(r.status_code, 500)

    def test_verify_ok(self):
        self.api.verify_device.return_value = True
        r = self.client.post("/api/mobile/verify", json={
            "device_id": "d1", "code": "123456"})
        self.assertEqual(r.get_json(), {"verified": True})
        self.api.verify_device.assert_called_once_with("d1", "123456")

    def test_verify_failed(self):
        self.api.verify_device.return_value = False
        r = self.client.post("/api/mobile/verify", json={
            "device_id": "d1", "code": "000000"})
        self.assertEqual(r.get_json(), {"verified": False})

    def test_verify_no_body(self):
        self.api.verify_device.return_value = False
        r = self.client.post("/api/mobile/verify")
        self.api.verify_device.assert_called_once_with("", "")

    def test_verify_exception_500(self):
        self.api.verify_device.side_effect = RuntimeError("v")
        r = self.client.post("/api/mobile/verify", json={})
        self.assertEqual(r.status_code, 500)

    def test_pairing_code_success(self):
        self.api.generate_pairing_code.return_value = "482913"
        r = self.client.post("/api/mobile/pairing-code/d1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"pairing_code": "482913", "device_id": "d1"})

    def test_pairing_code_not_found_404(self):
        self.api.generate_pairing_code.return_value = None
        r = self.client.post("/api/mobile/pairing-code/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "device_not_found")

    def test_pairing_code_exception_500(self):
        self.api.generate_pairing_code.side_effect = RuntimeError("pc")
        r = self.client.post("/api/mobile/pairing-code/d1")
        self.assertEqual(r.status_code, 500)

    def test_find_found(self):
        self.api.find_device_by_name.return_value = {"id": "d1"}
        r = self.client.get("/api/mobile/find?name=Pixel&platform=android")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"device": {"id": "d1"}})
        self.api.find_device_by_name.assert_called_once_with(
            "Pixel", "android")

    def test_find_missing_404(self):
        self.api.find_device_by_name.return_value = None
        r = self.client.get("/api/mobile/find?name=nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "not_found")

    def test_find_no_params(self):
        self.api.find_device_by_name.return_value = None
        r = self.client.get("/api/mobile/find")
        self.api.find_device_by_name.assert_called_once_with("", "")

    def test_find_exception_500(self):
        self.api.find_device_by_name.side_effect = RuntimeError("f")
        r = self.client.get("/api/mobile/find?name=x")
        self.assertEqual(r.status_code, 500)

    def test_list_devices(self):
        self.api.list_devices.return_value = ["d1", "d2"]
        r = self.client.get("/api/mobile/devices")
        self.assertEqual(r.get_json(), {"devices": ["d1", "d2"]})

    def test_list_devices_exception_500(self):
        self.api.list_devices.side_effect = RuntimeError("ld")
        r = self.client.get("/api/mobile/devices")
        self.assertEqual(r.status_code, 500)


class TestPreferences(MobileBpBase):
    def test_update_prefs_ok(self):
        self.api.update_preferences.return_value = True
        r = self.client.post("/api/mobile/device/d1/preferences",
                             json={"theme": "dark"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok"})
        self.api.update_preferences.assert_called_once_with(
            "d1", {"theme": "dark"})

    def test_update_prefs_not_found_404(self):
        self.api.update_preferences.return_value = False
        r = self.client.post("/api/mobile/device/nope/preferences",
                             json={})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Device not found")

    def test_update_prefs_exception_500(self):
        self.api.update_preferences.side_effect = RuntimeError("up")
        r = self.client.post("/api/mobile/device/d1/preferences",
                             json={})
        self.assertEqual(r.status_code, 500)

    def test_platform_pref_defaults(self):
        self.api.set_platform_preference.return_value = True
        r = self.client.post("/api/mobile/preferences/platform",
                             json={"device_id": "d1"})
        self.assertEqual(r.status_code, 200)
        self.api.set_platform_preference.assert_called_once_with(
            "d1", "general", "pc-first")

    def test_platform_pref_full(self):
        self.api.set_platform_preference.return_value = True
        self.client.post("/api/mobile/preferences/platform", json={
            "device_id": "d1", "task_type": "coding",
            "platform": "mobile-first"})
        self.api.set_platform_preference.assert_called_once_with(
            "d1", "coding", "mobile-first")

    def test_platform_pref_not_found_404(self):
        self.api.set_platform_preference.return_value = False
        r = self.client.post("/api/mobile/preferences/platform",
                             json={"device_id": "nope"})
        self.assertEqual(r.status_code, 404)

    def test_platform_pref_exception_500(self):
        self.api.set_platform_preference.side_effect = RuntimeError("pp")
        r = self.client.post("/api/mobile/preferences/platform", json={})
        self.assertEqual(r.status_code, 500)


class TestCache(MobileBpBase):
    def test_cache_set(self):
        r = self.client.post("/api/mobile/cache",
                             json={"key": "k1", "data": {"a": 1}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok"})
        self.api.cache_for_offline.assert_called_once_with("k1", {"a": 1})

    def test_cache_set_missing_key_400(self):
        r = self.client.post("/api/mobile/cache", json={"data": 1})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "key required")
        self.api.cache_for_offline.assert_not_called()

    def test_cache_set_no_data_key(self):
        self.client.post("/api/mobile/cache", json={"key": "k"})
        self.api.cache_for_offline.assert_called_once_with("k", None)

    def test_cache_set_exception_500(self):
        self.api.cache_for_offline.side_effect = RuntimeError("cs")
        r = self.client.post("/api/mobile/cache", json={"key": "k"})
        self.assertEqual(r.status_code, 500)

    def test_cache_get_hit(self):
        self.api.get_offline_cache.return_value = {"a": 1}
        r = self.client.get("/api/mobile/cache/k1")
        self.assertEqual(r.get_json(), {"data": {"a": 1}})
        self.api.get_offline_cache.assert_called_once_with("k1")

    def test_cache_get_miss_404(self):
        self.api.get_offline_cache.return_value = None
        r = self.client.get("/api/mobile/cache/missing")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Not cached")

    def test_cache_get_empty_dict_is_hit(self):
        # `is None` check: empty dict is a valid cached value
        self.api.get_offline_cache.return_value = {}
        r = self.client.get("/api/mobile/cache/empty")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"data": {}})

    def test_cache_get_exception_500(self):
        self.api.get_offline_cache.side_effect = RuntimeError("cg")
        r = self.client.get("/api/mobile/cache/k")
        self.assertEqual(r.status_code, 500)


class TestChatAgents(MobileBpBase):
    def test_chat_default_limit(self):
        self.api.get_chat_lightweight.return_value = ["m1"]
        r = self.client.get("/api/mobile/chat")
        self.assertEqual(r.get_json(), {"messages": ["m1"]})
        self.api.get_chat_lightweight.assert_called_once_with(10)

    def test_chat_custom_limit(self):
        self.api.get_chat_lightweight.return_value = []
        self.client.get("/api/mobile/chat?limit=3")
        self.api.get_chat_lightweight.assert_called_once_with(3)

    def test_chat_bad_limit_defaults_10(self):
        self.api.get_chat_lightweight.return_value = []
        self.client.get("/api/mobile/chat?limit=abc")
        self.api.get_chat_lightweight.assert_called_once_with(10)

    def test_chat_exception_500(self):
        self.api.get_chat_lightweight.side_effect = RuntimeError("ch")
        r = self.client.get("/api/mobile/chat")
        self.assertEqual(r.status_code, 500)

    def test_agents(self):
        self.api.get_agents_lightweight.return_value = [{"id": "q"}]
        r = self.client.get("/api/mobile/agents")
        self.assertEqual(r.get_json(), {"agents": [{"id": "q"}]})

    def test_agents_exception_500(self):
        self.api.get_agents_lightweight.side_effect = RuntimeError("ag")
        r = self.client.get("/api/mobile/agents")
        self.assertEqual(r.status_code, 500)


class TestTasks(MobileBpBase):
    def test_assign_success(self):
        self.api.assign_task.return_value = "t1"
        r = self.client.post("/api/mobile/tasks/assign", json={
            "device_id": "d1", "description": "sync"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(),
                         {"task_id": "t1", "status": "assigned"})
        self.api.assign_task.assert_called_once_with(
            "d1", "sync", "general")

    def test_assign_full_fields(self):
        self.api.assign_task.return_value = "t2"
        self.client.post("/api/mobile/tasks/assign", json={
            "device_id": "d1", "description": "d",
            "task_type": "coding"})
        self.api.assign_task.assert_called_once_with(
            "d1", "d", "coding")

    def test_assign_failed_400(self):
        self.api.assign_task.return_value = None
        r = self.client.post("/api/mobile/tasks/assign", json={
            "device_id": "d9"})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertEqual(body["error"], "assignment_failed")
        self.assertEqual(body["device_id"], "d9")

    def test_assign_exception_500(self):
        self.api.assign_task.side_effect = RuntimeError("at")
        r = self.client.post("/api/mobile/tasks/assign", json={})
        self.assertEqual(r.status_code, 500)

    def test_pending(self):
        self.api.get_pending_tasks.return_value = [{"id": "t1"}]
        r = self.client.get("/api/mobile/tasks/pending/d1")
        self.assertEqual(r.get_json(),
                         {"tasks": [{"id": "t1"}], "count": 1})
        self.api.get_pending_tasks.assert_called_once_with("d1")

    def test_pending_empty(self):
        self.api.get_pending_tasks.return_value = []
        r = self.client.get("/api/mobile/tasks/pending/d1")
        self.assertEqual(r.get_json(), {"tasks": [], "count": 0})

    def test_pending_exception_500(self):
        self.api.get_pending_tasks.side_effect = RuntimeError("pt")
        r = self.client.get("/api/mobile/tasks/pending/d1")
        self.assertEqual(r.status_code, 500)

    def test_submit_output_ok(self):
        self.api.submit_task_output.return_value = True
        r = self.client.post("/api/mobile/tasks/output/t1", json={
            "device_id": "d1", "output": "done"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"status": "ok"})
        self.api.submit_task_output.assert_called_once_with(
            "d1", "t1", "done")

    def test_submit_output_not_found_404(self):
        self.api.submit_task_output.return_value = False
        r = self.client.post("/api/mobile/tasks/output/t1", json={})
        self.assertEqual(r.status_code, 404)

    def test_submit_output_exception_500(self):
        self.api.submit_task_output.side_effect = RuntimeError("so")
        r = self.client.post("/api/mobile/tasks/output/t1", json={})
        self.assertEqual(r.status_code, 500)

    def test_get_output_found(self):
        self.api.get_task_output.return_value = {"result": "42"}
        r = self.client.get("/api/mobile/tasks/output/t1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"result": "42"})

    def test_get_output_missing_404(self):
        self.api.get_task_output.return_value = None
        r = self.client.get("/api/mobile/tasks/output/none")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "not_found")

    def test_get_output_exception_500(self):
        self.api.get_task_output.side_effect = RuntimeError("go")
        r = self.client.get("/api/mobile/tasks/output/t1")
        self.assertEqual(r.status_code, 500)


class TestNotifyCommand(MobileBpBase):
    def test_notify_ok(self):
        self.api.queue_notification.return_value = True
        r = self.client.post("/api/mobile/notify", json={
            "device_id": "d1", "title": "Hi", "body": "b",
            "data": {"k": "v"}})
        self.assertEqual(r.get_json(), {"status": "ok"})
        self.api.queue_notification.assert_called_once_with(
            "d1", "Hi", "b", {"k": "v"})

    def test_notify_defaults(self):
        self.api.queue_notification.return_value = False
        r = self.client.post("/api/mobile/notify", json={
            "device_id": "d1"})
        self.assertEqual(r.get_json(), {"status": "failed"})
        self.api.queue_notification.assert_called_once_with(
            "d1", "ORBIT", "", {})

    def test_notify_exception_500(self):
        self.api.queue_notification.side_effect = RuntimeError("nf")
        r = self.client.post("/api/mobile/notify", json={})
        self.assertEqual(r.status_code, 500)

    def test_command_allowed(self):
        with patch(VC, return_value=(True, "")):
            self.api.execute_command.return_value = {"out": "ok"}
            r = self.client.post("/api/mobile/command/open_url", json={
                "device_id": "d1", "params": {"u": "x"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"out": "ok"})
        self.api.execute_command.assert_called_once_with(
            "d1", "open_url", {"u": "x"})

    def test_command_allowed_no_body(self):
        with patch(VC, return_value=(True, "")):
            self.api.execute_command.return_value = {"ok": 1}
            r = self.client.post("/api/mobile/command/ping")
        self.api.execute_command.assert_called_once_with("", "ping", {})

    def test_command_blocked_403(self):
        with patch(VC, return_value=(False, "dangerous binary")):
            with self.assertLogs("orbit.core.mobile_bp",
                                 level="WARNING") as cm:
                r = self.client.post("/api/mobile/command/rm_rf")
        self.assertEqual(r.status_code, 403)
        body = r.get_json()
        self.assertEqual(body["error"], "command not allowed")
        self.assertEqual(body["reason"], "dangerous binary")
        self.assertIn("Blocked mobile command rm_rf", cm.output[0])
        self.api.execute_command.assert_not_called()

    def test_command_failed_500(self):
        with patch(VC, return_value=(True, "")):
            self.api.execute_command.return_value = None
            r = self.client.post("/api/mobile/command/broken")
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertEqual(body["error"], "command_failed")
        self.assertEqual(body["command"], "broken")

    def test_command_validate_exception_500(self):
        with patch(VC, side_effect=RuntimeError("vc fail")):
            r = self.client.post("/api/mobile/command/x")
        self.assertEqual(r.status_code, 500)
        self.assertIn("vc fail", r.get_json()["error"])

    def test_command_exception_500(self):
        with patch(VC, return_value=(True, "")):
            self.api.execute_command.side_effect = RuntimeError("ex")
            r = self.client.post("/api/mobile/command/x")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
