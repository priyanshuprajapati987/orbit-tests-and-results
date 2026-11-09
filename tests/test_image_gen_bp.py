"""Unit tests for orbit/orbit/core/image_gen_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.image_gen_bp import image_gen_bp


class TestImageGenBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(image_gen_bp)
        self.client = self.app.test_client()

    def test_blueprint_name(self):
        self.assertEqual(image_gen_bp.name, "image_gen_bp")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/image-gen/generate", "/api/image-gen/recent", "/api/image-gen/cache/clear"]:
            self.assertIn(p, rules)

    def test_generate_missing_prompt_400(self):
        r = self.client.post("/api/image-gen/generate", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_generate_invalid_model_400(self):
        r = self.client.post("/api/image-gen/generate", json={"prompt": "hi", "model": "foo"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Invalid model", r.get_json()["error"])

    def test_generate_success(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            engine = ge.return_value
            result = MagicMock()
            result.error = None
            result.images = ["img1"]
            result.model_used = "dalle3"
            result.latency_ms = 123.456
            result.cached = True
            engine.generate.return_value = result
            r = self.client.post("/api/image-gen/generate", json={"prompt": "a cat", "model": "dalle3", "quality": "hd", "style": "natural", "width": 512, "height": 512, "n": 2, "seed": 42, "steps": 10, "guidance_scale": 8.0, "negative_prompt": "blurry"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["images"], ["img1"])
        self.assertEqual(body["model_used"], "dalle3")
        self.assertEqual(body["latency_ms"], 123.5)
        self.assertTrue(body["cached"])
        req = engine.generate.call_args[0][0]
        self.assertEqual(req.prompt, "a cat")
        self.assertEqual(req.model, "dalle3")
        self.assertEqual(req.quality, "hd")
        self.assertEqual(req.style, "natural")
        self.assertEqual(req.width, 512)
        self.assertEqual(req.height, 512)
        self.assertEqual(req.n, 2)
        self.assertEqual(req.seed, 42)
        self.assertEqual(req.steps, 10)
        self.assertEqual(req.guidance_scale, 8.0)
        self.assertEqual(req.negative_prompt, "blurry")

    def test_generate_error(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            engine = ge.return_value
            result = MagicMock()
            result.error = "gen failed"
            engine.generate.return_value = result
            r = self.client.post("/api/image-gen/generate", json={"prompt": "hi"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "gen failed")

    def test_generate_quality_clamped(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            engine = ge.return_value
            result = MagicMock()
            result.error = None
            result.images = []
            result.model_used = "dalle3"
            result.latency_ms = 1.0
            result.cached = False
            engine.generate.return_value = result
            r = self.client.post("/api/image-gen/generate", json={"prompt": "hi", "quality": "invalid"})
        req = engine.generate.call_args[0][0]
        self.assertEqual(req.quality, "standard")

    def test_generate_style_clamped(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            engine = ge.return_value
            result = MagicMock()
            result.error = None
            result.images = []
            result.model_used = "dalle3"
            result.latency_ms = 1.0
            result.cached = False
            engine.generate.return_value = result
            r = self.client.post("/api/image-gen/generate", json={"prompt": "hi", "style": "invalid"})
        req = engine.generate.call_args[0][0]
        self.assertEqual(req.style, "vivid")

    def test_generate_width_clamped(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            engine = ge.return_value
            result = MagicMock()
            result.error = None
            result.images = []
            result.model_used = "dalle3"
            result.latency_ms = 1.0
            result.cached = False
            engine.generate.return_value = result
            r = self.client.post("/api/image-gen/generate", json={"prompt": "hi", "width": 9999, "height": 9999, "n": 10, "steps": 100})
        req = engine.generate.call_args[0][0]
        self.assertEqual(req.width, 2048)
        self.assertEqual(req.height, 2048)
        self.assertEqual(req.n, 4)
        self.assertEqual(req.steps, 50)

    def test_generate_no_body(self):
        r = self.client.post("/api/image-gen/generate")
        self.assertEqual(r.status_code, 400)

    def test_recent(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            ge.return_value.get_recent.return_value = [{"id": 1}]
            r = self.client.get("/api/image-gen/recent?limit=5")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["images"], [{"id": 1}])
        ge.return_value.get_recent.assert_called_once_with(5)

    def test_recent_default(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            ge.return_value.get_recent.return_value = []
            r = self.client.get("/api/image-gen/recent")
        ge.return_value.get_recent.assert_called_once_with(10)

    def test_clear_cache(self):
        with patch("orbit.core.image_gen_bp._get_engine") as ge:
            ge.return_value.clear_cache.return_value = {"cleared": True}
            r = self.client.post("/api/image-gen/cache/clear")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["cleared"])

    def test_register(self):
        from orbit.core.image_gen_bp import register
        server = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        self.assertTrue(register(server))
        server.register_blueprint.assert_called_once_with(image_gen_bp)


if __name__ == "__main__":
    unittest.main()
