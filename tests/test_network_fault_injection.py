"""Phase 13 - network fault injection.

Injects network faults AT THE requests/urllib layer (no real network) and
verifies every entry point degrades gracefully instead of raising:

  faults: ConnectionError (refused), Timeout/ReadTimeout (hang),
          garbage response body (json ValueError), HTTP 500,
          urllib URLError (DNS/conn for the stdlib-based validator)

Guarantees under test:
  - N8nTool.check_status() returns {online: False, ...} for BOTH
    ConnectionError and Timeout (Phase-13 fix: used to catch only
    ConnectionError -> requests.Timeout crashed the caller)
  - LLM provider methods return LLMResponse(success=False) - never raise
  - LLMRouter.generate() returns a response object - never raises when
    every provider is unreachable
  - APIValidator degrades with urllib faults
"""
import asyncio
import json

import requests


# ------------------------------------------------------------------ helpers
class _FakeResponse:
    """Minimal requests-like response for garbage/HTTP-500 injection."""

    def __init__(self, status_code=200, json_body=None, json_raises=False):
        self.status_code = status_code
        self._json_body = json_body
        self._json_raises = json_raises
        self.text = json.dumps(json_body) if json_body is not None else "<html>bad</html>"

    def json(self):
        if self._json_raises:
            raise ValueError("No JSON object could be decoded")
        return self._json_body


def _raise_conn(*a, **k):
    raise requests.ConnectionError("Connection refused (fault injection)")


def _raise_timeout(*a, **k):
    raise requests.Timeout("Read timed out (fault injection)")


def _garbage(*a, **k):
    return _FakeResponse(status_code=200, json_raises=True)


def _http500(*a, **k):
    return _FakeResponse(status_code=500, json_body={"error": "boom"})


# ------------------------------------------------------------- n8n (fix #1)
def test_n8n_check_status_survives_connection_refused(monkeypatch):
    from orbit.orbit.tools.n8n import N8nTool

    monkeypatch.setattr(requests, "get", _raise_conn)
    status = N8nTool().check_status()
    assert status["online"] is False
    assert "error" in status


def test_n8n_check_status_survives_timeout(monkeypatch):
    """THE Phase-13 fix: requests.Timeout used to escape the old
    `except requests.ConnectionError` handler and crash the caller."""
    from orbit.orbit.tools.n8n import N8nTool

    monkeypatch.setattr(requests, "get", _raise_timeout)
    status = N8nTool().check_status()
    assert status["online"] is False
    assert "error" in status


# -------------------------------------------------- LLM provider call paths
def _run(coro):
    return asyncio.run(coro)


def test_call_ollama_survives_connection_refused(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _raise_conn)
    monkeypatch.setattr(requests, "get", _raise_conn)
    resp = _run(LLMRouter()._call_ollama(LLMRequest(prompt="hi")))
    assert resp is not None
    assert resp.success is False


def test_call_ollama_survives_timeout(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _raise_timeout)
    resp = _run(LLMRouter()._call_ollama(LLMRequest(prompt="hi")))
    assert resp is not None
    assert resp.success is False


def test_call_ollama_survives_garbage_body(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _garbage)
    resp = _run(LLMRouter()._call_ollama(LLMRequest(prompt="hi")))
    assert resp is not None
    assert resp.success is False


def test_call_ollama_survives_http500(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _http500)
    resp = _run(LLMRouter()._call_ollama(LLMRequest(prompt="hi")))
    assert resp is not None
    assert resp.success is False


def test_call_gemini_survives_connection_refused(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _raise_conn)
    monkeypatch.setattr(requests, "get", _raise_conn)
    out = _run(LLMRouter()._call_gemini(LLMRequest(prompt="hi"), model="gemini-flash"))
    # None (provider unavailable) or LLMResponse(success=False) - never a raise
    assert out is None or getattr(out, "success", True) is False


def test_call_openrouter_survives_connection_refused(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _raise_conn)
    monkeypatch.setattr(requests, "get", _raise_conn)
    out = _run(LLMRouter()._call_openrouter(LLMRequest(prompt="hi"), model="some-model"))
    assert out is None or getattr(out, "success", True) is False


# ------------------------------------------------------- full generate path
def test_full_generate_never_raises_when_all_providers_down(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _raise_conn)
    monkeypatch.setattr(requests, "get", _raise_conn)
    router = LLMRouter()
    req = LLMRequest(prompt="hello", use_cache=False, force_offline=True)
    resp = _run(router.generate(req))
    assert resp is not None
    assert isinstance(resp.content, str)


def test_full_generate_never_raises_on_timeout(monkeypatch):
    from orbit.orbit.core.llm.router import LLMRequest, LLMRouter

    monkeypatch.setattr(requests, "post", _raise_timeout)
    monkeypatch.setattr(requests, "get", _raise_timeout)
    router = LLMRouter()
    req = LLMRequest(prompt="hello", use_cache=False, force_offline=True)
    resp = _run(router.generate(req))
    assert resp is not None
    assert isinstance(resp.content, str)


# --------------------------------------------------------- legacy adapter
def test_legacy_adapter_survives_total_network_outage(monkeypatch):
    from orbit.orbit.core.llm import legacy_adapter as la

    monkeypatch.setattr(requests, "post", _raise_conn)
    monkeypatch.setattr(requests, "get", _raise_conn)
    out = la.generate(prompt="hi")
    assert isinstance(out, str)  # never raises; error string or answer


# -------------------------------------------------- api validator (urllib)
def test_api_validator_survives_urllib_fault(monkeypatch):
    import urllib.error
    import urllib.request

    import orbit.orbit.core.api_validator as av

    def _raise_urlerror(*a, **k):
        raise urllib.error.URLError("Name or service not known (fault injection)")

    monkeypatch.setattr(urllib.request, "urlopen", _raise_urlerror)
    v = av.APIValidator()
    results = v.validate_all(force=True)
    assert isinstance(results, dict)
    status = v.get_status()
    assert isinstance(status, dict)


def test_api_validator_survives_socket_timeout(monkeypatch, tmp_path):
    import urllib.request

    import orbit.orbit.core.api_validator as av

    def _raise_timeout(*a, **k):
        raise TimeoutError("timed out (fault injection)")

    monkeypatch.setattr(urllib.request, "urlopen", _raise_timeout)
    v = av.APIValidator()
    results = v.validate_all(force=True)
    assert isinstance(results, dict)
