"""Unit tests for orbit/orbit/core/continuity.py."""

import base64
import hashlib
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.continuity as cont
from orbit.core.continuity import _key, _gather, export_package, import_package, _HAVE_CRYPTO


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography not installed")
class TestKey(unittest.TestCase):
    def test_key_matches_sha256_b64(self):
        expected = base64.urlsafe_b64encode(hashlib.sha256("pw".encode("utf-8")).digest())
        self.assertEqual(_key("pw"), expected)

    def test_key_deterministic(self):
        self.assertEqual(_key("abc"), _key("abc"))

    def test_key_differs(self):
        self.assertNotEqual(_key("a"), _key("b"))


class TestGather(unittest.TestCase):
    def test_gather_sources_ok(self):
        # personalization module does not exist -> skipped gracefully
        with patch("orbit.core.smart_memory.get_smart_memory") as gsm, \
             patch("orbit.core.companion_memory.get_companion_memory") as gcm:
            gsm.return_value._data = {"facts": [1]}
            gcm.return_value.timeline.return_value = [{"text": "hello"}]
            data = _gather()
        self.assertNotIn("personalization", data)
        self.assertEqual(data["smart_memory"], {"facts": [1]})
        self.assertEqual(data["companion_memory"], [{"text": "hello"}])

    def test_gather_smart_memory_fails(self):
        with patch("orbit.core.smart_memory.get_smart_memory", side_effect=RuntimeError("y")), \
             patch("orbit.core.companion_memory.get_companion_memory") as gcm:
            gcm.return_value.timeline.return_value = []
            data = _gather()
        self.assertNotIn("smart_memory", data)
        self.assertIn("companion_memory", data)

    def test_gather_companion_fails(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gsm, \
             patch("orbit.core.companion_memory.get_companion_memory", side_effect=RuntimeError("z")):
            gsm.return_value._data = {}
            data = _gather()
        self.assertNotIn("companion_memory", data)
        self.assertIn("smart_memory", data)

    def test_gather_all_fail_returns_empty(self):
        with patch("orbit.core.smart_memory.get_smart_memory", side_effect=RuntimeError("b")), \
             patch("orbit.core.companion_memory.get_companion_memory", side_effect=RuntimeError("c")):
            data = _gather()
        self.assertEqual(data, {})


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography not installed")
class TestExportPackage(unittest.TestCase):
    def test_export_empty_passphrase(self):
        self.assertIsNone(export_package(""))

    @patch.object(cont, "_HAVE_CRYPTO", False)
    def test_export_no_crypto(self):
        self.assertIsNone(export_package("pw"))

    def test_export_import_roundtrip(self):
        with patch("orbit.core.smart_memory.get_smart_memory") as gsm, \
             patch("orbit.core.companion_memory.get_companion_memory") as gcm:
            gsm.return_value._data = {"m": 1}
            gcm.return_value.timeline.return_value = [{"text": "t"}]
            pkg = export_package("secret")
        self.assertIsNotNone(pkg)
        base64.b64decode(pkg)
        r = import_package(pkg, "secret")
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["smart_memory"], {"m": 1})
        self.assertEqual(r["data"]["companion_memory"], [{"text": "t"}])

    def test_export_json_serializable_with_default_str(self):
        class Weird:
            def __str__(self):
                return "weird-obj"
        with patch("orbit.core.smart_memory.get_smart_memory") as gsm, \
             patch("orbit.core.companion_memory.get_companion_memory") as gcm:
            gsm.return_value._data = {"obj": Weird()}
            gcm.return_value.timeline.return_value = []
            pkg = export_package("pw")
        r = import_package(pkg, "pw")
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["smart_memory"]["obj"], "weird-obj")


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography not installed")
class TestImportPackage(unittest.TestCase):
    def _make_pkg(self, passphrase):
        with patch("orbit.core.smart_memory.get_smart_memory") as gsm, \
             patch("orbit.core.companion_memory.get_companion_memory") as gcm:
            gsm.return_value._data = {"x": 1}
            gcm.return_value.timeline.return_value = []
            return export_package(passphrase)

    def test_wrong_passphrase(self):
        pkg = self._make_pkg("right")
        r = import_package(pkg, "wrong")
        self.assertFalse(r["ok"])
        self.assertIn("decrypt failed", r["error"])

    def test_garbage_input(self):
        r = import_package("!!!not-valid!!!", "p")
        self.assertFalse(r["ok"])
        self.assertIn("decrypt failed", r["error"])

    def test_empty_string(self):
        r = import_package("", "p")
        self.assertFalse(r["ok"])

    @patch.object(cont, "_HAVE_CRYPTO", False)
    def test_import_no_crypto(self):
        r = import_package("whatever", "p")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "cryptography unavailable")


if __name__ == "__main__":
    unittest.main()
