"""Deep tests for orbit/main.py — desktop entry point (Loop 10/2).

29 statements. Covers:
  * ``_load_prefs``: missing file / valid JSON / corrupt JSON / unreadable
    path (directory) all resolve to a sane dict without raising.
  * ``main()``: each preference key maps to its environment variable
    (ORBIT_OFFLINE / TTS_ENGINE / KOKORO_VOICE), absent keys set nothing,
    and the desktop launcher is invoked exactly once.
  * module ``__main__`` guard via runpy.
"""

import json
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import orbit.main as main_mod


class _PlatformSaver(unittest.TestCase):
    """Importing orbit.main calls set_platform(PLATFORM_DESKTOP); keep the
    process-global platform value as we found it."""

    def setUp(self):
        from orbit.orbit.core import pform

        self._pform = pform
        self._saved = pform.get_platform() if hasattr(pform, "get_platform") \
            else None

    def tearDown(self):
        if self._saved is not None and hasattr(self._pform, "set_platform"):
            self._pform.set_platform(self._saved)


class LoadPrefsTests(_PlatformSaver):
    def _patch_pref(self, target):
        return mock.patch.object(main_mod, "PREF_FILE", Path(target))

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope.json"
            with self._patch_pref(missing):
                self.assertEqual(main_mod._load_prefs(), {})

    def test_valid_json_is_parsed(self):
        with tempfile.TemporaryDirectory() as td:
            pf = Path(td) / "orbit_prefs.json"
            pf.write_text(json.dumps({"offline_mode": True,
                                      "tts_engine": "kokoro"}),
                          encoding="utf-8")
            with self._patch_pref(pf):
                prefs = main_mod._load_prefs()
            self.assertTrue(prefs["offline_mode"])
            self.assertEqual(prefs["tts_engine"], "kokoro")

    def test_corrupt_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            pf = Path(td) / "orbit_prefs.json"
            pf.write_text("{not json", encoding="utf-8")
            with self._patch_pref(pf):
                self.assertEqual(main_mod._load_prefs(), {})

    def test_unreadable_path_returns_empty(self):
        # a directory exists but read_text() raises -> except branch
        with tempfile.TemporaryDirectory() as td:
            with self._patch_pref(td):
                self.assertEqual(main_mod._load_prefs(), {})

    def test_pref_file_location(self):
        # PREF_FILE lives in the orbit data dir
        self.assertEqual(main_mod.PREF_FILE.name, "orbit_prefs.json")
        self.assertTrue(str(main_mod.PREF_FILE.parent).endswith("orbit_data"))


class MainEntryTests(_PlatformSaver):
    ENV_KEYS = ("ORBIT_OFFLINE", "TTS_ENGINE", "KOKORO_VOICE")

    def _run(self, prefs):
        """Run main() with patched prefs file + launcher; return launcher."""
        with mock.patch.object(main_mod, "_load_prefs",
                               return_value=prefs), \
                mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch("orbit.launch_desktop.main") as launcher:
            for key in self.ENV_KEYS:
                os.environ.pop(key, None)
            main_mod.main()
            return launcher, dict(os.environ)

    def test_launcher_called_once(self):
        launcher, env = self._run({})
        launcher.assert_called_once_with()

    def test_offline_mode_env(self):
        _, env = self._run({"offline_mode": True})
        self.assertEqual(env.get("ORBIT_OFFLINE"), "true")

    def test_tts_engine_env(self):
        _, env = self._run({"tts_engine": "piper"})
        self.assertEqual(env.get("TTS_ENGINE"), "piper")

    def test_kokoro_voice_env(self):
        _, env = self._run({"kokoro_voice": "af_heart"})
        self.assertEqual(env.get("KOKORO_VOICE"), "af_heart")

    def test_no_prefs_sets_nothing(self):
        _, env = self._run({})
        for key in self.ENV_KEYS:
            self.assertNotIn(key, env)

    def test_falsey_offline_mode_not_set(self):
        _, env = self._run({"offline_mode": False})
        self.assertNotIn("ORBIT_OFFLINE", env)

    def test_all_prefs_together(self):
        _, env = self._run({"offline_mode": True, "tts_engine": "kokoro",
                            "kokoro_voice": "af_bella"})
        self.assertEqual(env["ORBIT_OFFLINE"], "true")
        self.assertEqual(env["TTS_ENGINE"], "kokoro")
        self.assertEqual(env["KOKORO_VOICE"], "af_bella")


class ScriptModeTests(_PlatformSaver):
    def test_run_as_main_invokes_launcher(self):
        # runpy re-executes the module source in a fresh namespace, so the
        # launcher must be patched on orbit.launch_desktop (imported inside
        # main()) and prefs resolve to the (absent) real file
        saved_path = list(sys.path)
        try:
            with mock.patch("orbit.launch_desktop.main") as launcher, \
                    mock.patch.dict(os.environ, {}, clear=False):
                for key in ("ORBIT_OFFLINE", "TTS_ENGINE", "KOKORO_VOICE"):
                    os.environ.pop(key, None)
                runpy.run_module("orbit.main", run_name="__main__")
                launcher.assert_called_once_with()
        finally:
            sys.path[:] = saved_path


if __name__ == "__main__":
    unittest.main()
