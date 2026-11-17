"""Unit tests for orbit/orbit/core/mesh.py."""

import base64
import json
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

import orbit.core.mesh as mesh_mod
from orbit.core.mesh import _key, export_capsule, import_capsule, _HAVE_CRYPTO


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography not installed")
class TestKey(unittest.TestCase):
    def test_key_is_urlsafe_b64_of_sha256(self):
        import hashlib
        import base64 as b64
        expected = b64.urlsafe_b64encode(hashlib.sha256("pass".encode("utf-8")).digest())
        self.assertEqual(_key("pass"), expected)

    def test_key_deterministic(self):
        self.assertEqual(_key("abc"), _key("abc"))

    def test_key_differs_by_passphrase(self):
        self.assertNotEqual(_key("abc"), _key("abd"))

    def test_key_returns_bytes(self):
        self.assertIsInstance(_key("x"), bytes)


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography not installed")
class TestExportCapsule(unittest.TestCase):
    def test_export_import_roundtrip(self):
        cap = export_capsule("mytool", "print('hi')", "secret-pass", {"v": 1})
        self.assertIsNotNone(cap)
        r = import_capsule(cap, "secret-pass")
        self.assertTrue(r["ok"])
        self.assertEqual(r["name"], "mytool")
        self.assertEqual(r["code"], "print('hi')")
        self.assertEqual(r["meta"], {"v": 1})

    def test_export_empty_passphrase_returns_none(self):
        self.assertIsNone(export_capsule("n", "c", ""))

    def test_export_meta_defaults_to_empty(self):
        cap = export_capsule("n", "c", "p")
        r = import_capsule(cap, "p")
        self.assertEqual(r["meta"], {})

    def test_export_unicode(self):
        cap = export_capsule("tool", "# héllo wörld ☃", "pw")
        r = import_capsule(cap, "pw")
        self.assertTrue(r["ok"])
        self.assertEqual(r["code"], "# héllo wörld ☃")

    def test_export_token_is_b64(self):
        cap = export_capsule("n", "c", "p")
        # should decode as base64 without error
        base64.b64decode(cap)

    @patch.object(mesh_mod, "_HAVE_CRYPTO", False)
    def test_export_no_crypto_returns_none(self):
        self.assertIsNone(export_capsule("n", "c", "p"))


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography not installed")
class TestImportCapsule(unittest.TestCase):
    def test_wrong_passphrase_fails(self):
        cap = export_capsule("n", "c", "right")
        r = import_capsule(cap, "wrong")
        self.assertFalse(r["ok"])
        self.assertIn("decrypt failed", r["error"])

    def test_garbage_input_fails(self):
        r = import_capsule("not-a-valid-capsule!!", "p")
        self.assertFalse(r["ok"])
        self.assertIn("decrypt failed", r["error"])

    def test_empty_string_fails(self):
        r = import_capsule("", "p")
        self.assertFalse(r["ok"])

    def test_non_dict_payload_returns_empty(self):
        # encrypt a JSON list (non-dict) manually
        from cryptography.fernet import Fernet
        token = Fernet(_key("p")).encrypt(b'[1, 2, 3]')
        cap = base64.b64encode(token).decode("ascii")
        r = import_capsule(cap, "p")
        self.assertEqual(r, {})

    @patch.object(mesh_mod, "_HAVE_CRYPTO", False)
    def test_import_no_crypto(self):
        r = import_capsule("whatever", "p")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "cryptography unavailable")


if __name__ == "__main__":
    unittest.main()
