"""Phase 14 - disk-read fault injection (read side; Phase 12 covered writes).

Injects corrupt/unreadable data files AT DISK and verifies every read path
degrades gracefully instead of raising:

  faults: binary garbage (UnicodeDecodeError), truncated JSON
          (JSONDecodeError), wrong-type JSON (dict where list expected),
          empty key file, vanished file after .exists() (TOCTOU)

Guarantees under test:
  - benchmark /battle/last + /ground-truth/last -> JSON 404, never 500
  - AutoUpdater boots with corrupt VERSION file (falls back to LOCAL_VERSION)
  - TokenManager regenerates binary/empty .token_secret, keeps valid ones
  - provider_keys._fernet() remints corrupt/empty vault keys (Fernet roundtrip)
  - PermissionManager treats corrupt/wrong-shape logs as empty, keeps lists
"""
import json

from flask import Flask


# ------------------------------------------------------------------ helpers
def _binary_garbage(path):
    """Invalid-UTF8 bytes -> UnicodeDecodeError on read_text/decode."""
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n\x00\xff\xfe\x00GARBAGE")


def _truncated_json(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"rounds": [{"winner": "JAR')  # cut mid-string


class _VanishedPath:
    """TOCTOU proxy: exists() is True, read raises FileNotFoundError."""

    def __init__(self, real_path):
        self._real = real_path

    def exists(self):
        return True

    def read_text(self, **kwargs):
        raise FileNotFoundError("file vanished after exists() check")

    def __str__(self):
        return str(self._real)


def _client_with_benchmark_bp():
    app = Flask(__name__)
    app.config["TESTING"] = True
    from orbit.orbit.core.benchmark_bp import benchmark_bp

    app.register_blueprint(benchmark_bp)
    return app.test_client()


# ------------------------------------------------- benchmark routes (TOCTOU
# + corrupt data: user-written battle/GT logs live on disk between runs)
def test_battle_last_corrupt_json_returns_404(monkeypatch):
    import orbit.orbit.core.battle as battle_mod

    real = battle_mod.DEFAULT_BATTLE_FILE
    real.parent.mkdir(parents=True, exist_ok=True)
    _truncated_json(real)
    monkeypatch.setattr(battle_mod, "DEFAULT_BATTLE_FILE", real)
    try:
        resp = _client_with_benchmark_bp().get("/api/benchmark/battle/last")
        assert resp.status_code == 404
        assert "error" in resp.get_json()
    finally:
        real.unlink(missing_ok=True)


def test_battle_last_binary_file_returns_404(monkeypatch):
    import orbit.orbit.core.battle as battle_mod

    real = battle_mod.DEFAULT_BATTLE_FILE
    real.parent.mkdir(parents=True, exist_ok=True)
    _binary_garbage(real)
    monkeypatch.setattr(battle_mod, "DEFAULT_BATTLE_FILE", real)
    try:
        resp = _client_with_benchmark_bp().get("/api/benchmark/battle/last")
        assert resp.status_code == 404
    finally:
        real.unlink(missing_ok=True)


def test_battle_last_vanished_after_exists_returns_404(monkeypatch):
    """TOCTOU: file deleted between .exists() and .read_text()."""
    import orbit.orbit.core.battle as battle_mod

    monkeypatch.setattr(
        battle_mod, "DEFAULT_BATTLE_FILE", _VanishedPath(battle_mod.DEFAULT_BATTLE_FILE)
    )
    resp = _client_with_benchmark_bp().get("/api/benchmark/battle/last")
    assert resp.status_code == 404


def test_battle_last_valid_still_serves_payload(monkeypatch, tmp_path):
    """Control: a healthy battle log must still round-trip as JSON."""
    import orbit.orbit.core.battle as battle_mod

    healthy = tmp_path / "battle_ok.json"
    healthy.write_text(json.dumps({"rounds": [], "count": 0}), encoding="utf-8")
    monkeypatch.setattr(battle_mod, "DEFAULT_BATTLE_FILE", healthy)
    resp = _client_with_benchmark_bp().get("/api/benchmark/battle/last")
    assert resp.status_code == 200
    assert resp.get_json() == {"rounds": [], "count": 0}


def test_ground_truth_last_corrupt_json_returns_404(monkeypatch, tmp_path):
    import orbit.orbit.core.ground_truth as gt_mod

    corrupt = tmp_path / "gt_corrupt.json"
    _truncated_json(corrupt)
    monkeypatch.setattr(gt_mod, "DEFAULT_GT_FILE", corrupt)
    resp = _client_with_benchmark_bp().get("/api/benchmark/ground-truth/last")
    assert resp.status_code == 404


def test_ground_truth_last_binary_returns_404(monkeypatch, tmp_path):
    import orbit.orbit.core.ground_truth as gt_mod

    binary = tmp_path / "gt_binary.json"
    _binary_garbage(binary)
    monkeypatch.setattr(gt_mod, "DEFAULT_GT_FILE", binary)
    resp = _client_with_benchmark_bp().get("/api/benchmark/ground-truth/last")
    assert resp.status_code == 404


# ------------------------------------------------------------- auto_updater
def test_auto_updater_binary_version_file_falls_back(monkeypatch, tmp_path):
    """Binary VERSION file used to crash AutoUpdater.__init__ (boot crash)."""
    import orbit.orbit.core.auto_updater as au

    monkeypatch.setattr(au, "DATA_DIR", tmp_path / "updater")
    monkeypatch.setattr(au, "BACKUP_DIR", tmp_path / "updater" / "backups")
    version_file = tmp_path / "VERSION"
    _binary_garbage(version_file)
    monkeypatch.setattr(au, "VERSION_FILE", version_file)

    updater = au.AutoUpdater()  # must not raise
    assert updater._version == au.LOCAL_VERSION


def test_auto_updater_empty_version_file_falls_back(monkeypatch, tmp_path):
    import orbit.orbit.core.auto_updater as au

    monkeypatch.setattr(au, "DATA_DIR", tmp_path / "updater")
    monkeypatch.setattr(au, "BACKUP_DIR", tmp_path / "updater" / "backups")
    version_file = tmp_path / "VERSION"
    version_file.write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(au, "VERSION_FILE", version_file)

    updater = au.AutoUpdater()
    assert updater._version == au.LOCAL_VERSION


def test_auto_updater_valid_version_file_used(monkeypatch, tmp_path):
    import orbit.orbit.core.auto_updater as au

    monkeypatch.setattr(au, "DATA_DIR", tmp_path / "updater")
    monkeypatch.setattr(au, "BACKUP_DIR", tmp_path / "updater" / "backups")
    version_file = tmp_path / "VERSION"
    version_file.write_text("9.9.9-test\n", encoding="utf-8")
    monkeypatch.setattr(au, "VERSION_FILE", version_file)

    updater = au.AutoUpdater()
    assert updater._version == "9.9.9-test"


# ------------------------------------------------------------- token_manager
def test_token_manager_binary_secret_regenerates(tmp_path):
    """Binary .token_secret used to raise UnicodeDecodeError at boot."""
    storage = tmp_path / "token_manager.json"
    secret_file = tmp_path / ".token_secret"
    _binary_garbage(secret_file)

    from orbit.orbit.core.token_manager import TokenManager

    tm = TokenManager(storage_file=str(storage))  # must not raise
    assert tm.secret_key
    # Regenerated secret must be a readable hex string on disk now
    on_disk = secret_file.read_text(encoding="utf-8").strip()
    assert on_disk == tm.secret_key
    assert all(c in "0123456789abcdef" for c in on_disk)


def test_token_manager_empty_secret_regenerates(tmp_path):
    storage = tmp_path / "token_manager.json"
    (tmp_path / ".token_secret").write_text("", encoding="utf-8")

    from orbit.orbit.core.token_manager import TokenManager

    tm = TokenManager(storage_file=str(storage))
    assert tm.secret_key


def test_token_manager_valid_secret_reused(tmp_path):
    storage = tmp_path / "token_manager.json"
    (tmp_path / ".token_secret").write_text("a" * 64, encoding="utf-8")

    from orbit.orbit.core.token_manager import TokenManager

    tm = TokenManager(storage_file=str(storage))
    assert tm.secret_key == "a" * 64


# -------------------------------------------------------------- provider_keys
def test_vault_key_empty_file_reminted(tmp_path, monkeypatch):
    import orbit.orbit.core.provider_keys as pk

    monkeypatch.setattr(pk, "_VAULT_DIR", tmp_path)
    key_file = tmp_path / ".vault.key"
    key_file.write_bytes(b"")

    fernet = pk._fernet()  # must not raise
    token = fernet.encrypt(b"hello")
    assert fernet.decrypt(token) == b"hello"


def test_vault_key_binary_garbage_reminted(tmp_path, monkeypatch):
    """Binary junk .vault.key -> Fernet() constructor used to raise binascii."""
    import orbit.orbit.core.provider_keys as pk

    monkeypatch.setattr(pk, "_VAULT_DIR", tmp_path)
    key_file = tmp_path / ".vault.key"
    key_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff NOT A FERNET KEY")

    fernet = pk._fernet()
    token = fernet.encrypt(b"secret")
    assert fernet.decrypt(token) == b"secret"


def test_vault_key_valid_key_untouched(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    import orbit.orbit.core.provider_keys as pk

    monkeypatch.setattr(pk, "_VAULT_DIR", tmp_path)
    key = Fernet.generate_key()
    (tmp_path / ".vault.key").write_bytes(key)

    fernet = pk._fernet()
    assert fernet.decrypt(fernet.encrypt(b"x")) == b"x"
    # Key file must NOT have been rewritten
    assert (tmp_path / ".vault.key").read_bytes() == key


# --------------------------------------------------------------- permission
def test_permission_corrupt_log_treated_as_empty(tmp_path):
    log_file = tmp_path / "permission_log.json"
    _truncated_json(log_file)

    from orbit.orbit.core.permission import PermissionManager

    pm = PermissionManager(log_file=str(log_file))
    # Reading via public path must not raise
    result = pm.approve_action("delete_file", reason="corrupt log test")
    assert result["resolved"] == 0
    pending = pm.get_pending_approvals()
    assert pending == []


def test_permission_wrong_shape_log_treated_as_empty(tmp_path):
    """Valid JSON but dict instead of list (Phase-12 class resurfacing)."""
    log_file = tmp_path / "permission_log.json"
    log_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    from orbit.orbit.core.permission import PermissionManager

    pm = PermissionManager(log_file=str(log_file))
    pending = pm.get_pending_approvals()
    assert pending == []


def test_permission_binary_log_treated_as_empty(tmp_path):
    log_file = tmp_path / "permission_log.json"
    _binary_garbage(log_file)

    from orbit.orbit.core.permission import PermissionManager

    pm = PermissionManager(log_file=str(log_file))
    entries = pm._read_log_unlocked()
    assert entries == []


def test_permission_valid_list_still_reads(tmp_path):
    log_file = tmp_path / "permission_log.json"
    log_file.write_text(
        json.dumps([{"action": "delete_file", "level": "high", "timestamp": "t"}]),
        encoding="utf-8",
    )

    from orbit.orbit.core.permission import PermissionManager

    pm = PermissionManager(log_file=str(log_file))
    entries = pm._read_log_unlocked()
    assert len(entries) == 1
    assert entries[0]["action"] == "delete_file"
