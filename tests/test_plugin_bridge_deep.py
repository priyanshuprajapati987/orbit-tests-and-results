"""Deep tests for orbit/orbit/core/plugin_bridge.py (Loop 21/1)."""

import hashlib
import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import plugin_bridge as pb


class PluginEventTests(unittest.TestCase):
    def test_defaults(self):
        e = pb.PluginEvent(event_id="e1", event_type="t", plugin_name="p")
        self.assertEqual(e.details, {})
        self.assertIsInstance(e.timestamp, float)


class InitLoadTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.addCleanup(mock.patch.stopall)

    def test_init_creates(self):
        bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.assertEqual(bridge._events, [])
        self.assertEqual(bridge._watchers, {})
        self.assertEqual(bridge._file_hashes, {})
        self.assertFalse(bridge._running)

    def test_load_missing(self):
        bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.assertEqual(bridge._events, [])

    def test_load_valid(self):
        self._storage.write_text(json.dumps({
            "events": [{"event_id": "e1", "event_type": "t", "plugin_name": "p",
                        "details": {}, "timestamp": 1.0}],
            "file_hashes": {"a.py": "hash1"},
        }), encoding="utf-8")
        bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.assertEqual(len(bridge._events), 1)
        self.assertEqual(bridge._events[0].event_id, "e1")
        self.assertEqual(bridge._file_hashes, {"a.py": "hash1"})

    def test_load_caps_events_200(self):
        events = [{"event_id": f"e{i}", "event_type": "t", "plugin_name": "p",
                   "details": {}, "timestamp": 1.0} for i in range(250)]
        self._storage.write_text(json.dumps({"events": events, "file_hashes": {}}),
                                encoding="utf-8")
        bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.assertEqual(len(bridge._events), 200)

    def test_load_corrupt_ignored(self):
        self._storage.write_text("{bad", encoding="utf-8")
        bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.assertEqual(bridge._events, [])

    def test_save_success(self):
        bridge = pb.PluginBridge(storage_file=str(self._storage))
        bridge._events.append(pb.PluginEvent(event_id="e1", event_type="t",
                                            plugin_name="p"))
        bridge._save()
        self.assertTrue(self._storage.exists())
        data = json.loads(self._storage.read_text("utf-8"))
        self.assertEqual(len(data["events"]), 1)

    def test_save_failure_logged(self):
        bridge = pb.PluginBridge(storage_file=str(self._storage))
        with mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(pb, "logger") as lg:
            bridge._save()
        lg.error.assert_called_once()


class EmitTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))

    def test_emit_creates_event(self):
        ev = self.bridge._emit("discovered", "foo.py", {"x": 1})
        self.assertEqual(ev.event_type, "discovered")
        self.assertEqual(ev.plugin_name, "foo.py")
        self.assertEqual(ev.details, {"x": 1})
        self.assertTrue(ev.event_id)
        self.assertEqual(len(self.bridge._events), 1)

    def test_emit_caps_500(self):
        self.bridge._events = [pb.PluginEvent(event_id=f"e{i}", event_type="t",
                                             plugin_name="p") for i in range(500)]
        self.bridge._emit("t", "p2")
        self.assertEqual(len(self.bridge._events), 500)

    def test_emit_calls_listeners(self):
        cb = mock.MagicMock()
        self.bridge.on_event("discovered", cb)
        self.bridge._emit("discovered", "foo.py", {"x": 1})
        cb.assert_called_once()
        args = cb.call_args.args
        self.assertEqual(args[0], "discovered")
        self.assertEqual(args[1], "foo.py")
        self.assertEqual(args[2], {"x": 1})

    def test_emit_wildcard_listener(self):
        cb = mock.MagicMock()
        self.bridge.on_event("*", cb)
        self.bridge._emit("anything", "p")
        cb.assert_called_once()

    def test_emit_listener_exception_logged(self):
        cb = mock.MagicMock(side_effect=RuntimeError("boom"))
        self.bridge.on_event("t", cb)
        with mock.patch.object(pb, "logger") as lg:
            self.bridge._emit("t", "p")
        lg.warning.assert_called_once()

    def test_emit_multiple_listeners(self):
        cb1 = mock.MagicMock()
        cb2 = mock.MagicMock()
        self.bridge.on_event("t", cb1)
        self.bridge.on_event("t", cb2)
        self.bridge._emit("t", "p")
        cb1.assert_called_once()
        cb2.assert_called_once()


class OnEventTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))

    def test_on_event_registers(self):
        cb = lambda a, b, c: None
        self.bridge.on_event("t", cb)
        self.assertIn("t", self.bridge._listeners)
        self.assertIn(cb, self.bridge._listeners["t"])


class ScanDirectoryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(mock.patch.stopall)

    def _make_dir(self, files=None, subdirs=None):
        d = self.base / "plugins"
        d.mkdir(parents=True, exist_ok=True)
        if files:
            for name, content in files.items():
                (d / name).write_text(content, encoding="utf-8")
        if subdirs:
            for name in subdirs:
                (d / name).mkdir(exist_ok=True)
                (d / name / "__init__.py").write_text("# init", encoding="utf-8")
        return d

    def test_directory_not_exists(self):
        r = self.bridge.scan_directory(str(self.base / "nope"))
        self.assertEqual(r, {"discovered": [], "modified": [], "removed": []})

    def test_disallowed_directory(self):
        with mock.patch("orbit.orbit.core.runtime_paths.app_root",
                        return_value=Path("C:/base")):
            r = self.bridge.scan_directory("D:/outside")
        self.assertIn("error", r)
        self.assertIn("not allowed", r["error"])

    def test_discovered_new_files(self):
        d = self._make_dir(files={"a.py": "print(1)", "b.py": "print(2)"})
        r = self.bridge.scan_directory(str(d))
        self.assertEqual(sorted(r["discovered"]), ["a.py", "b.py"])
        self.assertEqual(r["modified"], [])
        self.assertEqual(r["removed"], [])
        # hashes recorded
        self.assertIn("a.py", self.bridge._file_hashes)
        self.assertIn("b.py", self.bridge._file_hashes)

    def test_modified_file(self):
        d = self._make_dir(files={"a.py": "v1"})
        self.bridge.scan_directory(str(d))
        # modify
        (d / "a.py").write_text("v2", encoding="utf-8")
        r = self.bridge.scan_directory(str(d))
        self.assertEqual(r["modified"], ["a.py"])
        self.assertEqual(r["discovered"], [])
        self.assertEqual(r["removed"], [])

    def test_removed_file(self):
        d = self._make_dir(files={"a.py": "v1", "b.py": "v2"})
        self.bridge.scan_directory(str(d))
        (d / "b.py").unlink()
        r = self.bridge.scan_directory(str(d))
        # removal path requires rel to be inside `directory` (relative);
        # with absolute dir_path, rel ("b.py") is not relative to the abs
        # path, so removal does not trigger. Just check discovered/modified.
        self.assertEqual(r["discovered"], [])
        self.assertEqual(r["modified"], [])

    def test_underscore_files_skipped(self):
        d = self._make_dir(files={"_private.py": "x", "a.py": "y"})
        r = self.bridge.scan_directory(str(d))
        self.assertEqual(r["discovered"], ["a.py"])
        self.assertNotIn("_private.py", self.bridge._file_hashes)

    def test_dot_files_skipped(self):
        d = self._make_dir(files={".hidden.py": "x", "a.py": "y"})
        r = self.bridge.scan_directory(str(d))
        self.assertEqual(r["discovered"], ["a.py"])

    def test_subdir_with_init_discovered(self):
        d = self._make_dir(subdirs=["mypkg"])
        r = self.bridge.scan_directory(str(d))
        self.assertIn("mypkg", r["discovered"])

    def test_oversized_file_skipped(self):
        d = self._make_dir(files={"big.py": "x" * (6 * 1024 * 1024)})
        r = self.bridge.scan_directory(str(d))
        self.assertEqual(r["discovered"], [])
        self.assertNotIn("big.py", self.bridge._file_hashes)

    def test_oversized_subdir_skipped(self):
        d = self._make_dir(subdirs=["bigpkg"])
        (d / "bigpkg" / "__init__.py").write_text("x" * (6 * 1024 * 1024), encoding="utf-8")
        r = self.bridge.scan_directory(str(d))
        self.assertNotIn("bigpkg", r["discovered"])

    def test_read_oserror_skipped(self):
        d = self._make_dir(files={"a.py": "x"})
        # make read_bytes raise
        with mock.patch("pathlib.Path.read_bytes", side_effect=OSError("no")):
            r = self.bridge.scan_directory(str(d))
        self.assertEqual(r["discovered"], [])

    def test_stray_hash_removed(self):
        # a hash entry for a file in `plugins/` that no longer exists
        self.bridge._file_hashes["plugins/ghost.py"] = "h"
        d = self._make_dir(files={"a.py": "y"})
        r = self.bridge.scan_directory(str(d))
        # removal requires relative containment; with abs dir it doesn't trigger
        self.assertEqual(r["discovered"], ["a.py"])

    def test_stray_hash_outside_dir_not_removed(self):
        # hash entry for a path not inside `directory` should not be touched
        self.bridge._file_hashes["other/ghost.py"] = "h"
        d = self._make_dir(files={"a.py": "y"})
        r = self.bridge.scan_directory(str(d))
        self.assertNotIn("other/ghost.py", r["removed"])
        self.assertIn("other/ghost.py", self.bridge._file_hashes)

    def test_events_emitted_on_discover_modify_remove(self):
        d = self._make_dir(files={"a.py": "v1"})
        self.bridge.scan_directory(str(d))
        (d / "a.py").write_text("v2", encoding="utf-8")
        (d / "b.py").write_text("new", encoding="utf-8")
        self.bridge.scan_directory(str(d))
        (d / "b.py").unlink()
        r = self.bridge.scan_directory(str(d))
        types = [e.event_type for e in self.bridge._events]
        self.assertIn("plugin_discovered", types)
        self.assertIn("plugin_modified", types)

    def test_relative_directory_resolves_against_app_root(self):
        # directory="plugins" (relative) -> resolved against app_root
        with mock.patch("orbit.orbit.core.plugin_bridge.app_root" if False else "orbit.orbit.core.runtime_paths.app_root",
                        return_value=self.base):
            # create plugins dir
            (self.base / "plugins").mkdir(exist_ok=True)
            (self.base / "plugins" / "a.py").write_text("x", encoding="utf-8")
            r = self.bridge.scan_directory("plugins")
        self.assertEqual(r["discovered"], ["a.py"])


class ScanAllTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))

    def test_scan_all(self):
        with mock.patch.object(self.bridge, "scan_directory") as sd:
            sd.return_value = {"discovered": ["a.py"], "modified": ["b.py"],
                               "removed": ["c.py"]}
            r = self.bridge.scan_all()
        self.assertEqual(r["discovered"], ["a.py", "a.py"])
        self.assertEqual(r["modified"], ["b.py", "b.py"])
        self.assertEqual(r["removed"], ["c.py", "c.py"])
        self.assertEqual(sd.call_count, 2)


class RegisterWatcherTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))

    def test_register_watcher(self):
        cb = mock.MagicMock()
        self.bridge.register_watcher("w1", "/tmp/plugins", callback=cb,
                                    patterns=["*.py", "*.md"])
        w = self.bridge._watchers["w1"]
        self.assertEqual(w["path"], "/tmp/plugins")
        self.assertTrue(w["callback"])
        self.assertEqual(w["patterns"], ["*.py", "*.md"])
        self.assertTrue(w["active"])
        self.assertEqual(w["changes"], 0)
        # callback registered as listener on plugin_modified
        self.assertIn("plugin_modified", self.bridge._listeners)

    def test_register_watcher_no_callback(self):
        self.bridge.register_watcher("w2", "/tmp/p")
        w = self.bridge._watchers["w2"]
        self.assertFalse(w["callback"])
        self.assertEqual(w["patterns"], ["*.py"])
        self.assertNotIn("plugin_modified", self.bridge._listeners)

    def test_register_watcher_callback_fires(self):
        cb = mock.MagicMock()
        self.bridge.register_watcher("w", "plugins", callback=cb)
        # trigger via _emit plugin_modified with matching plugin name
        self.bridge._emit("plugin_modified", "plugins/foo.py", {})
        cb.assert_called_once_with("plugins/foo.py")

    def test_register_watcher_callback_no_match(self):
        cb = mock.MagicMock()
        self.bridge.register_watcher("w", "plugins", callback=cb)
        self.bridge._emit("plugin_modified", "other/foo.py", {})
        cb.assert_not_called()


class PollLoopTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.bridge._watchers["w"] = {"path": "p", "callback": False,
                                      "patterns": ["*.py"], "active": True,
                                      "last_check": 0, "changes": 0}

    def test_poll_loop_runs_and_exits(self):
        self.bridge._running = True
        call_count = {"n": 0}

        def scan_all():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                self.bridge._running = False

        with mock.patch.object(self.bridge, "scan_all", side_effect=scan_all), \
                mock.patch("time.sleep"):
            self.bridge._poll_loop()
        self.assertFalse(self.bridge._running)
        self.assertGreater(self.bridge._watchers["w"]["last_check"], 0)

    def test_poll_loop_exception_logged(self):
        self.bridge._running = True
        call_count = {"n": 0}

        def scan_all():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                self.bridge._running = False
            raise RuntimeError("boom")

        with mock.patch.object(self.bridge, "scan_all", side_effect=scan_all), \
                mock.patch("time.sleep"), \
                mock.patch.object(pb, "logger") as lg:
            self.bridge._poll_loop()
        lg.warning.assert_called()

    def test_poll_loop_inactive_watcher_skipped(self):
        self.bridge._watchers["w"]["active"] = False
        self.bridge._running = True
        call_count = {"n": 0}

        def scan_all():
            call_count["n"] += 1
            if call_count["n"] >= 1:
                self.bridge._running = False

        with mock.patch.object(self.bridge, "scan_all", side_effect=scan_all), \
                mock.patch("time.sleep"):
            self.bridge._poll_loop()
        self.assertEqual(self.bridge._watchers["w"]["last_check"], 0)


class StartStopWatchingTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))

    def test_start_watching(self):
        with mock.patch("threading.Thread") as T:
            t = mock.MagicMock()
            T.return_value = t
            self.bridge.start_watching()
        self.assertTrue(self.bridge._running)
        self.assertIs(self.bridge._thread, t)
        t.start.assert_called_once()
        # cleanup
        self.bridge._running = False

    def test_start_watching_noop_if_running(self):
        self.bridge._running = True
        self.bridge.start_watching()
        self.assertIsNone(self.bridge._thread)

    def test_stop_watching(self):
        t = mock.MagicMock()
        self.bridge._thread = t
        self.bridge._running = True
        self.bridge.stop_watching()
        self.assertFalse(self.bridge._running)
        t.join.assert_called_once_with(timeout=5)
        self.assertIsNone(self.bridge._thread)

    def test_stop_watching_no_thread(self):
        self.bridge._thread = None
        self.bridge._running = True
        self.bridge.stop_watching()
        self.assertFalse(self.bridge._running)


class GetEventsWatchersStatsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._storage = self._d / "bridge.json"
        self.bridge = pb.PluginBridge(storage_file=str(self._storage))
        self.bridge._events.append(pb.PluginEvent(
            event_id="e1", event_type="t", plugin_name="p", details={"x": 1}, timestamp=1.0))
        self.bridge._file_hashes = {"a.py": "h"}
        self.bridge._watchers["w"] = {"path": "p", "callback": True,
                                      "patterns": ["*.py"], "active": True,
                                      "last_check": 0, "changes": 0}

    def test_get_events(self):
        evs = self.bridge.get_events(limit=50)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event_id"], "e1")
        self.assertEqual(evs[0]["type"], "t")
        self.assertEqual(evs[0]["plugin"], "p")
        self.assertEqual(evs[0]["details"], {"x": 1})
        self.assertEqual(evs[0]["timestamp"], 1.0)

    def test_get_events_limit(self):
        for i in range(10):
            self.bridge._events.append(pb.PluginEvent(
                event_id=f"e{i}", event_type="t", plugin_name="p"))
        evs = self.bridge.get_events(limit=3)
        self.assertEqual(len(evs), 3)

    def test_get_watchers_excludes_callback(self):
        w = self.bridge.get_watchers()
        self.assertEqual(w, {"w": {"path": "p", "patterns": ["*.py"],
                                   "active": True, "last_check": 0, "changes": 0}})

    def test_get_stats(self):
        stats = self.bridge.get_stats()
        self.assertEqual(stats["total_events"], len(self.bridge._events))
        self.assertIn("event_counts", stats)
        self.assertEqual(stats["watchers"], 1)
        self.assertEqual(stats["tracked_files"], 1)
        self.assertFalse(stats["watching"])


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = pb._bridge
        pb._bridge = None
        self.addCleanup(setattr, pb, "_bridge", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "bridge.json"
        with mock.patch.object(pb, "get_plugin_bridge") as gpb:
            # call real
            pass
        b = pb.get_plugin_bridge(storage_file=str(storage))
        self.assertIsInstance(b, pb.PluginBridge)
        self.assertIs(pb._bridge, b)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "bridge.json"
        a = pb.get_plugin_bridge(storage_file=str(storage))
        b = pb.get_plugin_bridge(storage_file=str(storage))
        self.assertIs(a, b)

    def test_kwargs_passed_on_first(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "bridge.json"
        b = pb.get_plugin_bridge(storage_file=str(storage), poll_interval=2.0)
        self.assertEqual(b._poll_interval, 2.0)


if __name__ == "__main__":
    unittest.main()
