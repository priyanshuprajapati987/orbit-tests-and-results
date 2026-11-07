"""Unit tests for orbit/orbit/core/test_generator.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.test_generator import TestGenerator, get_test_generator


class TestTestGenerator(unittest.TestCase):
    def setUp(self):
        self.g = TestGenerator()

    def test_empty_source(self):
        r = self.g.generate("", "m")
        self.assertIn("import pytest", r)
        self.assertIn("import m", r)

    def test_function(self):
        src = "def foo(x):\n    return x\n"
        r = self.g.generate(src, "mymod")
        self.assertIn("def test_foo():", r)
        self.assertIn("result = mymod.foo()", r)
        self.assertIn("assert result is not None", r)

    def test_class(self):
        src = "class Foo:\n    pass\n"
        r = self.g.generate(src, "mymod")
        self.assertIn("class TestFoo:", r)
        self.assertIn("obj = mymod.Foo()", r)

    def test_syntax_error(self):
        r = self.g.generate("def broken(:\n", "m")
        self.assertTrue(r.startswith("# Syntax error:"))

    def test_multiple(self):
        src = "def a():\n    pass\ndef b():\n    pass\nclass C:\n    pass\n"
        r = self.g.generate(src, "m")
        self.assertIn("def test_a():", r)
        self.assertIn("def test_b():", r)
        self.assertIn("class TestC:", r)

    def test_default_module_name(self):
        r = self.g.generate("def x():\n    pass\n")
        self.assertIn("import module", r)

    def test_singleton(self):
        a = get_test_generator()
        b = get_test_generator()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
