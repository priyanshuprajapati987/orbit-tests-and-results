"""Deep tests for orbit/orbit/core/providers_bp.py (Loop 14/4)."""

import unittest
from unittest import mock

import flask

from orbit.orbit.core import providers_bp


def _validator():
    m = mock.MagicMock()
    m.validate_all.return_value = {"providers": {"groq": {"ok": True}}}
    m.get_status.return_value = {"groq": {"configured": True}}
    return m


def _vault():
    m = mock.MagicMock()
    m.status.return_value = {"groq": {"configured": True, "source": "env"}}
    m.set_key.return_value = {"ok": True, "provider": "groq"}
    m.clear_key.return_value = {"ok": True, "provider": "groq"}
    return m


class ProvidersBpTests(unittest.TestCase):
    def setUp(self):
        app = flask.Flask(__name__)
        app.register_blueprint(providers_bp.providers_bp)
        self.client = app.test_client()

    # ── status ──────────────────────────────────────────────────────

    def test_status_default(self):
        v = _validator()
        with mock.patch("orbit.orbit.core.api_validator.get_api_validator",
                        return_value=v):
            r = self.client.get("/api/providers/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"groq": {"configured": True}})
        v.get_status.assert_called_once()
        v.validate_all.assert_not_called()

    def test_status_force(self):
        v = _validator()
        with mock.patch("orbit.orbit.core.api_validator.get_api_validator",
                        return_value=v):
            r = self.client.get("/api/providers/status?force=1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"providers": {"groq": {"ok": True}}})
        v.validate_all.assert_called_once_with(force=True)

    def test_status_exception_500(self):
        with mock.patch("orbit.orbit.core.api_validator.get_api_validator",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/providers/status")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── route ───────────────────────────────────────────────────────

    def test_route_missing_prompt_400(self):
        with mock.patch("orbit.orbit.core.llm.router.analyze_prompt") as ap:
            r = self.client.get("/api/providers/route")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "prompt query param required")
        ap.assert_not_called()

    def test_route_success(self):
        plan = {"provider": "groq", "model": "llama"}
        stats = {"total": 5}
        with mock.patch("orbit.orbit.core.llm.router.analyze_prompt",
                        return_value=plan) as ap, \
                mock.patch("orbit.orbit.core.llm.orchestrator.get_orchestrator_stats",
                           return_value=stats):
            r = self.client.get("/api/providers/route?prompt=hello")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["provider"], "groq")
        self.assertEqual(body["orchestrator_stats"], stats)
        ap.assert_called_once_with("hello")

    def test_route_exception_500(self):
        with mock.patch("orbit.orbit.core.llm.router.analyze_prompt",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/providers/route?prompt=hi")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── orchestrator ────────────────────────────────────────────────

    def test_orchestrator_stats(self):
        stats = {"calls": 10}
        with mock.patch("orbit.orbit.core.llm.orchestrator.get_orchestrator_stats",
                        return_value=stats):
            r = self.client.get("/api/providers/orchestrator")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), stats)

    def test_orchestrator_exception_500(self):
        with mock.patch("orbit.orbit.core.llm.orchestrator.get_orchestrator_stats",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/providers/orchestrator")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── keys status ─────────────────────────────────────────────────

    def test_keys_status(self):
        v = _vault()
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        return_value=v):
            r = self.client.get("/api/providers/keys")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"groq": {"configured": True,
                                                 "source": "env"}})
        v.status.assert_called_once()

    def test_keys_status_exception_500(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        side_effect=RuntimeError("boom")):
            r = self.client.get("/api/providers/keys")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── keys save ───────────────────────────────────────────────────

    def test_keys_save_missing_400(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_vault") as g:
            r = self.client.post("/api/providers/keys", json={})
            r2 = self.client.post("/api/providers/keys",
                                  json={"provider": "groq"})
            r3 = self.client.post("/api/providers/keys",
                                  json={"provider": "groq", "key": ""})
            r4 = self.client.post("/api/providers/keys",
                                  json={"provider": "groq", "key": 123})
        for r in (r, r2, r3, r4):
            self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "provider and key required")
        g.assert_not_called()

    def test_keys_save_success(self):
        v = _vault()
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        return_value=v):
            r = self.client.post("/api/providers/keys",
                                 json={"provider": "groq", "key": "secret"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ok": True, "provider": "groq"})
        v.set_key.assert_called_once_with("groq", "secret")

    def test_keys_save_failure_400(self):
        v = _vault()
        v.set_key.return_value = {"ok": False, "error": "bad key"}
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        return_value=v):
            r = self.client.post("/api/providers/keys",
                                 json={"provider": "groq", "key": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json(), {"ok": False, "error": "bad key"})

    def test_keys_save_exception_500(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        side_effect=RuntimeError("boom")):
            r = self.client.post("/api/providers/keys",
                                 json={"provider": "groq", "key": "x"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    def test_keys_save_non_json_body(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_vault") as g:
            r = self.client.post("/api/providers/keys", data="",
                                 content_type="application/json")
        self.assertEqual(r.status_code, 400)
        g.assert_not_called()

    # ── keys delete ─────────────────────────────────────────────────

    def test_keys_delete_success(self):
        v = _vault()
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        return_value=v):
            r = self.client.delete("/api/providers/keys/groq")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"ok": True, "provider": "groq"})
        v.clear_key.assert_called_once_with("groq")

    def test_keys_delete_failure_400(self):
        v = _vault()
        v.clear_key.return_value = {"ok": False, "error": "nope"}
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        return_value=v):
            r = self.client.delete("/api/providers/keys/groq")
        self.assertEqual(r.status_code, 400)

    def test_keys_delete_exception_500(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_vault",
                        side_effect=RuntimeError("boom")):
            r = self.client.delete("/api/providers/keys/groq")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")

    # ── test endpoint ───────────────────────────────────────────────

    def test_test_unknown_provider_400(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key"):
            r = self.client.post("/api/providers/test",
                                 json={"provider": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "unknown provider")

    def test_test_ollama_success(self):
        resp = mock.MagicMock(status_code=200)
        with mock.patch("requests.get", return_value=resp), \
                mock.patch("orbit.orbit.config.OLLAMA_URL",
                           "http://localhost:11434"):
            r = self.client.post("/api/providers/test",
                                 json={"provider": "ollama"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"provider": "ollama", "ok": True,
                                        "detail": "HTTP 200"})

    def test_test_ollama_failure_status(self):
        resp = mock.MagicMock(status_code=500)
        with mock.patch("requests.get", return_value=resp), \
                mock.patch("orbit.orbit.config.OLLAMA_URL",
                           "http://localhost:11434"):
            r = self.client.post("/api/providers/test",
                                 json={"provider": "ollama"})
        self.assertEqual(r.get_json()["ok"], False)
        self.assertEqual(r.get_json()["detail"], "HTTP 500")

    def test_test_ollama_exception(self):
        with mock.patch("requests.get", side_effect=Exception("conn")), \
                mock.patch("orbit.orbit.config.OLLAMA_URL",
                           "http://localhost:11434"):
            r = self.client.post("/api/providers/test",
                                 json={"provider": "ollama"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ok"], False)
        self.assertIn("conn", r.get_json()["detail"])

    def test_test_no_key(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key",
                        return_value=None):
            r = self.client.post("/api/providers/test",
                                 json={"provider": "groq"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {"provider": "groq", "ok": False,
                                        "detail": "no key configured"})

    def test_test_openrouter_success(self):
        resp = mock.MagicMock(status_code=200)
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key",
                        return_value="key123"), \
                mock.patch("requests.get", return_value=resp) as rg:
            r = self.client.post("/api/providers/test",
                                 json={"provider": "openrouter"})
        self.assertEqual(r.get_json(), {"provider": "openrouter", "ok": True,
                                        "detail": "HTTP 200"})
        self.assertIn("openrouter.ai", rg.call_args.args[0])
        self.assertEqual(rg.call_args.kwargs["headers"]["Authorization"],
                         "Bearer key123")

    def test_test_openai_success(self):
        resp = mock.MagicMock(status_code=200)
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key",
                        return_value="key123"), \
                mock.patch("requests.get", return_value=resp) as rg:
            r = self.client.post("/api/providers/test",
                                 json={"provider": "openai"})
        self.assertEqual(r.get_json()["ok"], True)
        self.assertIn("api.openai.com", rg.call_args.args[0])

    def test_test_groq_success(self):
        resp = mock.MagicMock(status_code=200)
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key",
                        return_value="key123"), \
                mock.patch("requests.get", return_value=resp) as rg:
            r = self.client.post("/api/providers/test",
                                 json={"provider": "groq"})
        self.assertEqual(r.get_json()["ok"], True)
        self.assertIn("groq.com", rg.call_args.args[0])

    def test_test_gemini_success(self):
        resp = mock.MagicMock(status_code=200)
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key",
                        return_value="key123"), \
                mock.patch("requests.get", return_value=resp) as rg:
            r = self.client.post("/api/providers/test",
                                 json={"provider": "gemini"})
        self.assertEqual(r.get_json()["ok"], True)
        self.assertEqual(rg.call_args.kwargs["headers"]["x-goog-api-key"],
                         "key123")

    def test_test_http_exception(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key",
                        return_value="key123"), \
                mock.patch("requests.get", side_effect=Exception("boom")):
            r = self.client.post("/api/providers/test",
                                 json={"provider": "groq"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ok"], False)
        self.assertIn("boom", r.get_json()["detail"])

    def test_test_non_json_body(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key"):
            r = self.client.post("/api/providers/test", data="",
                                 content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_test_exception_500(self):
        with mock.patch("orbit.orbit.core.provider_keys.get_provider_key",
                        side_effect=RuntimeError("boom")):
            r = self.client.post("/api/providers/test",
                                 json={"provider": "groq"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "boom")


if __name__ == "__main__":
    unittest.main()
