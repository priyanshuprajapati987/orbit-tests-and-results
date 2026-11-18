"""Unit tests for orbit/orbit/core/plugin_store_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.plugin_store_bp import plugin_store_bp


class TestPluginStoreBpBase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(plugin_store_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(plugin_store_bp.name, "plugin_store_bp")
        self.assertEqual(plugin_store_bp.url_prefix, "/api/plugin-store")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/plugin-store/list", "/api/plugin-store/featured",
                  "/api/plugin-store/categories", "/api/plugin-store/search",
                  "/api/plugin-store/install/<plugin_id>",
                  "/api/plugin-store/uninstall/<plugin_id>",
                  "/api/plugin-store/rate/<plugin_id>"]:
            self.assertIn(p, rules)


class TestList(TestPluginStoreBpBase):
    def test_list_success(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.list_plugins.return_value = [{"id": "p1"}]
            r = self.client.get("/api/plugin-store/list")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["plugins"], [{"id": "p1"}])
        gs.return_value.list_plugins.assert_called_once_with(category=None)

    def test_list_with_category(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.list_plugins.return_value = []
            r = self.client.get("/api/plugin-store/list?category=tools")
        self.assertEqual(r.status_code, 200)
        gs.return_value.list_plugins.assert_called_once_with(category="tools")

    def test_list_exception_500(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store", side_effect=RuntimeError("x")):
            r = self.client.get("/api/plugin-store/list")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "internal error")


class TestFeatured(TestPluginStoreBpBase):
    def test_featured_success(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.get_featured.return_value = [{"id": "f1"}]
            r = self.client.get("/api/plugin-store/featured")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 1)

    def test_featured_exception_500(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store", side_effect=RuntimeError("x")):
            r = self.client.get("/api/plugin-store/featured")
        self.assertEqual(r.status_code, 500)


class TestCategories(TestPluginStoreBpBase):
    def test_categories_success(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.get_categories.return_value = ["tools", "games"]
            r = self.client.get("/api/plugin-store/categories")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["categories"], ["tools", "games"])

    def test_categories_exception_500(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store", side_effect=RuntimeError("x")):
            r = self.client.get("/api/plugin-store/categories")
        self.assertEqual(r.status_code, 500)


class TestInstall(TestPluginStoreBpBase):
    def test_install_success(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.install_plugin.return_value = {"id": "p1", "installed": True}
            r = self.client.post("/api/plugin-store/install/p1")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["plugin"]["id"], "p1")

    def test_install_not_found_404(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.install_plugin.return_value = None
            r = self.client.post("/api/plugin-store/install/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["plugin_id"], "nope")

    def test_install_exception_500(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store", side_effect=RuntimeError("x")):
            r = self.client.post("/api/plugin-store/install/p1")
        self.assertEqual(r.status_code, 500)


class TestUninstall(TestPluginStoreBpBase):
    def test_uninstall_success(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.uninstall_plugin.return_value = {"id": "p1"}
            r = self.client.post("/api/plugin-store/uninstall/p1")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])

    def test_uninstall_not_found_404(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.uninstall_plugin.return_value = None
            r = self.client.post("/api/plugin-store/uninstall/nope")
        self.assertEqual(r.status_code, 404)

    def test_uninstall_exception_500(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store", side_effect=RuntimeError("x")):
            r = self.client.post("/api/plugin-store/uninstall/p1")
        self.assertEqual(r.status_code, 500)


class TestRate(TestPluginStoreBpBase):
    def test_rate_success(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.rate_plugin.return_value = {"id": "p1", "rating": 4.5}
            r = self.client.post("/api/plugin-store/rate/p1", json={"rating": 4.5, "review": "nice"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["success"])
        gs.return_value.rate_plugin.assert_called_once_with("p1", 4.5, review="nice")

    def test_rate_missing_rating_400(self):
        r = self.client.post("/api/plugin-store/rate/p1", json={"review": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("rating is required", r.get_json()["error"])

    def test_rate_no_body_400(self):
        r = self.client.post("/api/plugin-store/rate/p1")
        self.assertEqual(r.status_code, 400)

    def test_rate_non_numeric_400(self):
        r = self.client.post("/api/plugin-store/rate/p1", json={"rating": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("rating must be a number", r.get_json()["error"])

    def test_rate_string_number_coerced(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.rate_plugin.return_value = {"id": "p1", "rating": 3.0}
            r = self.client.post("/api/plugin-store/rate/p1", json={"rating": "3"})
        self.assertEqual(r.status_code, 200)
        gs.return_value.rate_plugin.assert_called_once_with("p1", 3.0, review=None)

    def test_rate_store_valueerror_400(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.rate_plugin.side_effect = ValueError("rating must be between 1 and 5")
            r = self.client.post("/api/plugin-store/rate/p1", json={"rating": 99})
        self.assertEqual(r.status_code, 400)
        self.assertIn("between 1 and 5", r.get_json()["error"])

    def test_rate_not_found_404(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.rate_plugin.return_value = None
            r = self.client.post("/api/plugin-store/rate/nope", json={"rating": 3})
        self.assertEqual(r.status_code, 404)

    def test_rate_exception_500(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store", side_effect=RuntimeError("x")):
            r = self.client.post("/api/plugin-store/rate/p1", json={"rating": 3})
        self.assertEqual(r.status_code, 500)


class TestSearch(TestPluginStoreBpBase):
    def test_search_success(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store") as gs:
            gs.return_value.search_plugins.return_value = [{"id": "p1"}]
            r = self.client.get("/api/plugin-store/search?q=weather")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["query"], "weather")
        self.assertEqual(body["count"], 1)
        gs.return_value.search_plugins.assert_called_once_with("weather")

    def test_search_missing_q_400(self):
        r = self.client.get("/api/plugin-store/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("q parameter is required", r.get_json()["error"])

    def test_search_blank_q_400(self):
        r = self.client.get("/api/plugin-store/search?q=%20%20")
        self.assertEqual(r.status_code, 400)

    def test_search_exception_500(self):
        with patch("orbit.core.plugin_store_bp.get_plugin_store", side_effect=RuntimeError("x")):
            r = self.client.get("/api/plugin-store/search?q=x")
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
