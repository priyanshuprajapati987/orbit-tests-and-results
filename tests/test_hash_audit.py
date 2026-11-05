"""P2 hash audit — no MD5 in security-relevant paths (except allowlisted legacy).

Verifies:
  * smart_file_watcher.py uses SHA256 everywhere (was MD5 at 3 sites)
  * plugin_system.py comment matches reality (sha256)
  * encryption_manager.py is the only allowlisted legacy-MD5 file
  * dead_hand seal manifest persists + survives restart
  * vuln_scanner _SKIP_FILES includes encryption_manager
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "orbit" / "orbit" / "core"

# Files allowed to mention hashlib.md5 (legacy verify paths only).
_MD5_ALLOWLIST = {"encryption_manager.py"}


@pytest.fixture
def code_tree(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    (root / "orbit" / "core").mkdir(parents=True)
    (root / "orbit" / "core" / "engine.py").write_text("print('v1')\n", encoding="utf-8")
    (root / "orbit" / "core" / "util.py").write_text("X = 1\n", encoding="utf-8")
    (root / "ui").mkdir()
    (root / "ui" / "App.jsx").write_text("export default 1\n", encoding="utf-8")
    (root / "main.py").write_text("run()\n", encoding="utf-8")
    return root


def _py_files():
    return sorted(p for p in CORE.glob("*.py") if p.is_file())


class TestNoMD5InSecurityPaths:
    def test_smart_file_watcher_uses_sha256(self):
        text = (CORE / "smart_file_watcher.py").read_text(encoding="utf-8")
        assert "hashlib.md5" not in text
        assert "h.md5(" not in text
        assert "hashlib.sha256" in text

    def test_plugin_system_comment_matches_reality(self):
        text = (CORE / "plugin_system.py").read_text(encoding="utf-8")
        # stale comment said "path -> md5" while code used sha256
        assert "path -> sha256" in text
        assert "path \u2192 md5" not in text
        assert "hashlib.md5" not in text

    def test_dead_hand_uses_sha256_only(self):
        text = (CORE / "dead_hand.py").read_text(encoding="utf-8")
        assert "hashlib.md5" not in text
        assert "hashlib.sha256" in text

    def test_only_allowlisted_files_use_md5(self):
        offenders = []
        for path in _py_files():
            if path.name in _MD5_ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"hashlib\.md5\s*\(", text):
                offenders.append(path.name)
        assert offenders == [], f"unexpected hashlib.md5 usage in: {offenders}"

    def test_encryption_manager_md5_is_deprecated(self):
        text = (CORE / "encryption_manager.py").read_text(encoding="utf-8")
        assert "DEPRECATED" in text
        assert "deprecated" in text


class TestVulnScannerSkip:
    def test_encryption_manager_in_skip_files(self):
        text = (CORE / "vuln_scanner.py").read_text(encoding="utf-8")
        assert '"encryption_manager.py"' in text

    def test_security_tool_skips_still_present(self):
        from orbit.orbit.core.vuln_scanner import _SKIP_FILES
        for name in ("bugfixer.py", "vuln_scanner.py", "encryption_manager.py"):
            assert name in _SKIP_FILES


class TestRollbackBackupsGone:
    def test_no_rollback_backup_files_in_core(self):
        backups = list(CORE.glob("*.rollback_backup"))
        assert backups == [], f"stale rollback backups still present: {backups}"


class TestSealManifest:
    def _engine(self, tmp_path, code_tree):
        from orbit.orbit.core.dead_hand import DeadHand
        return DeadHand(
            store_dir=tmp_path / "sec",
            code_root=code_tree,
            armed=True,
            exit_on_trigger=False,
        )

    def test_seal_persists_manifest(self, tmp_path, code_tree):
        engine = self._engine(tmp_path, code_tree)
        engine.seal()
        manifest = Path(engine._store_dir) / "deadhand_manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["file_count"] == 4
        assert "sealed_at" in data
        assert data["code_root"] == str(code_tree)

    def test_manifest_loaded_on_monitor_start(self, tmp_path, code_tree):
        store = tmp_path / "sec"
        a = self._engine(store, code_tree)
        a.seal()
        a.stop_monitor()
        # new instance must restore baseline from manifest (not re-seal)
        b = self._engine(store, code_tree)
        assert b._baseline is None  # not yet loaded
        loaded = b._load_manifest()
        assert loaded is True
        assert b._baseline is not None
        assert len(b._baseline) == 4

    def test_manifest_mismatched_root_rejected(self, tmp_path, code_tree):
        store = tmp_path / "sec"
        a = self._engine(store, code_tree)
        a.seal()
        # different tree
        other = tmp_path / "other_app"
        other.mkdir()
        (other / "x.py").write_text("x\n", encoding="utf-8")
        b = self._engine(store, other)
        assert b._load_manifest() is False
        assert b._baseline is None

    def test_restart_detects_offline_tamper(self, tmp_path, code_tree):
        store = tmp_path / "sec"
        a = self._engine(store, code_tree)
        a.seal()
        a.stop_monitor()
        # tamper while "offline"
        (code_tree / "orbit" / "core" / "engine.py").write_text("evil\n", encoding="utf-8")
        b = self._engine(store, code_tree)
        b._load_manifest()
        assert b._baseline is not None
        changed = b._check_integrity()
        assert "orbit/core/engine.py" in changed
