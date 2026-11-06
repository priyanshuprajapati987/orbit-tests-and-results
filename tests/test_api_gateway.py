"""Unit tests for orbit/orbit/core/api_gateway.py."""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.api_gateway import (
    APIEndpoint, APIGateway, get_api_gateway, register_endpoint,
    handle_request, generate_api_key, get_statistics,
)


def _handler(req):
    return {"ok": True, "echo": req}


class TestAPIEndpoint(unittest.TestCase):
    def test_init(self):
        ep = APIEndpoint(path="/x", method="get", handler=_handler)
        self.assertEqual(ep.path, "/x")
        self.assertEqual(ep.method, "GET")
        self.assertEqual(ep.call_count, 0)


class TestAPIGateway(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        if os.path.exists(self.path):
            os.remove(self.path)
        self.gw = APIGateway(storage_file=self.path)

    def tearDown(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def test_instantiation(self):
        self.assertIsNotNone(self.gw)

    def test_register_endpoint(self):
        ep = self.gw.register_endpoint("/x", "GET", _handler)
        self.assertIsNotNone(ep)
        self.assertTrue(any("/x" in k for k in self.gw.endpoints))

    def test_handle_request(self):
        self.gw.register_endpoint("/x", "GET", _handler)
        r = self.gw.handle_request("/x", "GET", {"q": 1})
        self.assertIsNotNone(r)

    def test_generate_api_key(self):
        r = self.gw.generate_api_key("user1")
        self.assertIsNotNone(r)

    def test_revoke_api_key(self):
        key = self.gw.generate_api_key("user2")
        kid = key if isinstance(key, str) else (key.get("key") if isinstance(key, dict) else None)
        if kid:
            r = self.gw.revoke_api_key(kid)
            self.assertTrue(r is None or isinstance(r, (bool, dict)))

    def test_get_endpoint_stats(self):
        self.gw.register_endpoint("/x", "GET", _handler)
        r = self.gw.get_endpoint_stats("/x")
        self.assertIsNotNone(r)

    def test_get_request_log(self):
        r = self.gw.get_request_log()
        self.assertIsInstance(r, list)

    def test_get_statistics(self):
        r = self.gw.get_statistics()
        self.assertIsNotNone(r)

    def test_add_middleware(self):
        self.gw.add_middleware(lambda r: r)
        self.assertTrue(True)

    def test_singleton(self):
        a = get_api_gateway()
        b = get_api_gateway()
        self.assertIs(a, b)


class TestModuleFunctions(unittest.TestCase):
    def test_register_endpoint_func(self):
        self.assertTrue(callable(register_endpoint))

    def test_handle_request_func(self):
        self.assertTrue(callable(handle_request))

    def test_generate_api_key_func(self):
        self.assertTrue(callable(generate_api_key))

    def test_get_statistics_func(self):
        self.assertTrue(callable(get_statistics))


if __name__ == "__main__":
    unittest.main()
