"""Unit tests for orbit/orbit/core/encryption_manager.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.encryption_manager import (
    EncryptionManager, get_encryption_manager, generate_key, hash_sha256,
    simple_encrypt, simple_decrypt, generate_api_key, generate_password,
)


class TestEncryptionManager(unittest.TestCase):
    def setUp(self):
        self.em = EncryptionManager()

    def test_instantiation(self):
        self.assertIsNotNone(self.em)

    def test_generate_key(self):
        k = self.em.generate_key(16)
        self.assertIsInstance(k, str)
        self.assertEqual(len(k), 32)

    def test_generate_salt(self):
        s = self.em.generate_salt(8)
        self.assertIsInstance(s, str)
        self.assertEqual(len(s), 16)

    def test_hash_sha256(self):
        h = self.em.hash_sha256("hello")
        self.assertEqual(len(h), 64)

    def test_hash_sha256_with_salt(self):
        h = self.em.hash_sha256("hello", salt="salt")
        self.assertEqual(len(h), 64)
        self.assertNotEqual(h, self.em.hash_sha256("hello"))

    def test_hash_sha512(self):
        h = self.em.hash_sha512("hello")
        self.assertEqual(len(h), 128)

    def test_hash_md5(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            h = self.em.hash_md5("hello")
        self.assertEqual(len(h), 32)

    def test_verify_hash_sha256(self):
        h = self.em.hash_sha256("hello")
        self.assertTrue(self.em.verify_hash("hello", h, "sha256"))

    def test_verify_hash_wrong(self):
        self.assertFalse(self.em.verify_hash("hello", "0" * 64, "sha256"))

    def test_create_hmac(self):
        sig = self.em.create_hmac("data", "key")
        self.assertIsInstance(sig, str)
        self.assertTrue(len(sig) > 0)

    def test_verify_hmac(self):
        sig = self.em.create_hmac("data", "key")
        self.assertTrue(self.em.verify_hmac("data", "key", sig))

    def test_simple_encrypt_decrypt(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            enc = self.em.simple_encrypt("hello", "key")
        dec = self.em.simple_decrypt(enc, "key")
        self.assertEqual(dec, "hello")

    def test_simple_decrypt_bad(self):
        self.assertEqual(self.em.simple_decrypt("!!!", "key"), "")

    def test_generate_api_key(self):
        k = self.em.generate_api_key("orbit")
        self.assertTrue(k.startswith("orbit_"))

    def test_generate_password(self):
        p = self.em.generate_password(12)
        self.assertEqual(len(p), 12)

    def test_mask_sensitive(self):
        self.assertEqual(self.em.mask_sensitive("secret1234", 4), "secr******")

    def test_secure_compare(self):
        self.assertTrue(self.em.secure_compare("abc", "abc"))
        self.assertFalse(self.em.secure_compare("abc", "xyz"))

    def test_singleton(self):
        a = get_encryption_manager()
        b = get_encryption_manager()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_generate_key_func(self):
        self.assertIsInstance(generate_key(8), str)

    def test_hash_sha256_func(self):
        self.assertEqual(len(hash_sha256("hello")), 64)

    def test_simple_encrypt_decrypt_func(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            enc = simple_encrypt("hi", "k")
        self.assertEqual(simple_decrypt(enc, "k"), "hi")

    def test_generate_api_key_func(self):
        self.assertTrue(generate_api_key().startswith("orbit_"))

    def test_generate_password_func(self):
        self.assertEqual(len(generate_password(10)), 10)


if __name__ == "__main__":
    unittest.main()
