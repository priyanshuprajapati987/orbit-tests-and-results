"""Unit tests for orbit/orbit/core/password_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.password_bp import password_bp


class TestPasswordBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(password_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(password_bp.name, "password_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        self.assertIn("/api/password/generate", rules)
        self.assertIn("/api/password/passphrase", rules)

    def test_generate(self):
        with patch("orbit.core.password_bp.get_password_generator") as gp:
            gp.return_value.generate.return_value = {"password": "abc123"}
            r = self.client.post("/api/password/generate", json={"length": 8, "upper": False, "lower": True, "digits": True, "symbols": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["password"], "abc123")
        gp.return_value.generate.assert_called_once_with(length=8, use_upper=False, use_lower=True, use_digits=True, use_symbols=False)

    def test_generate_defaults(self):
        with patch("orbit.core.password_bp.get_password_generator") as gp:
            gp.return_value.generate.return_value = {"password": "x"}
            r = self.client.post("/api/password/generate", json={})
        gp.return_value.generate.assert_called_once_with(length=16, use_upper=True, use_lower=True, use_digits=True, use_symbols=True)

    def test_generate_no_body(self):
        with patch("orbit.core.password_bp.get_password_generator") as gp:
            gp.return_value.generate.return_value = {"password": "x"}
            r = self.client.post("/api/password/generate")
        gp.return_value.generate.assert_called_once_with(length=16, use_upper=True, use_lower=True, use_digits=True, use_symbols=True)

    def test_passphrase(self):
        with patch("orbit.core.password_bp.get_password_generator") as gp:
            gp.return_value.generate_passphrase.return_value = {"passphrase": "word1-word2-word3-word4"}
            r = self.client.post("/api/password/passphrase", json={"words": 4})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["passphrase"], "word1-word2-word3-word4")
        gp.return_value.generate_passphrase.assert_called_once_with(4)

    def test_passphrase_default(self):
        with patch("orbit.core.password_bp.get_password_generator") as gp:
            gp.return_value.generate_passphrase.return_value = {"passphrase": "x"}
            r = self.client.post("/api/password/passphrase", json={})
        gp.return_value.generate_passphrase.assert_called_once_with(4)

    def test_passphrase_no_body(self):
        with patch("orbit.core.password_bp.get_password_generator") as gp:
            gp.return_value.generate_passphrase.return_value = {"passphrase": "x"}
            r = self.client.post("/api/password/passphrase")
        gp.return_value.generate_passphrase.assert_called_once_with(4)


if __name__ == "__main__":
    unittest.main()
