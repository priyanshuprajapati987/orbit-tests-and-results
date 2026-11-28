"""Deep tests for orbit/orbit/core/json_formatter.py (Loop 24/1)."""
import json, unittest
from orbit.orbit.core import json_formatter as jf

class ClampTests(unittest.TestCase):
    def test_int(self): self.assertEqual(jf.JSONFormatter._clamp_indent(4),4)
    def test_str(self): self.assertEqual(jf.JSONFormatter._clamp_indent("4"),4)
    def test_none(self): self.assertEqual(jf.JSONFormatter._clamp_indent(None),2)
    def test_bad_str(self): self.assertEqual(jf.JSONFormatter._clamp_indent("abc"),2)
    def test_clamp_high(self): self.assertEqual(jf.JSONFormatter._clamp_indent(100),8)
    def test_clamp_low(self): self.assertEqual(jf.JSONFormatter._clamp_indent(-5),0)

class FormatTests(unittest.TestCase):
    def setUp(self): self.f = jf.JSONFormatter()
    def test_valid(self):
        r = self.f.format_json('{"a":1}')
        self.assertEqual(r["status"],"valid")
        self.assertIn('"a": 1', r["formatted"])
        self.assertEqual(r["type"],"dict")
        self.assertEqual(r["size"], len(r["formatted"]))
    def test_invalid_json(self):
        r = self.f.format_json('{bad}')
        self.assertEqual(r["status"],"invalid")
        self.assertIn("line", r)
        self.assertIn("column", r)
    def test_non_dict(self):
        self.assertEqual(self.f.format_json('[1,2]'), {})
    def test_type_error(self):
        r = self.f.format_json(None)
        self.assertEqual(r["status"],"invalid")
    def test_indent_clamp(self):
        r = self.f.format_json('{"a":1}', indent=100)
        self.assertIn("        ", r["formatted"])  # 8 spaces

class MinifyTests(unittest.TestCase):
    def setUp(self): self.f = jf.JSONFormatter()
    def test_valid(self):
        r = self.f.minify('{"a": 1, "b": 2}')
        self.assertEqual(r["status"],"minified")
        self.assertEqual(r["minified"],'{"a":1,"b":2}')
    def test_non_dict(self):
        self.assertEqual(self.f.minify('[1,2]'), {})
    def test_invalid(self):
        r = self.f.minify('{bad}')
        self.assertEqual(r["status"],"invalid")

class ValidateTests(unittest.TestCase):
    def setUp(self): self.f = jf.JSONFormatter()
    def test_valid(self):
        self.assertEqual(self.f.validate('{"a":1}'), {"valid":True,"type":"dict"})
    def test_invalid(self):
        r = self.f.validate('{bad}')
        self.assertFalse(r["valid"])
        self.assertIn("line", r)
    def test_list(self):
        self.assertEqual(self.f.validate('[1,2]'), {"valid":True,"type":"list"})
    def test_type_error(self):
        r = self.f.validate(None)
        self.assertFalse(r["valid"])

class ExtractKeysTests(unittest.TestCase):
    def setUp(self): self.f = jf.JSONFormatter()
    def test_dict(self):
        self.assertEqual(self.f.extract_keys('{"a":1,"b":2}'), {"keys":["a","b"],"count":2})
    def test_non_dict(self):
        self.assertEqual(self.f.extract_keys('[1,2]'), {})
    def test_invalid(self):
        r = self.f.extract_keys('{bad}')
        self.assertIn("error", r)
    def test_list_branch(self):
        # extract_keys checks isinstance dict first; list returns {} via first guard? Actually first guard returns {} for non-dict
        self.assertEqual(self.f.extract_keys('[1,2]'), {})

class SingletonTests(unittest.TestCase):
    def test_singleton(self):
        jf._json = None
        a = jf.get_json_formatter()
        b = jf.get_json_formatter()
        self.assertIs(a,b)
        jf._json = None

if __name__ == "__main__":
    unittest.main()
