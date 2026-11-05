"""BYOK provider-key vault regression tests (Milestone 1).

Hermetic: vault pointed at tmp dirs via monkeypatched module paths.
No network, no real keys (synthetic values only).
"""

import os


def _vault_with_tmp(tmp_path, monkeypatch):
    import orbit.orbit.core.provider_keys as pk

    vault_dir = tmp_path / "security"
    monkeypatch.setattr(pk, "_VAULT_DIR", vault_dir)
    monkeypatch.setattr(pk, "_VAULT_FILE", vault_dir / "provider_keys.json")
    monkeypatch.setattr(pk, "_KEY_FILE", vault_dir / ".vault.key")
    return pk.ProviderKeyVault()


def test_set_get_roundtrip(tmp_path, monkeypatch):
    pk = _vault_with_tmp(tmp_path, monkeypatch)
    r = pk.set_key("groq", "gsk_test_synthetic_key_12345")
    assert r["ok"] is True
    assert pk.get_key("groq") == "gsk_test_synthetic_key_12345"


def test_no_plaintext_on_disk(tmp_path, monkeypatch):
    pk = _vault_with_tmp(tmp_path, monkeypatch)
    pk.set_key("groq", "gsk_test_synthetic_key_12345")
    raw = (tmp_path / "security" / "provider_keys.json").read_text(encoding="utf-8")
    assert "gsk_test_synthetic_key_12345" not in raw


def test_rejects_bad_input(tmp_path, monkeypatch):
    pk = _vault_with_tmp(tmp_path, monkeypatch)
    assert pk.set_key("nope", "whatever-key-here")["ok"] is False
    assert pk.set_key("groq", "short")["ok"] is False
    assert pk.set_key("groq", "has space inside key xx")["ok"] is False
    assert pk.clear_key("nope")["ok"] is False


def test_clear_falls_back_to_env(tmp_path, monkeypatch):
    pk = _vault_with_tmp(tmp_path, monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env_synthetic_67890")
    assert pk.get_key("groq") == "gsk_env_synthetic_67890"
    pk.set_key("groq", "gsk_vault_synthetic_abcde")
    assert pk.get_key("groq") == "gsk_vault_synthetic_abcde"
    assert pk.clear_key("groq")["ok"] is True
    assert pk.get_key("groq") == "gsk_env_synthetic_67890"


def test_status_never_leaks_values(tmp_path, monkeypatch, caplog=None):
    pk = _vault_with_tmp(tmp_path, monkeypatch)
    pk.set_key("openrouter", "sk-or-test-synthetic-1234567890")
    st = pk.status()
    assert st["openrouter"]["configured"] is True
    assert st["openrouter"]["source"] == "vault"
    assert st["gemini"]["configured"] is False
    blob = str(st)
    assert "sk-or-test-synthetic" not in blob


def test_env_mirror_set(tmp_path, monkeypatch):
    pk = _vault_with_tmp(tmp_path, monkeypatch)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    pk.set_key("groq", "gsk_mirror_synthetic_xyz")
    assert os.environ.get("GROQ_API_KEY") == "gsk_mirror_synthetic_xyz"


def test_redacts_groq_keys():
    from orbit.orbit.core.secret_redactor import redact_text

    out = redact_text("key=gsk_abcdefghij1234567890 done")
    assert "gsk_abcdefghij1234567890" not in out
