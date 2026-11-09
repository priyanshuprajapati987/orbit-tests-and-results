"""Unit tests for orbit/orbit/core/settings_api.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.settings_api import settings_bp


class TestSettingsApi(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(settings_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(settings_bp.name, "settings")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/settings", "/api/settings/<path:key>"]:
            self.assertIn(p, rules)

    def test_get_settings(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.get_all.return_value = {"a": 1}
            r = self.client.get("/api/settings")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["settings"], {"a": 1})

    def test_get_settings_error(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.get_all.side_effect = RuntimeError("boom")
            r = self.client.get("/api/settings")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_update_settings_missing_400(self):
        r = self.client.post("/api/settings", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_update_settings_no_body(self):
        r = self.client.post("/api/settings")
        self.assertEqual(r.status_code, 400)

    def test_update_settings_success(self):
        mgr = patch("orbit.core.settings_api.get_config_manager").start()
        mgr.return_value.set.side_effect = lambda k, v, validate=True: True
        r = self.client.post("/api/settings", json={"settings": {"section": {"key1": "val1", "key2": "val2"}}})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["updated"], 2)
        patch.stopall()

    def test_update_settings_partial(self):
        mgr = patch("orbit.core.settings_api.get_config_manager").start()
        # first set succeeds, second fails
        mgr.return_value.set.side_effect = [True, False]
        r = self.client.post("/api/settings", json={"settings": {"s": {"k1": "v1", "k2": "v2"}}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["updated"], 1)
        patch.stopall()

    def test_update_settings_non_dict_values_skipped(self):
        mgr = patch("orbit.core.settings_api.get_config_manager").start()
        mgr.return_value.set.return_value = True
        r = self.client.post("/api/settings", json={"settings": {"section": "not a dict"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["updated"], 0)
        mgr.return_value.set.assert_not_called()
        patch.stopall()

    def test_update_settings_error(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.set.side_effect = RuntimeError("boom")
            r = self.client.post("/api/settings", json={"settings": {"s": {"k": "v"}}})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_get_setting_found(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.get.return_value = "val"
            r = self.client.get("/api/settings/some.key")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["key"], "some.key")
        self.assertEqual(r.get_json()["value"], "val")
        gm.return_value.get.assert_called_once_with("some.key")

    def test_get_setting_not_found_404(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.get.return_value = None
            r = self.client.get("/api/settings/some.key")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())

    def test_get_setting_error(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.get.side_effect = RuntimeError("boom")
            r = self.client.get("/api/settings/some.key")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())

    def test_set_setting_missing_value_400(self):
        r = self.client.put("/api/settings/some.key", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_setting_no_body(self):
        r = self.client.put("/api/settings/some.key")
        self.assertEqual(r.status_code, 400)

    def test_set_setting_success(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.set.return_value = True
            r = self.client.put("/api/settings/some.key", json={"value": "newval"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])
        self.assertEqual(r.get_json()["key"], "some.key")
        self.assertEqual(r.get_json()["value"], "newval")
        gm.return_value.set.assert_called_once_with("some.key", "newval", validate=True)

    def test_set_setting_validation_failed_400(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.set.return_value = False
            r = self.client.put("/api/settings/some.key", json={"value": "bad"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_set_setting_error(self):
        with patch("orbit.core.settings_api.get_config_manager") as gm:
            gm.return_value.set.side_effect = RuntimeError("boom")
            r = self.client.put("/api/settings/some.key", json={"value": "v"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.get_json())


if __name__ == "__main__":
    unittest.main()
