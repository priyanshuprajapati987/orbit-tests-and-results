"""Unit tests for orbit/orbit/core/doc_generator.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.doc_generator import DocGenerator, get_doc_generator


class TestDocGenerator(unittest.TestCase):
    def setUp(self):
        self.g = DocGenerator()

    def test_generate_empty(self):
        r = self.g.generate("", "empty")
        self.assertIn("# empty", r)
        self.assertIn("## Functions", r)
        self.assertIn("## Classes", r)

    def test_generate_function(self):
        src = "def foo(x, y):\n    \"\"\"Add two numbers.\"\"\"\n    return x + y\n"
        r = self.g.generate(src, "mathmod")
        self.assertIn("# mathmod", r)
        self.assertIn("### `foo(x, y)`", r)
        self.assertIn("Add two numbers.", r)

    def test_generate_function_no_docstring(self):
        src = "def bar():\n    pass\n"
        r = self.g.generate(src, "m")
        self.assertIn("### `bar()`", r)
        self.assertIn("No description.", r)

    def test_generate_class(self):
        src = "class Foo:\n    \"\"\"A foo class.\"\"\"\n    pass\n"
        r = self.g.generate(src, "m")
        self.assertIn("### `Foo`", r)
        self.assertIn("A foo class.", r)

    def test_generate_syntax_error(self):
        r = self.g.generate("def broken(:\n", "m")
        self.assertTrue(r.startswith("# Error:"))

    def test_generate_multiple(self):
        src = "def a():\n    pass\ndef b(x):\n    pass\nclass C:\n    pass\n"
        r = self.g.generate(src, "m")
        self.assertIn("### `a()`", r)
        self.assertIn("### `b(x)`", r)
        self.assertIn("### `C`", r)

    def test_singleton(self):
        a = get_doc_generator()
        b = get_doc_generator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
