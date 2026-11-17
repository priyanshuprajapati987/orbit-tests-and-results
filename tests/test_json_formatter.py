"""Unit tests for orbit/orbit/core/json_formatter.py."""

import json
import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.json_formatter import JSONFormatter, get_json_formatter


class TestClampIndent(unittest.TestCase):
    def test_valid_indent(self):
        self.assertEqual(JSONFormatter._clamp_indent(4), 4)

    def test_clamp_max(self):
        self.assertEqual(JSONFormatter._clamp_indent(100), 8)

    def test_clamp_min(self):
        self.assertEqual(JSONFormatter._clamp_indent(-5), 0)

    def test_zero_allowed(self):
        self.assertEqual(JSONFormatter._clamp_indent(0), 0)

    def test_none_defaults_to_2(self):
        self.assertEqual(JSONFormatter._clamp_indent(None), 2)

    def test_string_number(self):
        self.assertEqual(JSONFormatter._clamp_indent("4"), 4)

    def test_bad_string_defaults_to_2(self):
        self.assertEqual(JSONFormatter._clamp_indent("abc"), 2)


class TestFormatJson(unittest.TestCase):
    def setUp(self):
        self.jf = JSONFormatter()

    def test_valid_dict(self):
        r = self.jf.format_json('{"a": 1}')
        self.assertEqual(r["status"], "valid")
        self.assertEqual(r["type"], "dict")
        self.assertIn('"a": 1', r["formatted"])
        self.assertGreater(r["size"], 0)

    def test_indent_clamped(self):
        r = self.jf.format_json('{"a": 1}', indent=99)
        # indent clamped to 8 -> 8 spaces before "a"
        self.assertIn('\n        "a"', r["formatted"])

    def test_indent_zero(self):
        r = self.jf.format_json('{"a": 1}', indent=0)
        self.assertIn('"a": 1', r["formatted"])

    def test_unicode_preserved(self):
        r = self.jf.format_json('{"emoji": "☕"}')
        self.assertEqual(r["status"], "valid")
        self.assertIn("☕", r["formatted"])

    def test_invalid_json(self):
        r = self.jf.format_json("{invalid json")
        self.assertEqual(r["status"], "invalid")
        self.assertIn("error", r)
        self.assertIn("line", r)
        self.assertIn("column", r)

    def test_non_dict_returns_empty(self):
        self.assertEqual(self.jf.format_json("[1, 2]"), {})
        self.assertEqual(self.jf.format_json('"hello"'), {})
        self.assertEqual(self.jf.format_json("42"), {})
        self.assertEqual(self.jf.format_json("null"), {})

    def test_none_input(self):
        r = self.jf.format_json(None)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("error", r)


class TestMinify(unittest.TestCase):
    def setUp(self):
        self.jf = JSONFormatter()

    def test_minify_dict(self):
        r = self.jf.minify('{"a": 1, "b": 2}')
        self.assertEqual(r["status"], "minified")
        self.assertEqual(r["minified"], '{"a":1,"b":2}')
        self.assertEqual(r["size"], len(r["minified"]))

    def test_minify_removes_whitespace(self):
        pretty = json.dumps({"a": 1, "b": [1, 2]}, indent=4)
        r = self.jf.minify(pretty)
        self.assertNotIn("    ", r["minified"])
        self.assertNotIn("\n", r["minified"])

    def test_minify_non_dict(self):
        self.assertEqual(self.jf.minify("[1, 2]"), {})

    def test_minify_invalid(self):
        r = self.jf.minify("{bad")
        self.assertEqual(r["status"], "invalid")
        self.assertIn("error", r)

    def test_minify_none(self):
        r = self.jf.minify(None)
        self.assertEqual(r["status"], "invalid")


class TestValidate(unittest.TestCase):
    def setUp(self):
        self.jf = JSONFormatter()

    def test_validate_valid(self):
        r = self.jf.validate('{"a": 1}')
        self.assertTrue(r["valid"])
        self.assertEqual(r["type"], "dict")

    def test_validate_list(self):
        r = self.jf.validate("[1, 2]")
        self.assertTrue(r["valid"])
        self.assertEqual(r["type"], "list")

    def test_validate_string(self):
        r = self.jf.validate('"hi"')
        self.assertTrue(r["valid"])
        self.assertEqual(r["type"], "str")

    def test_validate_invalid(self):
        r = self.jf.validate("{nope")
        self.assertFalse(r["valid"])
        self.assertIn("error", r)
        self.assertIn("line", r)

    def test_validate_none(self):
        r = self.jf.validate(None)
        self.assertFalse(r["valid"])

    def test_validate_empty_string(self):
        r = self.jf.validate("")
        self.assertFalse(r["valid"])


class TestExtractKeys(unittest.TestCase):
    def setUp(self):
        self.jf = JSONFormatter()

    def test_extract_dict_keys(self):
        r = self.jf.extract_keys('{"b": 1, "a": 2, "c": 3}')
        self.assertEqual(r["keys"], ["b", "a", "c"])
        self.assertEqual(r["count"], 3)

    def test_extract_list_returns_empty(self):
        self.assertEqual(self.jf.extract_keys("[1, 2]"), {})

    def test_extract_string_returns_empty(self):
        self.assertEqual(self.jf.extract_keys('"hi"'), {})

    def test_extract_number_returns_empty(self):
        self.assertEqual(self.jf.extract_keys("42"), {})

    def test_extract_null_returns_empty(self):
        self.assertEqual(self.jf.extract_keys("null"), {})

    def test_extract_invalid(self):
        r = self.jf.extract_keys("{bad")
        self.assertIn("error", r)

    def test_extract_empty_dict(self):
        r = self.jf.extract_keys("{}")
        self.assertEqual(r["keys"], [])
        self.assertEqual(r["count"], 0)

    def test_extract_none(self):
        r = self.jf.extract_keys(None)
        self.assertIn("error", r)


class TestGetJsonFormatter(unittest.TestCase):
    def test_singleton(self):
        a = get_json_formatter()
        b = get_json_formatter()
        self.assertIs(a, b)

    def test_instance_type(self):
        self.assertIsInstance(get_json_formatter(), JSONFormatter)


if __name__ == "__main__":
    unittest.main()
