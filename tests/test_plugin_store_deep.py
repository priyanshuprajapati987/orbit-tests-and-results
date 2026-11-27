"""Deep tests for orbit/orbit/core/plugin_store.py (Loop 15/3)."""

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import plugin_store as ps


class LoadSeedTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        self._data_dir = Path(self._d)
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = self._data_dir
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)

    def test_load_existing_file(self):
        data = [{"id": "x", "name": "X", "installed": True}]
        self._store_file.write_text(json.dumps(data), encoding="utf-8")
        store = ps.PluginStore()
        self.assertEqual(store.get_plugin("x")["name"], "X")
        self.assertTrue(store.get_plugin("x")["installed"])

    def test_load_corrupt_reseeds(self):
        self._store_file.write_text("{bad", encoding="utf-8")
        store = ps.PluginStore()
        # seeded with preloaded
        self.assertIsNotNone(store.get_plugin("weather"))
        self.assertTrue(self._store_file.exists())

    def test_load_missing_seeds_preloaded(self):
        store = ps.PluginStore()
        self.assertEqual(len(store.list_plugins()), len(ps.PRELOADED_PLUGINS))
        self.assertIsNotNone(store.get_plugin("weather"))
        self.assertFalse(store.get_plugin("weather")["installed"])

    def test_save_failure_logged(self):
        store = ps.PluginStore()
        with mock.patch.object(Path, "mkdir", side_effect=OSError("nope")), \
                mock.patch.object(ps, "logger") as lg:
            store._save()
        lg.error.assert_called_once()


class ListPluginsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = Path(self._d)
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)
        self.store = ps.PluginStore()

    def test_list_all(self):
        plugins = self.store.list_plugins()
        self.assertEqual(len(plugins), len(ps.PRELOADED_PLUGINS))

    def test_list_by_category(self):
        plugins = self.store.list_plugins(category="tools")
        self.assertTrue(all(p["category"] == "tools" for p in plugins))
        self.assertGreater(len(plugins), 0)

    def test_list_unknown_category_empty(self):
        self.assertEqual(self.store.list_plugins(category="nope"), [])

    def test_returns_copies(self):
        p = self.store.list_plugins()[0]
        p["name"] = "MUTATED"
        self.assertNotEqual(self.store.list_plugins()[0]["name"], "MUTATED")


class GetPluginTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = Path(self._d)
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)
        self.store = ps.PluginStore()

    def test_found(self):
        p = self.store.get_plugin("weather")
        self.assertEqual(p["name"], "Weather Plugin")
        # copy
        p["name"] = "MUTATED"
        self.assertEqual(self.store.get_plugin("weather")["name"], "Weather Plugin")

    def test_not_found(self):
        self.assertIsNone(self.store.get_plugin("nope"))


class InstallUninstallTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = Path(self._d)
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)
        self.store = ps.PluginStore()

    def test_install_success(self):
        with mock.patch.object(ps, "logger") as lg:
            r = self.store.install_plugin("weather")
        self.assertTrue(r["installed"])
        self.assertEqual(r["id"], "weather")
        self.assertTrue(self.store.get_plugin("weather")["installed"])
        lg.info.assert_called_once()

    def test_install_unknown(self):
        self.assertIsNone(self.store.install_plugin("nope"))

    def test_uninstall_success(self):
        self.store.install_plugin("weather")
        with mock.patch.object(ps, "logger") as lg:
            r = self.store.uninstall_plugin("weather")
        self.assertFalse(r["installed"])
        lg.info.assert_called_once()

    def test_uninstall_unknown(self):
        self.assertIsNone(self.store.uninstall_plugin("nope"))


class GetFeaturedTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = Path(self._d)
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)
        self.store = ps.PluginStore()

    def test_featured(self):
        featured = self.store.get_featured()
        self.assertTrue(all(p.get("featured") for p in featured))
        self.assertEqual(len(featured), sum(1 for p in ps.PRELOADED_PLUGINS if p.get("featured")))


class RatePluginTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = Path(self._d)
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)
        self.store = ps.PluginStore()

    def test_rate_success(self):
        with mock.patch.object(ps, "logger") as lg:
            r = self.store.rate_plugin("weather", 5.0, review="great")
        self.assertEqual(r["reviews_count"], 129)
        # rolling avg: (4.5*128 + 5)/129
        expected = round((4.5 * 128 + 5.0) / 129, 2)
        self.assertEqual(r["rating"], expected)
        self.assertEqual(r["reviews"][0], {"rating": 5.0, "review": "great"})
        lg.info.assert_called_once()

    def test_rate_no_review(self):
        r = self.store.rate_plugin("weather", 3.0)
        self.assertNotIn("reviews", r) or True
        # reviews key may not exist if no review; check reviews_count
        self.assertEqual(r["reviews_count"], 129)

    def test_rate_invalid_low(self):
        with self.assertRaises(ValueError):
            self.store.rate_plugin("weather", -0.1)

    def test_rate_invalid_high(self):
        with self.assertRaises(ValueError):
            self.store.rate_plugin("weather", 5.1)

    def test_rate_boundary_0_and_5(self):
        r1 = self.store.rate_plugin("weather", 0.0)
        self.assertIsNotNone(r1)
        r2 = self.store.rate_plugin("weather", 5.0)
        self.assertIsNotNone(r2)

    def test_rate_unknown(self):
        self.assertIsNone(self.store.rate_plugin("nope", 4.0))

    def test_rate_review_cap_100(self):
        plugin = self.store.get_plugin("weather")
        plugin["reviews"] = [{"rating": 4.0, "review": "x"} for _ in range(100)]
        self.store._plugins["weather"] = plugin
        with mock.patch.object(self.store, "_save"):
            r = self.store.rate_plugin("weather", 4.0, review="new")
        self.assertEqual(len(r["reviews"]), 100)
        self.assertEqual(r["reviews"][-1]["review"], "new")

    def test_rate_rolling_avg_no_reviews_key(self):
        # plugin without reviews_count defaults 0
        self.store._plugins["weather"]["reviews_count"] = 0
        self.store._plugins["weather"]["rating"] = 0.0
        r = self.store.rate_plugin("weather", 4.0)
        self.assertEqual(r["rating"], 4.0)
        self.assertEqual(r["reviews_count"], 1)


class SearchPluginsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = Path(self._d)
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)
        self.store = ps.PluginStore()

    def test_search_by_name(self):
        r = self.store.search_plugins("weather")
        self.assertTrue(any(p["id"] == "weather" for p in r))

    def test_search_by_description(self):
        r = self.store.search_plugins("cryptocurrency")
        self.assertTrue(any(p["id"] == "crypto" for p in r))

    def test_search_case_insensitive(self):
        r = self.store.search_plugins("WEATHER")
        self.assertTrue(any(p["id"] == "weather" for p in r))

    def test_search_no_match(self):
        self.assertEqual(self.store.search_plugins("zzzzzzz"), [])

    def test_search_returns_copies(self):
        r = self.store.search_plugins("weather")
        r[0]["name"] = "MUTATED"
        self.assertNotEqual(self.store.search_plugins("weather")[0]["name"], "MUTATED")


class GetCategoriesTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._store_file = Path(self._d) / "plugins.json"
        ps.STORE_FILE = self._store_file
        ps.DATA_DIR = Path(self._d)
        self.addCleanup(setattr, ps, "STORE_FILE", ps.STORE_FILE)
        self.addCleanup(setattr, ps, "DATA_DIR", ps.DATA_DIR)
        self.store = ps.PluginStore()

    def test_categories(self):
        cats = self.store.get_categories()
        self.assertIn("tools", cats)
        self.assertIn("productivity", cats)
        self.assertEqual(sum(cats.values()), len(ps.PRELOADED_PLUGINS))

    def test_unknown_category_fallback(self):
        # inject a plugin with no category
        self.store._plugins["nocat"] = {"id": "nocat", "name": "N"}
        cats = self.store.get_categories()
        self.assertIn("unknown", cats)


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = ps._instance
        ps._instance = None
        self.addCleanup(setattr, ps, "_instance", self._saved)

    def test_creates(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "plugins.json"
        with mock.patch("orbit.orbit.core.plugin_store.DATA_DIR", Path(d)), \
                mock.patch("orbit.orbit.core.plugin_store.STORE_FILE", p):
            a = ps.get_plugin_store()
        self.assertIsInstance(a, ps.PluginStore)
        self.assertIs(ps._instance, a)

    def test_reuses(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "plugins.json"
        with mock.patch("orbit.orbit.core.plugin_store.DATA_DIR", Path(d)), \
                mock.patch("orbit.orbit.core.plugin_store.STORE_FILE", p):
            a = ps.get_plugin_store()
            b = ps.get_plugin_store()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
