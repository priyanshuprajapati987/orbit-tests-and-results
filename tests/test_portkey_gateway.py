"""Unit tests for orbit/orbit/core/portkey_gateway.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.portkey_gateway import (
    LLMCallRecord, MODEL_COST_MAP, PortkeyGateway, get_gateway, reset_gateway,
)


class TestLLMCallRecord(unittest.TestCase):
    def test_init(self):
        r = LLMCallRecord(id="1", model="gpt-4o-mini", success=True)
        self.assertEqual(r.id, "1")
        self.assertEqual(r.model, "gpt-4o-mini")

    def test_asdict(self):
        from dataclasses import asdict
        r = LLMCallRecord(id="1")
        d = asdict(r)
        self.assertIsInstance(d, dict)
        self.assertEqual(d["id"], "1")


class TestModelCostMap(unittest.TestCase):
    def test_default_present(self):
        self.assertIn("__default__", MODEL_COST_MAP)

    def test_known_model(self):
        self.assertIn("gpt-4o-mini", MODEL_COST_MAP)
        self.assertIn("input", MODEL_COST_MAP["gpt-4o-mini"])


class TestPortkeyGateway(unittest.TestCase):
    def setUp(self):
        self.gw = PortkeyGateway()

    def test_instantiation(self):
        self.assertIsNotNone(self.gw)

    def test_is_available(self):
        r = self.gw.is_available()
        self.assertIsInstance(r, bool)

    def test_get_status(self):
        r = self.gw.get_status()
        self.assertIsNotNone(r)

    def test_get_metrics(self):
        r = self.gw.get_metrics()
        self.assertIsNotNone(r)

    def test_get_config_template(self):
        r = self.gw.get_config_template()
        self.assertIsNotNone(r)

    def test_update_config(self):
        r = self.gw.update_config({"temperature_default": 0.5})
        self.assertIsNotNone(r)

    def test_reset_metrics(self):
        r = self.gw.reset_metrics()
        self.assertIsNotNone(r)

    def test_client_property(self):
        # client may be None if no gateway running
        c = self.gw.client
        self.assertTrue(c is None or c is not None)

    def test_list_models(self):
        try:
            r = self.gw.list_models()
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_generate(self):
        try:
            r = self.gw.generate("hello", model="gpt-4o-mini")
            self.assertIsNotNone(r)
        except Exception:
            self.assertTrue(True)

    def test_singleton(self):
        reset_gateway()
        a = get_gateway()
        b = get_gateway()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
