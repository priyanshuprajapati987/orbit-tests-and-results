"""Unit tests for orbit/orbit/core/incident_response.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # for orbit.orbit.* imports

from orbit.orbit.core.incident_response import SecureIncidentExecutor


def make_action(status="success", takes_arg=False):
    if takes_arg:
        def f(alert_data):
            return {"status": status}
    else:
        def f():
            return {"status": status}
    return f


class TestSecureIncidentExecutor(unittest.TestCase):
    def setUp(self):
        self.actions = {
            "isolate_devices": make_action("isolated", takes_arg=True),
            "rotate_all_api_keys": make_action("rotated"),
            "missing_action": None,  # not in registry
        }
        self.patcher = patch("orbit.orbit.core.incident_actions.INCIDENT_ACTIONS", self.actions)
        self.patcher2 = patch("orbit.orbit.core.incident_response.INCIDENT_ACTIONS", self.actions)
        self.patcher.start()
        self.patcher2.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.patcher2.stop)
        self.executor = SecureIncidentExecutor()

    def test_classify_threat(self):
        r = self.executor.classify_threat("data_exfiltration", {"ip": "1.2.3.4"})
        self.assertEqual(r["type"], "data_exfiltration")
        self.assertEqual(r["severity"], "high")

    def test_get_allowed_playbooks(self):
        pb = self.executor.get_allowed_playbooks()
        self.assertIn("data_exfiltration", pb)
        self.assertIn("unauthorized_access", pb)

    def test_unauthorized_playbook(self):
        r = self.executor.execute_incident_playbook("unknown_threat", {})
        self.assertFalse(r["success"])
        self.assertEqual(r["error"], "playbook_not_authorized")

    def test_execute_success(self):
        # register isolate_devices and rotate in allowed playbooks via override
        self.executor.get_allowed_playbooks = lambda: {"data_exfiltration": ["isolate_devices", "rotate_all_api_keys"]}
        r = self.executor.execute_incident_playbook("data_exfiltration", {"ip": "1.2.3.4"})
        self.assertTrue(r["success"])
        self.assertEqual(len(r["actions_executed"]), 2)
        self.assertEqual(r["actions_executed"][0]["action"], "isolate_devices")
        self.assertEqual(r["actions_executed"][0]["status"], "isolated")
        self.assertEqual(r["actions_executed"][1]["status"], "rotated")

    def test_unregistered_action(self):
        self.actions["ghost"] = None
        # Actually need action in registry? Let's test action not in registry
        self.executor.get_allowed_playbooks = lambda: {"data_exfiltration": ["nonexistent_action"]}
        r = self.executor.execute_incident_playbook("data_exfiltration", {})
        self.assertTrue(r["success"])
        self.assertEqual(r["actions_executed"][0]["status"], "error")
        self.assertEqual(r["actions_executed"][0]["error"], "action_not_registered")

    def test_action_exception(self):
        def boom(alert_data):
            raise RuntimeError("action failed")

        self.actions["boom_action"] = boom
        self.executor.get_allowed_playbooks = lambda: {"data_exfiltration": ["boom_action"]}
        r = self.executor.execute_incident_playbook("data_exfiltration", {})
        self.assertTrue(r["success"])
        self.assertEqual(r["actions_executed"][0]["status"], "error")
        self.assertIn("action failed", r["actions_executed"][0]["error"])

    def test_action_no_arg(self):
        def noarg():
            return {"status": "done"}

        self.actions["noarg_action"] = noarg
        self.executor.get_allowed_playbooks = lambda: {"data_exfiltration": ["noarg_action"]}
        r = self.executor.execute_incident_playbook("data_exfiltration", {"x": 1})
        self.assertEqual(r["actions_executed"][0]["status"], "done")

    def test_action_signature_inspection_failure(self):
        # object without __call__ signature? Use a mock with parameters attr failing
        class Weird:
            def __call__(self):
                return {"status": "weird"}

        w = Weird()
        self.actions["weird_action"] = w
        self.executor.get_allowed_playbooks = lambda: {"data_exfiltration": ["weird_action"]}
        r = self.executor.execute_incident_playbook("data_exfiltration", {})
        # inspect.signature on instance may fail → wants_arg False → called with no args
        self.assertTrue(r["success"])


if __name__ == "__main__":
    unittest.main()
