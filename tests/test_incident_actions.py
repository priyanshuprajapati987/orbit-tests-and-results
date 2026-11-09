"""Unit tests for orbit/orbit/core/incident_actions.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.incident_actions import (
    ActionStatus,
    INCIDENT_ACTIONS,
    register_action,
    isolate_devices,
    rotate_all_api_keys,
    enable_full_disk_encryption,
    start_forensic_capture,
    notify_compliance_team,
    block_ips_from_threat_feed,
)


class TestActionStatus(unittest.TestCase):
    def test_values(self):
        self.assertEqual(ActionStatus.SUCCESS.value, "success")
        self.assertEqual(ActionStatus.BLOCKED.value, "blocked")
        self.assertEqual(ActionStatus.ERROR.value, "error")


class TestIncidentActions(unittest.TestCase):
    def test_registry_populated(self):
        self.assertIn("isolate_devices", INCIDENT_ACTIONS)
        self.assertIn("rotate_all_api_keys", INCIDENT_ACTIONS)
        self.assertIn("enable_full_disk_encryption", INCIDENT_ACTIONS)
        self.assertIn("start_forensic_capture", INCIDENT_ACTIONS)
        self.assertIn("notify_compliance_team", INCIDENT_ACTIONS)
        self.assertIn("block_ips_from_threat_feed", INCIDENT_ACTIONS)
        self.assertEqual(len(INCIDENT_ACTIONS), 6)

    def test_register_action_decorator(self):
        @register_action("test_action_xyz")
        def f():
            return {"status": "ok"}
        self.assertIn("test_action_xyz", INCIDENT_ACTIONS)
        self.assertEqual(INCIDENT_ACTIONS["test_action_xyz"](), {"status": "ok"})
        # cleanup
        del INCIDENT_ACTIONS["test_action_xyz"]

    def test_isolate_devices_no_match(self):
        dm = MagicMock()
        dm.devices = {}
        with patch("orbit.core.device_manager.device_manager", dm):
            r = isolate_devices("dev1,dev2")
        self.assertEqual(r["isolated"], [])
        self.assertEqual(r["count"], 0)

    def test_isolate_devices_match(self):
        dm = MagicMock()
        dm.devices = {"dev1": {}, "dev2": {}}
        with patch("orbit.core.device_manager.device_manager", dm):
            r = isolate_devices("dev1, dev2")
        self.assertEqual(r["isolated"], ["dev1", "dev2"])
        self.assertEqual(r["count"], 2)
        self.assertEqual(dm.revoke_device.call_count, 2)

    def test_isolate_devices_dict_alert_data(self):
        dm = MagicMock()
        dm.devices = {"dev1": {}}
        with patch("orbit.core.device_manager.device_manager", dm):
            r = isolate_devices({"device_ids": "dev1"})
        self.assertEqual(r["isolated"], ["dev1"])

    def test_isolate_devices_dict_devices_key(self):
        dm = MagicMock()
        dm.devices = {"dev2": {}}
        with patch("orbit.core.device_manager.device_manager", dm):
            r = isolate_devices({"devices": "dev2"})
        self.assertEqual(r["isolated"], ["dev2"])

    def test_isolate_devices_empty_string(self):
        dm = MagicMock()
        dm.devices = {"dev1": {}}
        with patch("orbit.core.device_manager.device_manager", dm):
            r = isolate_devices("")
        self.assertEqual(r["isolated"], [])
        self.assertEqual(r["count"], 0)

    def test_isolate_devices_none(self):
        dm = MagicMock()
        dm.devices = {"dev1": {}}
        with patch("orbit.core.device_manager.device_manager", dm):
            r = isolate_devices(None)
        self.assertEqual(r["isolated"], [])
        self.assertEqual(r["count"], 0)

    def test_rotate_stub(self):
        r = rotate_all_api_keys()
        self.assertEqual(r["status"], "stub")
        self.assertEqual(r["action"], "rotate_all_api_keys")

    def test_enable_disk_encryption_stub(self):
        r = enable_full_disk_encryption()
        self.assertEqual(r["status"], "stub")
        self.assertEqual(r["action"], "enable_full_disk_encryption")

    def test_forensic_capture_stub(self):
        r = start_forensic_capture()
        self.assertEqual(r["status"], "stub")
        self.assertEqual(r["action"], "start_forensic_capture")

    def test_notify_compliance_stub(self):
        r = notify_compliance_team()
        self.assertEqual(r["status"], "stub")
        self.assertEqual(r["action"], "notify_compliance_team")

    def test_block_ips_stub(self):
        r = block_ips_from_threat_feed()
        self.assertEqual(r["status"], "stub")
        self.assertEqual(r["action"], "block_ips_from_threat_feed")


if __name__ == "__main__":
    unittest.main()
