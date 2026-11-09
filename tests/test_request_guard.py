"""Unit tests for orbit/orbit/core/request_guard.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.request_guard import RequestGuard, get_request_guard, DEFAULT_MAX_BODY_BYTES


class TestRequestGuard(unittest.TestCase):
    def setUp(self):
        self.g = RequestGuard(max_body_bytes=100)

    def test_max_body_bytes(self):
        self.assertEqual(self.g.max_body_bytes, 100)

    def test_validate_body_size_none(self):
        self.assertIsNone(self.g.validate_body_size(None))

    def test_validate_body_size_ok(self):
        self.assertIsNone(self.g.validate_body_size(50))

    def test_validate_body_size_too_large(self):
        r = self.g.validate_body_size(200)
        self.assertIn("too large", r)

    def test_validate_body_size_invalid(self):
        r = self.g.validate_body_size("abc")
        self.assertEqual(r, "Invalid Content-Length header")

    def test_validate_body_size_increments_stats(self):
        self.g.validate_body_size(50)
        self.g.validate_body_size(200)
        stats = self.g.get_stats()
        self.assertEqual(stats["checked"], 2)
        self.assertEqual(stats["rejected"], 1)

    def test_validate_json_depth_ok(self):
        self.assertIsNone(self.g.validate_json_depth({"a": 1, "b": [1, 2]}))

    def test_validate_json_depth_too_deep(self):
        # build 12 levels deep
        obj = 1
        for _ in range(12):
            obj = {"x": obj}
        r = self.g.validate_json_depth(obj)
        self.assertIn("nesting too deep", r)

    def test_validate_json_depth_big_dict(self):
        obj = {f"k{i}": i for i in range(1001)}
        r = self.g.validate_json_depth(obj)
        self.assertIn("dict too large", r)

    def test_validate_json_depth_big_list(self):
        obj = list(range(1001))
        r = self.g.validate_json_depth(obj)
        self.assertIn("list too large", r)

    def test_validate_json_depth_long_string(self):
        obj = "a" * 100001
        r = self.g.validate_json_depth(obj)
        self.assertIn("String value too long", r)

    def test_validate_json_depth_nested_list_in_dict(self):
        obj = {"a": [1, 2, {"b": "x" * 10}]}
        self.assertIsNone(self.g.validate_json_depth(obj))

    def test_get_stats_copy(self):
        self.g.validate_body_size(50)
        s = self.g.get_stats()
        s["checked"] = 999
        self.assertEqual(self.g.get_stats()["checked"], 1)

    def test_singleton(self):
        import orbit.core.request_guard as rg
        rg._singleton = None
        a = get_request_guard()
        b = get_request_guard()
        self.assertIs(a, b)
        rg._singleton = None

    def test_default_max_body_bytes(self):
        # int_env default
        g = RequestGuard()
        self.assertEqual(g.max_body_bytes, 16 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
