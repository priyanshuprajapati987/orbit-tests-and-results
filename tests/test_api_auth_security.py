"""Security regression tests for the ORBIT Flask API auth + SPA key injection.

Covers:
- API key fail-closed auth on /api/* endpoints
- Public health paths exempt
- index.html carries injected window.__ORBIT_API_KEY__ when auth enabled
- index.html is NOT CORS-readable (no Access-Control-Allow-Origin)
- JS assets still carry ACAO (needed by QtWebEngine)
- Wrong/absent key rejected
"""

import pytest

from orbit.orbit.server import create_app

TEST_KEY = "test-orbit-api-key-123456"


@pytest.fixture
def client(monkeypatch):
    from orbit.orbit import config

    monkeypatch.setattr(config, "ORBIT_API_KEY", TEST_KEY)
    monkeypatch.setattr(config, "ORBIT_API_AUTH_ENABLED", True)
    app = create_app()
    with app.test_client() as c:
        yield c


def test_health_public(client):
    assert client.get("/api/health").status_code == 200


def test_public_prefix_does_not_leak(client):
    """Public entries match exact-or-subtree only: /api/healthXYZ (a mere
    prefix collision, not a subtree) still requires auth, while the real
    /api/health subtree stays public."""
    assert client.get("/api/healthXYZ").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/dashboard").status_code == 200


def test_chat_engine_status_public(client):
    assert client.get("/api/chat/engine-status").status_code == 200


def test_api_requires_key(client):
    assert client.get("/api/watchdog/status").status_code == 401


def test_api_wrong_key_rejected(client):
    r = client.get("/api/watchdog/status", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_api_bearer_key_accepted(client):
    r = client.get(
        "/api/watchdog/status", headers={"Authorization": "Bearer " + TEST_KEY}
    )
    assert r.status_code == 200


def test_api_x_api_key_accepted(client):
    r = client.get("/api/watchdog/status", headers={"X-API-Key": TEST_KEY})
    assert r.status_code == 200


def test_index_injects_api_key(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "__ORBIT_API_KEY__" in r.get_data(as_text=True)


def _injected_nonce(html):
    import re

    m = re.search(r'script nonce="([^"]+)"', html)
    return m.group(1) if m else None


def _csp_nonce(resp):
    import re

    m = re.search(r"nonce-([^'\s]+)", resp.headers.get("Content-Security-Policy", ""))
    return m.group(1) if m else None


def test_index_never_served_as_304(client):
    """Regression: a conditional GET must NOT return 304. A 304 keeps the old
    cached body (old injected-script nonce) but ships a NEW CSP nonce header ->
    inline script refused -> window.__ORBIT_API_KEY__ undefined -> every /api
    call 401 -> broken UI. index.html must always be a full 200."""
    first = client.get("/")
    etag = first.headers.get("ETag")
    if not etag:
        pytest.skip("no etag to condition on")
    r = client.get("/", headers={"If-None-Match": etag})
    assert r.status_code == 200
    assert "__ORBIT_API_KEY__" in r.get_data(as_text=True)


def test_index_html_no_store(client):
    r = client.get("/")
    cc = (r.headers.get("Cache-Control") or "").lower()
    assert "no-store" in cc


def test_index_injected_nonce_matches_csp(client):
    first = client.get("/")
    assert _injected_nonce(first.get_data(as_text=True)) == _csp_nonce(first)
    etag = first.headers.get("ETag")
    if etag:
        reloaded = client.get("/", headers={"If-None-Match": etag})
        assert reloaded.status_code == 200
        assert _injected_nonce(reloaded.get_data(as_text=True)) == _csp_nonce(reloaded)


def test_index_not_cors_readable(client):
    r = client.get("/")
    assert r.headers.get("Access-Control-Allow-Origin") is None


def test_js_assets_cors_loopback_only(client):
    import pathlib

    dist = pathlib.Path(__file__).resolve().parent.parent / "ui_provided" / "dist" / "assets"
    if not dist.exists():
        pytest.skip("frontend dist not built")
    js = next((p.name for p in dist.iterdir() if p.suffix == ".js"), None)
    if not js:
        pytest.skip("no js asset found")
    # Same-origin/loopback Origin is reflected so the local SPA can load modules.
    r = client.get(f"/assets/{js}", headers={"Origin": "http://127.0.0.1:5000"})
    assert r.status_code == 200
    assert r.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:5000"


def test_js_assets_cors_external_denied(client):
    import pathlib

    dist = pathlib.Path(__file__).resolve().parent.parent / "ui_provided" / "dist" / "assets"
    if not dist.exists():
        pytest.skip("frontend dist not built")
    js = next((p.name for p in dist.iterdir() if p.suffix == ".js"), None)
    if not js:
        pytest.skip("no js asset found")
    # An external site must NOT get a CORS header -> cross-origin reads denied.
    r = client.get(f"/assets/{js}", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 200
    assert r.headers.get("Access-Control-Allow-Origin") is None


def test_key_does_not_leak_into_js_assets(client):
    import pathlib

    dist = pathlib.Path(__file__).resolve().parent.parent / "ui_provided" / "dist" / "assets"
    if not dist.exists():
        pytest.skip("frontend dist not built")
    js = next((p.name for p in dist.iterdir() if p.suffix == ".js"), None)
    if not js:
        pytest.skip("no js asset found")
    r = client.get(f"/assets/{js}")
    assert TEST_KEY not in r.get_data(as_text=True)


def test_key_not_injected_when_disabled(client, monkeypatch):
    from orbit.orbit import config

    monkeypatch.setattr(config, "ORBIT_API_AUTH_ENABLED", False)
    app = create_app()
    with app.test_client() as c:
        r = c.get("/")
        assert "__ORBIT_API_KEY__" not in r.get_data(as_text=True)
        assert c.get("/api/agents").status_code != 401


def test_injected_token_is_not_master_key(client):
    """The browser only ever receives the ephemeral UI token, never the master key."""
    r = client.get("/")
    html = r.get_data(as_text=True)
    # extract window.__ORBIT_API_KEY__="..." value
    import re

    m = re.search(r'window\.__ORBIT_API_KEY__="([^"]*)"', html)
    assert m, "UI token not injected"
    assert m.group(1) != TEST_KEY
    assert len(m.group(1)) >= 16


def test_ui_token_authenticates(client):
    """The injected UI token must satisfy the API auth gate."""
    import re

    html = client.get("/").get_data(as_text=True)
    m = re.search(r'window\.__ORBIT_API_KEY__="([^"]*)"', html)
    token = m.group(1)
    # UI token works
    r = client.get("/api/agents", headers={"X-API-Key": token})
    assert r.status_code == 200
    # Master key also still works (server-side only)
    r2 = client.get("/api/agents", headers={"X-API-Key": TEST_KEY})
    assert r2.status_code == 200


def test_billing_webhook_public(client):
    """Real Stripe POSTs carry no ORBIT key — the webhook must bypass API-key
    auth (it verifies the Stripe-Signature itself) instead of 401-ing every
    checkout event in production."""
    r = client.post(
        "/api/billing/webhook",
        data=b"{}",
        content_type="application/json",
    )
    assert r.status_code != 401
    # and it actually reaches the view (verification failure => 400, not auth wall)
    assert r.status_code in (400, 500)
