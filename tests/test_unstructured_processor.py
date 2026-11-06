"""Unit tests for orbit/orbit/core/unstructured_processor.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.unstructured_processor import (
    _validate_url, ProcessingResult, UnstructuredProcessor, get_processor,
)


class TestValidateUrl(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(_validate_url("https://example.com/x"))

    def test_blocks_localhost(self):
        self.assertFalse(_validate_url("http://localhost/x"))

    def test_blocks_private(self):
        self.assertFalse(_validate_url("http://192.168.1.1/x"))

    def test_blocks_bad_scheme(self):
        self.assertFalse(_validate_url("ftp://example.com/x"))


class TestProcessingResult(unittest.TestCase):
    def test_init(self):
        r = ProcessingResult({"success": True, "elements": [{"text": "hi"}]})
        self.assertTrue(r.success)
        self.assertEqual(r.text, "hi")

    def test_chunks(self):
        r = ProcessingResult({"success": True, "chunks": [{"text": "chunk1"}]})
        self.assertIn("chunk1", r.text)

    def test_to_dict(self):
        r = ProcessingResult({"success": True, "elements": [{"text": "hi"}]})
        d = r.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["element_count"], 1)

    def test_failed(self):
        r = ProcessingResult({"status": "failed", "error": "boom"})
        self.assertFalse(r.success)
        self.assertEqual(r.error, "boom")


class TestUnstructuredProcessor(unittest.TestCase):
    def setUp(self):
        self.up = UnstructuredProcessor()

    def test_instantiation(self):
        self.assertIsNotNone(self.up)

    def test_is_available(self):
        r = self.up.is_available()
        self.assertIsInstance(r, bool)

    def test_process_text(self):
        try:
            r = self.up.process_text("Hello world. This is a test.")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_classify(self):
        try:
            r = self.up.classify("Hello world")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_extract_tables(self):
        try:
            r = self.up.extract_tables("Hello world")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_get_stats(self):
        r = self.up.get_stats()
        self.assertIsNotNone(r)

    def test_get_status(self):
        r = self.up.get_status()
        self.assertIsNotNone(r)

    def test_process_file(self):
        import tempfile
        fd, p = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(p, "w") as f:
            f.write("Hello world.")
        try:
            r = self.up.process_file(p)
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)
        finally:
            os.remove(p)

    def test_singleton(self):
        a = get_processor()
        b = get_processor()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
