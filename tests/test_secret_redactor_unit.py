"""Tests for SecretRedactor — secret masking in logs and audit."""

import os
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

from orbit.orbit.core.secret_redactor import (
    SecretRedactor,
    get_redactor,
    redact_text,
    redact_value,
)


class TestRedactText(unittest.TestCase):
    def test_openai_key_redacted(self):
        text = "api key: sk-proj-abc123def456ghi789jkl012mno345"
        result = redact_text(text)
        self.assertNotIn("sk-proj-abc", result)
        self.assertIn("[REDACTED]", result)

    def test_anthropic_key_redacted(self):
        text = "key: sk-ant-abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_text(text)
        self.assertNotIn("sk-ant-abc", result)
        self.assertIn("[REDACTED]", result)

    def test_google_key_redacted(self):
        # NOTE: deliberately non-standard length (32 chars after "AIza")
        # so GitHub secret-scanning does not flag this test fixture as a
        # real Google API key, while still matching ORBIT's redactor
        # pattern (AIza + 30+ chars).
        text = "api_key=AIzaFAKE-TEST-KEY-NOT-REAL-SECRET-01"
        result = redact_text(text)
        self.assertNotIn("AIzaFAKE", result)
        self.assertIn("[REDACTED]", result)

    def test_aws_key_redacted(self):
        text = "AKIAIOSFODNN7EXAMPLE"
        result = redact_text(text)
        self.assertNotIn("AKIAIOSF", result)
        self.assertIn("[REDACTED]", result)

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test.signature"
        result = redact_text(text)
        self.assertNotIn("Bearer eyJ", result)
        self.assertIn("[REDACTED]", result)

    def test_password_in_value_redacted(self):
        text = 'password="super_secret_123"'
        result = redact_text(text)
        self.assertNotIn("super_secret_123", result)

    def test_normal_text_preserved(self):
        text = "This is a normal log message with no secrets."
        result = redact_text(text)
        self.assertEqual(result, text)

    def test_empty_string(self):
        result = redact_text("")
        self.assertEqual(result, "")

    def test_private_key_redacted(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK..."
        result = redact_text(text)
        self.assertIn("[REDACTED]", result)

    def test_github_token_redacted(self):
        text = "token: ghp_abcdefghijklmnopqrstuvwxyz123456"
        result = redact_text(text)
        self.assertNotIn("ghp_abc", result)

    def test_multiple_secrets_in_one_string(self):
        text = "keys: sk-proj-abc123def456 and AKIAIOSFODNN7EXAMPLE"
        result = redact_text(text)
        self.assertNotIn("sk-proj-abc", result)
        self.assertNotIn("AKIAIOSF", result)
        self.assertIn("[REDACTED]", result)


class TestRedactValue(unittest.TestCase):
    def test_string_redact(self):
        result = redact_value("sk-proj-abc123def456ghi789jkl012mno345")
        self.assertIn("[REDACTED]", result)

    def test_dict_redact(self):
        data = {"api_key": "sk-proj-abc123def456ghi789jkl012", "name": "test"}
        result = redact_value(data)
        self.assertIn("[REDACTED]", str(result["api_key"]))
        self.assertEqual(result["name"], "test")

    def test_list_redact(self):
        data = ["sk-proj-abc123def456ghi789jkl012", "normal text"]
        result = redact_value(data)
        self.assertIn("[REDACTED]", str(result[0]))
        self.assertEqual(result[1], "normal text")

    def test_nested_redact(self):
        data = {"config": {"secret": "sk-proj-abc123def456ghi789jkl012"}}
        result = redact_value(data)
        self.assertIn("[REDACTED]", str(result["config"]["secret"]))

    def test_non_string_passthrough(self):
        self.assertEqual(redact_value(42), 42)
        self.assertIsNone(redact_value(None))
        self.assertTrue(redact_value(True))

    def test_header_key_masked(self):
        data = {"authorization": "Bearer token123", "content": "hello"}
        result = redact_value(data)
        self.assertEqual(result["authorization"], "[REDACTED]")
        self.assertEqual(result["content"], "hello")


class TestSecretRedactorClass(unittest.TestCase):
    def setUp(self):
        self.redactor = SecretRedactor()

    def test_redact_method(self):
        result = self.redactor.redact("sk-abc123def456ghi789")
        self.assertIn("[REDACTED]", result)
        self.assertEqual(self.redactor._redacted_count, 1)

    def test_redact_no_change(self):
        result = self.redactor.redact("no secrets here")
        self.assertEqual(result, "no secrets here")
        self.assertEqual(self.redactor._redacted_count, 0)

    def test_redact_dict(self):
        result = self.redactor.redact_dict({"key": "sk-proj-abc123def456ghi789"})
        self.assertIn("[REDACTED]", str(result["key"]))

    def test_stats(self):
        self.redactor.redact("sk-abc123def456ghi789")
        stats = self.redactor.stats()
        self.assertEqual(stats["redacted_items"], 1)
        self.assertGreater(stats["patterns"], 0)

    def test_reset(self):
        self.redactor.redact("sk-abc123def456ghi789")
        self.redactor.reset()
        self.assertEqual(self.redactor._redacted_count, 0)


class TestGetRedactor(unittest.TestCase):
    def test_singleton(self):
        r1 = get_redactor()
        r2 = get_redactor()
        self.assertIs(r1, r2)

    def test_singleton_is_redactor(self):
        r = get_redactor()
        self.assertIsInstance(r, SecretRedactor)


class TestSecretRedactorEdgeCases(unittest.TestCase):
    def test_jwt_not_redacted(self):
        """UUIDs should NOT be redacted (only credential-adjacent)."""
        text = "trace-id: 550e8400-e29b-41d4-a716-446655440000"
        result = redact_text(text)
        self.assertIn("550e8400", result)

    def test_no_false_positives(self):
        text = "Use the API endpoint /api/v1/users"
        result = redact_text(text)
        self.assertEqual(result, text)

    def test_mixed_content(self):
        text = "User test logged in with key sk-proj-abc123def456ghi789 at 10:00"
        result = redact_text(text)
        self.assertIn("User test logged in", result)
        self.assertNotIn("sk-proj-abc", result)


if __name__ == "__main__":
    unittest.main()
