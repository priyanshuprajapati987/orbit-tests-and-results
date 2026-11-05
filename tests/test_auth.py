"""Milestone 2 auth regression tests (hermetic: isolated SQLite DB).

Covers: signup validation, first-user-admin bootstrap, login,
wrong-password rejection, refresh rotation + reuse rejection,
logout idempotency, /me, password reset flow, OAuth linking,
weak-password rejection, duplicate signup.
"""

import os

import pytest


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    db = tmp_path / "auth_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-1234567890123456")
    monkeypatch.setenv("ORBIT_API_KEY", "")
    monkeypatch.setenv("ORBIT_API_AUTH_ENABLED", "0")
    from orbit.orbit.core.auth import store as _store

    _store._engine = None
    _store._session_factory = None
    import orbit.orbit.core.auth.service as _svc

    _svc._initialized = False
    from orbit.orbit.core.auth_bp import auth_bp
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    _store._engine = None
    _store._session_factory = None
    _svc._initialized = False


def _signup(client, email="u1@x.com", password="correct-horse-99", name="U1"):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "display_name": name},
    )


def test_signup_first_user_admin(app_client):
    r = _signup(app_client)
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    assert d["user"]["role"] == "admin"
    assert d["first_admin"] is True
    assert "access_token" in d


def test_signup_second_user_not_admin(app_client):
    _signup(app_client, "a@x.com")
    r = _signup(app_client, "b@x.com")
    assert r.get_json()["user"]["role"] == "user"
    assert "first_admin" not in r.get_json()


def test_signup_validation(app_client):
    assert app_client.post("/api/auth/signup", json={"email": "bad", "password": "correct-horse-99"}).status_code == 400
    assert app_client.post("/api/auth/signup", json={"email": "c@x.com", "password": "short"}).status_code == 400
    _signup(app_client, "d@x.com")
    r = app_client.post(
        "/api/auth/signup", json={"email": "d@x.com", "password": "correct-horse-99"}
    )
    assert r.status_code == 409


def test_login_and_wrong_password(app_client):
    _signup(app_client, "e@x.com", "correct-horse-99")
    r = app_client.post("/api/auth/login", json={"email": "e@x.com", "password": "correct-horse-99"})
    assert r.status_code == 200
    assert "access_token" in r.get_json()
    r2 = app_client.post("/api/auth/login", json={"email": "e@x.com", "password": "wrong-password-x"})
    assert r2.status_code == 401
    r3 = app_client.post("/api/auth/login", json={"email": "nobody@x.com", "password": "whatever-123"})
    assert r3.status_code == 401


def test_refresh_rotation_rejects_reuse(app_client):
    r = _signup(app_client, "f@x.com")
    refresh = r.get_json()["refresh_token"]
    r2 = app_client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    assert "access_token" in r2.get_json()
    # Old refresh token must now be dead (rotation).
    r3 = app_client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r3.status_code == 401


def test_logout_idempotent(app_client):
    r = _signup(app_client, "g@x.com")
    refresh = r.get_json()["refresh_token"]
    assert app_client.post("/api/auth/logout", json={"refresh_token": refresh}).status_code == 200
    # Second logout + garbage token both succeed (idempotent).
    assert app_client.post("/api/auth/logout", json={"refresh_token": refresh}).status_code == 200
    assert app_client.post("/api/auth/logout", json={"refresh_token": "garbage"}).status_code == 200
    # Logged-out refresh token is dead.
    assert app_client.post("/api/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_me(app_client):
    r = _signup(app_client, "h@x.com")
    access = r.get_json()["access_token"]
    m = app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert m.status_code == 200
    assert m.get_json()["user"]["email"] == "h@x.com"
    assert app_client.get("/api/auth/me").status_code == 401
    assert app_client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_password_reset_flow(app_client):
    _signup(app_client, "i@x.com", "correct-horse-99")
    # Always ok (no enumeration), mailed False without SMTP.
    r = app_client.post("/api/auth/password/request", json={"email": "i@x.com"})
    assert r.get_json() == {"ok": True, "mailed": False}
    r2 = app_client.post("/api/auth/password/request", json={"email": "ghost@x.com"})
    assert r2.get_json() == {"ok": True, "mailed": False}
    # Direct service-level confirm (mail path unconfigured in tests).
    from orbit.orbit.core.auth import service as svc

    Session = svc.get_session_factory() if hasattr(svc, "get_session_factory") else None
    from orbit.orbit.core.auth.store import get_session_factory
    from orbit.orbit.core.auth.models import User

    Session = get_session_factory()
    with Session() as db:
        user = db.query(User).filter_by(email="i@x.com").first()
        uid = user.id
    from orbit.orbit.core.auth.tokens import issue_reset

    token, _jti = issue_reset(uid)
    # Simulate the stored row exactly as request_reset would.
    import hashlib
    from datetime import datetime, timedelta, timezone
    from orbit.orbit.core.auth.models import PasswordReset

    with Session() as db:
        db.add(
            PasswordReset(
                jti=_jti,
                user_id=uid,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
        db.commit()
    r3 = app_client.post("/api/auth/password/reset", json={"token": token, "new_password": "new-horse-99-ok"})
    assert r3.status_code == 200, r3.get_data(as_text=True)
    # Old password dead, new works.
    assert app_client.post("/api/auth/login", json={"email": "i@x.com", "password": "correct-horse-99"}).status_code == 401
    assert app_client.post("/api/auth/login", json={"email": "i@x.com", "password": "new-horse-99-ok"}).status_code == 200
    # Token single-use.
    r4 = app_client.post("/api/auth/password/reset", json={"token": token, "new_password": "another-99-ok"})
    assert r4.status_code == 400


def test_oauth_link_and_login(app_client):
    from orbit.orbit.core.auth import service as svc

    svc.init_db_if_needed()  # mirrors the blueprint path (tables first)
    r = svc.oauth_login("google", {"subject": "google:123", "email": "oa@x.com", "name": "OA"})
    assert r["ok"] is True
    assert r["user"]["role"] == "admin"  # first user
    r2 = svc.oauth_login("google", {"subject": "google:123", "email": "oa@x.com", "name": "OA"})
    assert r2["user"]["id"] == r["user"]["id"]  # same account
    assert svc.oauth_login("google", {"subject": "", "email": "x@x.com"})["error"]
