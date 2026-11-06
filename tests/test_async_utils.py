"""Unit tests for orbit/orbit/core/async_utils.py."""

import os
import sys
import asyncio
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.async_utils import run_llm_sync


class TestAsyncUtils(unittest.TestCase):
    def test_plain_value_returned(self):
        self.assertEqual(run_llm_sync(42), 42)
        self.assertEqual(run_llm_sync("hello"), "hello")

    def test_coroutine_resolved(self):
        async def coro():
            return "result"
        r = run_llm_sync(coro())
        self.assertEqual(r, "result")

    def test_none_value(self):
        self.assertIsNone(run_llm_sync(None))


if __name__ == "__main__":
    unittest.main()
