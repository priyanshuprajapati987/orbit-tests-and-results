"""
Unit tests for orbit.orbit.core.token_manager (previously 0% covered).

Covers token generation, signature validation, expiry, refresh, revocation,
cleanup and statistics.
"""

import base64
import json

import pytest

from orbit.orbit.core import token_manager as tm
from orbit.orbit.core.token_manager import TokenManager


@pytest.fixture
def manager(tmp_path):
    return TokenManager(storage_file=str(tmp_path / "tokens.json"),
                        secret_key="test-secret")


def _payload_of(token):
    return json.loads(base64.b64decode(token.split(".")[0].encode()).decode())


class TestGenerate:
    def test_token_has_payload_and_signature(self, manager):
        token = manager.generate_token("alice")
        assert token.count(".") == 1
        assert _payload_of(token)["user_id"] == "alice"

    def test_permissions_and_metadata_round_trip(self, manager):
        token = manager.generate_token("alice", permissions=["read", "write"],
                                       metadata={"ip": "127.0.0.1"})
        payload = _payload_of(token)
        assert payload["permissions"] == ["read", "write"]
        assert payload["metadata"] == {"ip": "127.0.0.1"}

    def test_token_recorded_as_active(self, manager):
        manager.generate_token("alice")
        assert manager.get_statistics()["active_tokens"] == 1

    def test_stored_record_only_keeps_prefix(self, manager):
        token = manager.generate_token("alice")
        record = next(iter(manager.tokens.values()))
        assert record["token_prefix"] == token[:20] + "..."
        assert token not in json.dumps(manager.tokens)

    def test_random_secret_key_generated_when_missing(self, tmp_path):
        m = TokenManager(storage_file=str(tmp_path / "t.json"))
        assert len(m.secret_key) == 64


class TestValidate:
    def test_valid_token(self, manager):
        result = manager.validate_token(manager.generate_token("alice", ["read"]))
        assert result["valid"] is True
        assert result["user_id"] == "alice"
        assert result["permissions"] == ["read"]

    def test_metadata_returned(self, manager):
        token = manager.generate_token("alice", metadata={"role": "admin"})
        assert manager.validate_token(token)["metadata"] == {"role": "admin"}

    def test_empty_token_rejected(self, manager):
        assert manager.validate_token("")["error"] == "Invalid token format"

    def test_token_without_separator_rejected(self, manager):
        assert manager.validate_token("garbage")["error"] == "Invalid token format"

    def test_token_with_too_many_parts_rejected(self, manager):
        assert manager.validate_token("a.b.c")["error"] == "Invalid token format"

    def test_tampered_signature_rejected(self, manager):
        token = manager.generate_token("alice")
        data, _ = token.split(".")
        result = manager.validate_token(f"{data}.{'0' * 64}")
        assert result == {"valid": False, "error": "Invalid signature"}

    def test_tampered_payload_rejected(self, manager):
        token = manager.generate_token("alice")
        payload = _payload_of(token)
        payload["user_id"] = "attacker"
        forged = base64.b64encode(
            json.dumps(payload, sort_keys=True).encode()).decode()
        result = manager.validate_token(f"{forged}.{token.split('.')[1]}")
        assert result["valid"] is False

    def test_token_from_other_secret_rejected(self, tmp_path):
        other = TokenManager(storage_file=str(tmp_path / "a.json"),
                             secret_key="other-secret")
        mine = TokenManager(storage_file=str(tmp_path / "b.json"),
                            secret_key="my-secret")
        assert mine.validate_token(other.generate_token("alice"))["valid"] is False

    def test_expired_token_rejected(self, manager):
        token = manager.generate_token("alice", expires_in_hours=-1)
        assert manager.validate_token(token)["error"] == "Token expired"

    def test_undecodable_payload_reports_error(self, manager):
        result = manager.validate_token("!!!!.signature")
        assert result["valid"] is False
        assert result["error"]


class TestRevoke:
    def test_revoked_token_is_invalid(self, manager):
        token = manager.generate_token("alice")
        assert manager.revoke_token(token) is True
        assert manager.validate_token(token)["error"] == "Token revoked"

    def test_revoke_unknown_token_returns_false(self, manager):
        assert manager.revoke_token("unknown.token") is False

    def test_revoke_all_user_tokens(self, manager):
        manager.generate_token("alice")
        manager.generate_token("alice")
        manager.generate_token("bob")
        assert manager.revoke_all_user_tokens("alice") == 2
        assert manager.get_statistics()["active_tokens"] == 1

    def test_revoke_all_is_idempotent(self, manager):
        manager.generate_token("alice")
        manager.revoke_all_user_tokens("alice")
        assert manager.revoke_all_user_tokens("alice") == 0


class TestRefresh:
    def test_refresh_returns_new_token(self, manager):
        token = manager.generate_token("alice", ["read"])
        new_token = manager.refresh_token(token)
        assert new_token != token
        assert manager.validate_token(new_token)["user_id"] == "alice"

    def test_refresh_preserves_permissions(self, manager):
        token = manager.generate_token("alice", ["read", "write"])
        refreshed = manager.refresh_token(token)
        assert manager.validate_token(refreshed)["permissions"] == ["read", "write"]

    def test_refresh_revokes_old_token(self, manager):
        token = manager.generate_token("alice")
        manager.refresh_token(token)
        assert manager.validate_token(token)["error"] == "Token revoked"

    def test_refresh_extends_expiry(self, manager):
        token = manager.generate_token("alice", expires_in_hours=1)
        refreshed = manager.refresh_token(token, extends_hours=48)
        assert _payload_of(refreshed)["expires_at"] > _payload_of(token)["expires_at"]

    def test_refresh_invalid_token_returns_none(self, manager):
        assert manager.refresh_token("garbage") is None

    def test_refresh_expired_token_returns_none(self, manager):
        token = manager.generate_token("alice", expires_in_hours=-1)
        assert manager.refresh_token(token) is None


class TestQueriesAndCleanup:
    def test_get_user_tokens_only_returns_that_user(self, manager):
        manager.generate_token("alice")
        manager.generate_token("bob")
        tokens = manager.get_user_tokens("alice")
        assert len(tokens) == 1
        assert tokens[0]["is_active"] is True

    def test_get_user_tokens_unknown_user(self, manager):
        assert manager.get_user_tokens("ghost") == []

    def test_cleanup_expired_removes_expired_records(self, manager):
        manager.generate_token("alice", expires_in_hours=-1)
        manager.generate_token("bob", expires_in_hours=24)
        manager.cleanup_expired()
        stats = manager.get_statistics()
        assert stats["total_tokens"] == 1
        assert stats["unique_users"] == 1

    def test_cleanup_ignores_unparsable_expiry(self, manager):
        manager.generate_token("alice")
        next(iter(manager.tokens.values()))["expires_at"] = "not-a-date"
        manager.cleanup_expired()
        assert manager.get_statistics()["total_tokens"] == 1

    def test_statistics(self, manager):
        token = manager.generate_token("alice")
        manager.generate_token("bob")
        manager.revoke_token(token)
        stats = manager.get_statistics()
        assert stats["total_tokens"] == 2
        assert stats["active_tokens"] == 1
        assert stats["revoked_tokens"] == 1
        assert stats["unique_users"] == 2


class TestPersistence:
    def test_records_survive_reload(self, tmp_path):
        path = str(tmp_path / "tokens.json")
        token = TokenManager(storage_file=path,
                             secret_key="s").generate_token("alice")
        reloaded = TokenManager(storage_file=path, secret_key="s")
        assert reloaded.validate_token(token)["valid"] is True
        assert reloaded.get_statistics()["total_tokens"] == 1

    def test_revocations_survive_reload(self, tmp_path):
        path = str(tmp_path / "tokens.json")
        first = TokenManager(storage_file=path, secret_key="s")
        token = first.generate_token("alice")
        first.revoke_token(token)
        reloaded = TokenManager(storage_file=path, secret_key="s")
        assert reloaded.validate_token(token)["error"] == "Token revoked"

    def test_corrupt_storage_file_is_tolerated(self, tmp_path):
        path = tmp_path / "tokens.json"
        path.write_text("{not json", encoding="utf-8")
        m = TokenManager(storage_file=str(path), secret_key="s")
        assert m.get_statistics()["total_tokens"] == 0


class TestModuleLevelApi:
    @pytest.fixture(autouse=True)
    def _isolated_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tm, "_token_manager",
                            TokenManager(storage_file=str(tmp_path / "t.json"),
                                         secret_key="s"))

    def test_get_token_manager_is_singleton(self):
        assert tm.get_token_manager() is tm.get_token_manager()

    def test_generate_and_validate(self):
        assert tm.validate_token(tm.generate_token("alice"))["user_id"] == "alice"

    def test_refresh_and_revoke(self):
        token = tm.refresh_token(tm.generate_token("alice"))
        assert tm.revoke_token(token) is True
        assert tm.get_statistics()["active_tokens"] == 0
