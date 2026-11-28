"""Deep tests for orbit/orbit/core/config_manager.py (Loop 20/5)."""

import json
import os
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import config_manager as cm


class InitTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._cfg = Path(self._d) / "orbit_config.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self, env="development", cfg_file=None):
        cf = cfg_file or str(self._cfg)
        with mock.patch("orbit.orbit.core.config_manager.app_root",
                        return_value=Path(self._d)), \
                mock.patch("orbit.orbit.core.config_manager.VERSION", "3.7.0", create=True):
            # version import happens inside; patch module
            with mock.patch("orbit.orbit.core.version.VERSION", "3.7.0", create=True):
                m = cm.ConfigManager(config_file=cf, env=env)
        return m

    def test_init_defaults(self):
        m = self._make()
        self.assertEqual(m.env, "development")
        self.assertEqual(m.config["app"]["version"], "3.7.0")
        self.assertEqual(m.config["app"]["name"], "ORBIT")
        self.assertFalse(m.config["app"]["debug"])
        self.assertEqual(m.config["app"]["log_level"], "INFO")
        self.assertEqual(m.config["llm"]["default_provider"], "openrouter")
        self.assertEqual(m.config["llm"]["max_retries"], 3)
        self.assertTrue(m.config["cache"]["enabled"])
        self.assertEqual(m.config["cache"]["ttl"], 300)
        self.assertTrue(m.config["rate_limit"]["enabled"])
        self.assertTrue(m.config["security"]["permission_system"])
        self.assertTrue(m.config["notifications"]["desktop"])
        self.assertFalse(m.config["notifications"]["email"])
        self.assertEqual(m.history, [])
        self.assertEqual(m.watchers, {})

    def test_init_env_from_os(self):
        with mock.patch.dict(os.environ, {"ORBIT_ENV": "production"}):
            m = self._make(env=None)
        self.assertEqual(m.env, "production")

    def test_init_loads_existing_config(self):
        self._cfg.write_text(json.dumps({"app": {"version": "2.0.0", "debug": True},
                                        "custom": "x"}), encoding="utf-8")
        m = self._make()
        # version synced to 3.7.0
        self.assertEqual(m.config["app"]["version"], "3.7.0")
        self.assertTrue(m.config["app"]["debug"])
        # custom preserved
        self.assertEqual(m.config["custom"], "x")
        # defaults merged for missing sections
        self.assertIn("llm", m.config)

    def test_init_corrupt_config(self):
        self._cfg.write_text("{bad", encoding="utf-8")
        m = self._make()
        # config reset to {} then defaults applied
        self.assertIn("app", m.config)
        self.assertEqual(m.config["app"]["version"], "3.7.0")

    def test_init_non_dict_config(self):
        self._cfg.write_text('[1,2]', encoding="utf-8")
        m = self._make()
        self.assertIn("app", m.config)

    def test_ensure_config_dir(self):
        m = cm.ConfigManager.__new__(cm.ConfigManager)
        m.config_file = str(self._cfg)
        m._ensure_config_dir()
        self.assertTrue(self._cfg.parent.exists())

    def test_sync_version_import_failure(self):
        # version import fails -> uses 3.7.0 fallback
        with mock.patch("orbit.orbit.core.version.VERSION", side_effect=ImportError, create=True):
            # make import fail by removing module
            pass
        # Simpler: patch builtins __import__ to fail for version module
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if "version" in name:
                raise ImportError("no version")
            return real_import(name, *a, **k)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            m = self._make()
        self.assertEqual(m.config["app"]["version"], "3.7.0")


class GetTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._cfg = Path(self._d) / "orbit_config.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.config_manager.app_root",
                        return_value=Path(self._d)), \
                mock.patch("orbit.orbit.core.version.VERSION", "3.7.0", create=True):
            return cm.ConfigManager(config_file=str(self._cfg))

    def test_get_simple(self):
        m = self._make()
        self.assertEqual(m.get("app.name"), "ORBIT")
        self.assertEqual(m.get("app.version"), "3.7.0")

    def test_get_nested(self):
        m = self._make()
        self.assertEqual(m.get("llm.default_provider"), "openrouter")
        self.assertEqual(m.get("llm.max_retries"), 3)

    def test_get_missing_returns_default(self):
        m = self._make()
        self.assertIsNone(m.get("nope"))
        self.assertEqual(m.get("nope", "default"), "default")
        self.assertEqual(m.get("app.nope", 42), 42)

    def test_get_partial_path_missing(self):
        m = self._make()
        self.assertIsNone(m.get("app.name.x"))

    def test_get_non_dict_intermediate(self):
        m = self._make()
        m.config["x"] = "string"
        self.assertIsNone(m.get("x.y"))

    def test_get_top_level(self):
        m = self._make()
        self.assertIsInstance(m.get("app"), dict)


class SetTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._cfg = Path(self._d) / "orbit_config.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.config_manager.app_root",
                        return_value=Path(self._d)), \
                mock.patch("orbit.orbit.core.version.VERSION", "3.7.0", create=True):
            return cm.ConfigManager(config_file=str(self._cfg))

    def test_set_success(self):
        m = self._make()
        with mock.patch.object(m, "_notify_watchers") as nw:
            r = m.set("app.debug", True)
        self.assertTrue(r)
        self.assertTrue(m.config["app"]["debug"])
        self.assertEqual(len(m.history), 1)
        self.assertEqual(m.history[0]["key"], "app.debug")
        self.assertFalse(m.history[0]["old_value"])
        self.assertTrue(m.history[0]["new_value"])
        self.assertIn("timestamp", m.history[0])
        nw.assert_called_once_with("app.debug", True, False)

    def test_set_creates_intermediate(self):
        m = self._make()
        m.set("new.section.key", "val")
        self.assertEqual(m.config["new"]["section"]["key"], "val")

    def test_set_validation_fail(self):
        m = self._make()
        with mock.patch.object(m, "_notify_watchers") as nw:
            r = m.set("app.log_level", "INVALID")
        self.assertFalse(r)
        # value not changed
        self.assertEqual(m.config["app"]["log_level"], "INFO")
        self.assertEqual(len(m.history), 0)
        nw.assert_not_called()

    def test_set_validation_pass(self):
        m = self._make()
        r = m.set("app.log_level", "DEBUG")
        self.assertTrue(r)
        self.assertEqual(m.config["app"]["log_level"], "DEBUG")

    def test_set_llm_max_retries_valid(self):
        m = self._make()
        r = m.set("llm.max_retries", 5)
        self.assertTrue(r)

    def test_set_llm_max_retries_invalid(self):
        m = self._make()
        r = m.set("llm.max_retries", -1)
        self.assertFalse(r)

    def test_set_cache_ttl_valid(self):
        m = self._make()
        r = m.set("cache.ttl", 600)
        self.assertTrue(r)

    def test_set_cache_ttl_invalid(self):
        m = self._make()
        r = m.set("cache.ttl", 0)
        self.assertFalse(r)

    def test_set_cache_max_size_valid(self):
        m = self._make()
        r = m.set("cache.max_size", 500)
        self.assertTrue(r)

    def test_set_cache_max_size_invalid(self):
        m = self._make()
        r = m.set("cache.max_size", 0)
        self.assertFalse(r)

    def test_set_security_max_login_attempts(self):
        m = self._make()
        r = m.set("security.max_login_attempts", 3)
        self.assertTrue(r)
        r2 = m.set("security.max_login_attempts", 0)
        self.assertFalse(r2)

    def test_set_validation_disabled(self):
        m = self._make()
        r = m.set("app.log_level", "INVALID", validate=False)
        self.assertTrue(r)
        self.assertEqual(m.config["app"]["log_level"], "INVALID")

    def test_set_unvalidated_key_always_ok(self):
        m = self._make()
        r = m.set("random.key", 42)
        self.assertTrue(r)

    def test_set_history_cap_100(self):
        m = self._make()
        for i in range(110):
            m.set("app.debug", bool(i % 2), validate=False)
        self.assertEqual(len(m.history), 100)

    def test_set_persists(self):
        m = self._make()
        m.set("app.debug", True, validate=False)
        # reload
        m2 = self._make()
        self.assertTrue(m2.config["app"]["debug"])

    def test_set_validation_fail_does_not_persist(self):
        m = self._make()
        m.set("app.log_level", "INVALID")
        m2 = self._make()
        self.assertEqual(m2.config["app"]["log_level"], "INFO")

    def test_set_notify_watchers_called(self):
        m = self._make()
        cb = mock.MagicMock()
        m.watch("app", cb)
        m.set("app.debug", True, validate=False)
        cb.assert_called_once_with("app.debug", True, False)

    def test_set_logs(self):
        m = self._make()
        with mock.patch.object(cm, "logger") as lg:
            m.set("app.debug", True, validate=False)
        lg.info.assert_called_once()

    def test_set_validation_fail_logs_warning(self):
        m = self._make()
        with mock.patch.object(cm, "logger") as lg:
            m.set("app.log_level", "INVALID")
        lg.warning.assert_called_once()

    def test_set_save_failure(self):
        m = self._make()
        with mock.patch.object(m, "_save_config", side_effect=Exception("save fail")):
            # _save_config catches internally; but if we make it raise, set propagates?
            pass
        # Instead test _save_config failure logged
        m2 = self._make()
        with mock.patch("builtins.open", side_effect=OSError("boom")):
            ok = m2._save_config()
        # _save_config returns None (no explicit return) but logs
        # Actually it catches and logs; returns None
        self.assertIsNone(ok)


class ValidateValueTests(unittest.TestCase):
    def test_validators(self):
        m = cm.ConfigManager.__new__(cm.ConfigManager)
        m.config = {}
        m.defaults = {}
        m.history = []
        m.watchers = {}
        m._lock = threading.Lock()
        m.config_file = "/tmp/x.json"
        m.env = "dev"
        # access _validate_value directly
        self.assertTrue(m._validate_value("app.log_level", "INFO"))
        self.assertFalse(m._validate_value("app.log_level", "NOPE"))
        self.assertTrue(m._validate_value("llm.max_retries", 3))
        self.assertFalse(m._validate_value("llm.max_retries", -1))
        self.assertFalse(m._validate_value("llm.max_retries", "x"))
        self.assertTrue(m._validate_value("cache.ttl", 300))
        self.assertFalse(m._validate_value("cache.ttl", 0))
        self.assertTrue(m._validate_value("cache.max_size", 100))
        self.assertFalse(m._validate_value("cache.max_size", 0))
        self.assertTrue(m._validate_value("security.max_login_attempts", 5))
        self.assertFalse(m._validate_value("security.max_login_attempts", 0))
        self.assertTrue(m._validate_value("other.key", "anything"))


class WatchNotifyTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._cfg = Path(self._d) / "orbit_config.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.config_manager.app_root",
                        return_value=Path(self._d)), \
                mock.patch("orbit.orbit.core.version.VERSION", "3.7.0", create=True):
            return cm.ConfigManager(config_file=str(self._cfg))

    def test_watch_registers(self):
        m = self._make()
        cb = mock.MagicMock()
        m.watch("app", cb)
        self.assertEqual(m.watchers, {"app": [cb]})

    def test_watch_multiple(self):
        m = self._make()
        cb1 = mock.MagicMock()
        cb2 = mock.MagicMock()
        m.watch("app", cb1)
        m.watch("app", cb2)
        self.assertEqual(len(m.watchers["app"]), 2)

    def test_notify_exact_prefix(self):
        m = self._make()
        cb = mock.MagicMock()
        m.watchers["app"] = [cb]
        m._notify_watchers("app.debug", True, False)
        cb.assert_called_once_with("app.debug", True, False)

    def test_notify_reverse_prefix(self):
        m = self._make()
        cb = mock.MagicMock()
        m.watchers["app.debug"] = [cb]
        m._notify_watchers("app", True, False)
        cb.assert_called_once()

    def test_notify_callback_exception_logged(self):
        m = self._make()
        cb = mock.MagicMock(side_effect=RuntimeError("boom"))
        m.watchers["app"] = [cb]
        with mock.patch.object(cm, "logger") as lg:
            m._notify_watchers("app.debug", True, False)
        lg.error.assert_called_once()

    def test_notify_no_match(self):
        m = self._make()
        cb = mock.MagicMock()
        m.watchers["other"] = [cb]
        m._notify_watchers("app.debug", True, False)
        cb.assert_not_called()


class GetSectionDeleteResetTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._cfg = Path(self._d) / "orbit_config.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.config_manager.app_root",
                        return_value=Path(self._d)), \
                mock.patch("orbit.orbit.core.version.VERSION", "3.7.0", create=True):
            return cm.ConfigManager(config_file=str(self._cfg))

    def test_get_section(self):
        m = self._make()
        self.assertEqual(m.get_section("app"), m.config["app"])
        self.assertEqual(m.get_section("nope"), {})

    def test_get_all(self):
        m = self._make()
        c = m.get_all()
        self.assertEqual(c, m.config)
        # copy
        c["x"] = 1
        self.assertNotIn("x", m.config)

    def test_delete_success(self):
        m = self._make()
        m.set("app.debug", True, validate=False)
        self.assertTrue(m.delete("app.debug"))
        self.assertNotIn("debug", m.config["app"])

    def test_delete_missing_key(self):
        m = self._make()
        self.assertFalse(m.delete("app.nope"))

    def test_delete_missing_section(self):
        m = self._make()
        self.assertFalse(m.delete("nope.key"))

    def test_delete_persists(self):
        m = self._make()
        m.set("app.debug", True, validate=False)
        m.delete("app.debug")
        m2 = self._make()
        self.assertNotIn("debug", m2.config.get("app", {}))

    def test_reset_key(self):
        m = self._make()
        m.set("app.log_level", "DEBUG", validate=False)
        m.reset("app.log_level")
        self.assertEqual(m.config["app"]["log_level"], "INFO")

    def test_reset_key_missing_in_defaults(self):
        m = self._make()
        m.reset("nope.key")  # no crash, no change

    def test_reset_all(self):
        m = self._make()
        m.set("app.debug", True, validate=False)
        m.config["custom"] = "x"
        m.reset()
        self.assertFalse(m.config["app"]["debug"])
        self.assertNotIn("custom", m.config)

    def test_reset_all_persists(self):
        m = self._make()
        m.set("app.debug", True, validate=False)
        m.reset()
        m2 = self._make()
        self.assertFalse(m2.config["app"]["debug"])

    def test_get_history(self):
        m = self._make()
        m.set("app.debug", True, validate=False)
        m.set("app.debug", False, validate=False)
        h = m.get_history(1)
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["new_value"], False)

    def test_get_history_default_50(self):
        m = self._make()
        for i in range(60):
            m.set("app.debug", bool(i % 2), validate=False)
        h = m.get_history()
        self.assertEqual(len(h), 50)


class ExportImportTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._cfg = Path(self._d) / "orbit_config.json"
        self.addCleanup(mock.patch.stopall)

    def _make(self):
        with mock.patch("orbit.orbit.core.config_manager.app_root",
                        return_value=Path(self._d)), \
                mock.patch("orbit.orbit.core.version.VERSION", "3.7.0", create=True):
            return cm.ConfigManager(config_file=str(self._cfg))

    def test_export_config(self):
        m = self._make()
        out = Path(self._d) / "exported.json"
        m.export_config(str(out))
        self.assertTrue(out.exists())
        data = json.loads(out.read_text("utf-8"))
        self.assertEqual(data["app"]["name"], "ORBIT")

    def test_export_config_failure(self):
        m = self._make()
        with mock.patch("builtins.open", side_effect=OSError("boom")), \
                mock.patch.object(cm, "logger") as lg:
            m.export_config("/tmp/x.json")
        lg.error.assert_called_once()

    def test_import_config(self):
        m = self._make()
        imp = Path(self._d) / "imported.json"
        imp.write_text(json.dumps({"app": {"debug": True}}), encoding="utf-8")
        m.import_config(str(imp))
        self.assertTrue(m.config["app"]["debug"])

    def test_import_config_failure(self):
        m = self._make()
        with mock.patch.object(cm, "logger") as lg:
            m.import_config("/tmp/nonexistent.json")
        lg.error.assert_called_once()

    def test_import_config_merges(self):
        m = self._make()
        m.set("app.debug", False, validate=False)
        imp = Path(self._d) / "imported.json"
        imp.write_text(json.dumps({"llm": {"max_retries": 99}}), encoding="utf-8")
        m.import_config(str(imp))
        self.assertEqual(m.config["llm"]["max_retries"], 99)
        self.assertFalse(m.config["app"]["debug"])


class ModuleLevelTests(unittest.TestCase):
    def test_get_config_manager_singleton(self):
        cm._config_manager = None
        a = cm.get_config_manager()
        b = cm.get_config_manager()
        self.assertIs(a, b)
        cm._config_manager = None

    def test_module_get(self):
        cm._config_manager = None
        with mock.patch("orbit.orbit.core.config_manager.ConfigManager") as C:
            m = mock.MagicMock()
            m.get.return_value = "val"
            C.return_value = m
            cm._config_manager = None
            r = cm.get("key", "default")
        self.assertEqual(r, "val")
        m.get.assert_called_once_with("key", "default")
        cm._config_manager = None

    def test_module_set(self):
        cm._config_manager = None
        with mock.patch("orbit.orbit.core.config_manager.ConfigManager") as C:
            m = mock.MagicMock()
            m.set.return_value = True
            C.return_value = m
            cm._config_manager = None
            r = cm.set("key", "val", validate=False)
        self.assertTrue(r)
        m.set.assert_called_once_with("key", "val", False)
        cm._config_manager = None

    def test_module_watch(self):
        cm._config_manager = None
        with mock.patch("orbit.orbit.core.config_manager.ConfigManager") as C:
            m = mock.MagicMock()
            C.return_value = m
            cm._config_manager = None
            cb = lambda x: x
            cm.watch("key", cb)
        m.watch.assert_called_once_with("key", cb)
        cm._config_manager = None

    def test_module_get_all(self):
        cm._config_manager = None
        with mock.patch("orbit.orbit.core.config_manager.ConfigManager") as C:
            m = mock.MagicMock()
            m.get_all.return_value = {"a": 1}
            C.return_value = m
            cm._config_manager = None
            r = cm.get_all()
        self.assertEqual(r, {"a": 1})
        cm._config_manager = None


if __name__ == "__main__":
    unittest.main()
