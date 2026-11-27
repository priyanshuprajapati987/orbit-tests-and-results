"""Deep tests for orbit/orbit/core/model_monitor.py (Loop 18/5)."""

import json
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from orbit.orbit.core import model_monitor as mm


class InitLoadTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        # reset singleton
        mm.ModelMonitor._instance = None

    def test_init_loads_existing(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        f = d / "releases.json"
        f.write_text(json.dumps({
            "last_scan": "2026-01-01T00:00:00",
            "releases": [{"name": "m1", "provider": "hf", "release_date": "",
                          "source": "hf", "url": "u", "description": "d",
                          "detected_at": "2026-01-01T00:00:00",
                          "benchmarked": False, "recommended": False, "reason": ""}],
        }), encoding="utf-8")
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            m = mm.ModelMonitor()
        self.assertEqual(m._last_scan, "2026-01-01T00:00:00")
        self.assertEqual(len(m._releases), 1)
        self.assertEqual(m._releases[0].name, "m1")
        self.assertIn("m1", m._known_models)
        self.assertTrue(m._initialized)

    def test_init_corrupt_load_ignored(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        f = d / "releases.json"
        f.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            m = mm.ModelMonitor()
        self.assertEqual(m._releases, [])
        self.assertIsNone(m._last_scan)

    def test_init_missing_file(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            m = mm.ModelMonitor()
        self.assertEqual(m._releases, [])
        self.assertIsNone(m._last_scan)

    def test_init_singleton_reuse(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            m1 = mm.ModelMonitor()
            m2 = mm.ModelMonitor()
        self.assertIs(m1, m2)

    def test_save_success(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            m = mm.ModelMonitor()
        m._releases.append(mm.ModelRelease(name="m2", provider="p", source="s"))
        m._save()
        f = d / "releases.json"
        self.assertTrue(f.exists())
        data = json.loads(f.read_text("utf-8"))
        self.assertEqual(len(data["releases"]), 1)

    def test_save_failure_logged(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            m = mm.ModelMonitor()
        with mock.patch("orbit.orbit.core.model_monitor.atomic_write_text",
                        side_effect=OSError("boom")), \
                mock.patch.object(mm, "logger") as lg:
            m._save()
        lg.error.assert_called_once()


class ScanHuggingfaceTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            self.m = mm.ModelMonitor()

    def test_success(self):
        resp = mock.MagicMock()
        resp.ok = True
        resp.json.return_value = [
            {"id": "org/model1", "lastModified": "2026-01-01",
             "tags": ["text-generation", "agent"]},
            {"id": "", "tags": []},  # skipped (no name)
        ]
        with mock.patch("requests.get", return_value=resp):
            found = self.m.scan_huggingface()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, "org/model1")
        self.assertEqual(found[0].provider, "huggingface")
        self.assertEqual(found[0].source, "huggingface")

    def test_not_ok(self):
        resp = mock.MagicMock(ok=False)
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(self.m.scan_huggingface(), [])

    def test_exception(self):
        with mock.patch("requests.get", side_effect=Exception("net")):
            found = self.m.scan_huggingface()
        self.assertEqual(found, [])


class ScanOpenrouterTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            self.m = mm.ModelMonitor()

    def test_success(self):
        resp = mock.MagicMock()
        resp.ok = True
        resp.json.return_value = {"data": [
            {"id": "openai/gpt-4", "name": "GPT-4"},
            {"id": "", "name": ""},  # skipped
        ]}
        with mock.patch("requests.get", return_value=resp):
            found = self.m.scan_openrouter()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, "openai/gpt-4")
        self.assertEqual(found[0].provider, "openrouter")
        self.assertEqual(found[0].description, "GPT-4")

    def test_not_ok(self):
        resp = mock.MagicMock(ok=False)
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(self.m.scan_openrouter(), [])

    def test_exception(self):
        with mock.patch("requests.get", side_effect=Exception("net")):
            self.assertEqual(self.m.scan_openrouter(), [])


class ScanOllamaTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            self.m = mm.ModelMonitor()

    def test_success(self):
        resp = mock.MagicMock()
        resp.ok = True
        resp.json.return_value = {"models": [
            {"name": "llama3:8b"}, {"name": ""}]}
        with mock.patch("orbit.orbit.config.OLLAMA_URL", "http://localhost:11434"), \
                mock.patch("requests.get", return_value=resp):
            found = self.m.scan_ollama()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, "llama3:8b")
        self.assertEqual(found[0].provider, "ollama")
        self.assertEqual(found[0].source, "ollama_local")

    def test_not_ok(self):
        resp = mock.MagicMock(ok=False)
        with mock.patch("orbit.orbit.config.OLLAMA_URL", "http://localhost:11434"), \
                mock.patch("requests.get", return_value=resp):
            self.assertEqual(self.m.scan_ollama(), [])

    def test_exception(self):
        with mock.patch("orbit.orbit.config.OLLAMA_URL", "http://localhost:11434"), \
                mock.patch("requests.get", side_effect=Exception("net")):
            found = self.m.scan_ollama()
        self.assertEqual(found, [])


class RunFullScanTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            self.m = mm.ModelMonitor()

    def test_run_full_scan_new_models(self):
        r1 = mm.ModelRelease(name="m1", provider="hf", source="hf")
        r2 = mm.ModelRelease(name="m2", provider="or", source="or")
        with mock.patch.object(self.m, "scan_huggingface", return_value=[r1]), \
                mock.patch.object(self.m, "scan_openrouter", return_value=[r2]), \
                mock.patch.object(self.m, "scan_ollama", return_value=[]):
            result = self.m.run_full_scan()
        self.assertEqual(result["new_models"], 2)
        self.assertEqual(result["total_known"], 2)
        self.assertIn("elapsed_ms", result)
        self.assertIn("last_scan", result)
        self.assertEqual(len(result["new_releases"]), 2)
        self.assertEqual(result["new_releases"][0]["name"], "m1")
        # known_models updated
        self.assertIn("m1", self.m._known_models)
        self.assertIn("m2", self.m._known_models)

    def test_run_full_scan_duplicate_ignored(self):
        # pre-populate known_models
        self.m._known_models["m1"] = "2026-01-01"
        r1 = mm.ModelRelease(name="m1", provider="hf", source="hf")
        with mock.patch.object(self.m, "scan_huggingface", return_value=[r1]), \
                mock.patch.object(self.m, "scan_openrouter", return_value=[]), \
                mock.patch.object(self.m, "scan_ollama", return_value=[]):
            result = self.m.run_full_scan()
        self.assertEqual(result["new_models"], 0)
        self.assertEqual(len(self.m._releases), 0)

    def test_run_full_scan_cap_releases(self):
        # pre-fill _releases with 501 items
        for i in range(501):
            self.m._releases.append(mm.ModelRelease(name=f"m{i}", provider="p", source="s"))
        # known_models too
        for i in range(5001):
            self.m._known_models[f"k{i}"] = "t"
        r1 = mm.ModelRelease(name="new", provider="hf", source="hf")
        with mock.patch.object(self.m, "scan_huggingface", return_value=[r1]), \
                mock.patch.object(self.m, "scan_openrouter", return_value=[]), \
                mock.patch.object(self.m, "scan_ollama", return_value=[]):
            self.m.run_full_scan()
        self.assertLessEqual(len(self.m._releases), 500)
        self.assertLessEqual(len(self.m._known_models), 5000)

    def test_run_full_scan_new_releases_capped_20(self):
        releases = [mm.ModelRelease(name=f"m{i}", provider="hf", source="hf")
                    for i in range(25)]
        with mock.patch.object(self.m, "scan_huggingface", return_value=releases), \
                mock.patch.object(self.m, "scan_openrouter", return_value=[]), \
                mock.patch.object(self.m, "scan_ollama", return_value=[]):
            result = self.m.run_full_scan()
        self.assertEqual(result["new_models"], 25)
        self.assertEqual(len(result["new_releases"]), 20)

    def test_run_full_scan_saves(self):
        with mock.patch.object(self.m, "scan_huggingface", return_value=[]), \
                mock.patch.object(self.m, "scan_openrouter", return_value=[]), \
                mock.patch.object(self.m, "scan_ollama", return_value=[]), \
                mock.patch.object(self.m, "_save") as sv:
            self.m.run_full_scan()
        sv.assert_called_once()


class NeedsScanTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            self.m = mm.ModelMonitor()

    def test_no_last_scan_true(self):
        self.m._last_scan = None
        self.assertTrue(self.m.needs_scan())

    def test_recent_scan_false(self):
        self.m._last_scan = datetime.now().isoformat()
        self.assertFalse(self.m.needs_scan())

    def test_old_scan_true(self):
        from datetime import timedelta
        old = (datetime.now() - timedelta(hours=25)).isoformat()
        self.m._last_scan = old
        self.assertTrue(self.m.needs_scan())

    def test_invalid_last_scan_true(self):
        self.m._last_scan = "not-a-date"
        self.assertTrue(self.m.needs_scan())


class GetReleasesTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            self.m = mm.ModelMonitor()
        for i in range(3):
            self.m._releases.append(mm.ModelRelease(
                name=f"m{i}", provider="p", source="s", url=f"u{i}",
                detected_at="t", benchmarked=(i == 1),
                recommended=(i == 2), reason="r"))

    def test_default_limit(self):
        r = self.m.get_releases()
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0]["name"], "m0")
        self.assertTrue(r[1]["benchmarked"])
        self.assertTrue(r[2]["recommended"])

    def test_limit(self):
        r = self.m.get_releases(limit=2)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["name"], "m1")

    def test_limit_invalid_string(self):
        r = self.m.get_releases(limit="abc")
        self.assertEqual(len(r), 3)

    def test_limit_none(self):
        r = self.m.get_releases(limit=None)
        self.assertEqual(len(r), 3)

    def test_limit_clamped_high(self):
        r = self.m.get_releases(limit=1000)
        self.assertEqual(len(r), 3)

    def test_limit_clamped_low(self):
        r = self.m.get_releases(limit=0)
        self.assertEqual(len(r), 1)


class GetStatusTests(unittest.TestCase):
    def setUp(self):
        mm.ModelMonitor._instance = None
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            self.m = mm.ModelMonitor()
        self.m._last_scan = None
        self.m._scan_interval_hours = 12

    def test_status(self):
        s = self.m.get_status()
        self.assertEqual(s["total_known_models"], 0)
        self.assertEqual(s["total_releases"], 0)
        self.assertIsNone(s["last_scan"])
        self.assertTrue(s["needs_scan"])
        self.assertEqual(s["scan_interval_hours"], 12)


class GetModelMonitorTests(unittest.TestCase):
    def test_returns_instance(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.model_monitor._MONITOR_DIR", d):
            m = mm.get_model_monitor()
        self.assertIsInstance(m, mm.ModelMonitor)


if __name__ == "__main__":
    unittest.main()
