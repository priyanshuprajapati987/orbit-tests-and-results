"""Milestone 7 — production deploy probes (liveness/readiness) + WSGI entry.

Covers: /api/healthz liveness, /api/readyz readiness (200/503 per dependency),
probe routes exempt from API-key auth, and the orbit.wsgi production entry.
"""

import os

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")

import pytest


@pytest.fixture(scope="module")
def app():
    from orbit.orbit.server import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


def test_healthz_alive(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "alive"
    assert "version" in body


def test_readyz_ready(client):
    r = client.get("/api/readyz")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ready"
    assert set(body["checks"]) >= {"data_dir", "frontend", "disk"}
    assert all(v == "ok" for v in body["checks"].values())


def test_readyz_503_when_data_dir_unwritable(client, monkeypatch):
    from orbit.orbit.core import runtime_paths

    def boom():
        raise RuntimeError("data dir not writable")

    monkeypatch.setattr(runtime_paths, "orbit_data_dir", boom)
    r = client.get("/api/readyz")
    assert r.status_code == 503
    body = r.get_json()
    assert body["status"] == "not_ready"
    assert "fail" in body["checks"]["data_dir"]


def test_readyz_503_when_frontend_missing(client, monkeypatch):
    from orbit.orbit.core import runtime_paths

    monkeypatch.setattr(runtime_paths, "frontend_dist", lambda: "/nonexistent/dist/path")
    r = client.get("/api/readyz")
    assert r.status_code == 503
    assert "fail" in r.get_json()["checks"]["frontend"]


def test_probes_are_public_paths():
    from orbit.orbit.config import ORBIT_API_PUBLIC_PATHS
    from orbit.orbit.server import _is_public_api_path

    assert _is_public_api_path("/api/healthz", ORBIT_API_PUBLIC_PATHS)
    assert _is_public_api_path("/api/readyz", ORBIT_API_PUBLIC_PATHS)
    # exact/subtree only — no prefix bleed
    assert not _is_public_api_path("/api/readyzEVIL", ORBIT_API_PUBLIC_PATHS)
    assert not _is_public_api_path("/api/admin/readyz", ORBIT_API_PUBLIC_PATHS)


def test_wsgi_exports_flask_app():
    import orbit.wsgi

    assert hasattr(orbit.wsgi.app, "url_map")
    rules = {str(r) for r in orbit.wsgi.app.url_map.iter_rules()}
    assert "/api/healthz" in rules
    assert "/api/readyz" in rules


def test_probes_public_when_auth_enabled(monkeypatch):
    """Probes must answer orchestrators without an API key even in fail-closed auth."""
    from orbit.orbit import config
    from orbit.orbit.server import create_app

    monkeypatch.setattr(config, "ORBIT_API_KEY", "test-key-probe-123456")
    monkeypatch.setattr(config, "ORBIT_API_AUTH_ENABLED", True)
    application = create_app()
    application.config["TESTING"] = True
    with application.test_client() as c:
        assert c.get("/api/healthz").status_code == 200
        assert c.get("/api/readyz").status_code == 200
        # non-probe endpoint still fail-closed
        assert c.get("/api/watchdog/status").status_code == 401
