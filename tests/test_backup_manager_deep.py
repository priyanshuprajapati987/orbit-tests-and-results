"""Deep tests for orbit/orbit/core/backup_manager.py (Loop 23/4)."""

import json
import os
import shutil
import threading
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit.core import backup_manager as bm


class BackupTypeTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(bm.BackupType.FULL, "full")
        self.assertEqual(bm.BackupType.INCREMENTAL, "incremental")
        self.assertEqual(bm.BackupType.DIFFERENTIAL, "differential")


class InitLoadTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "backup_manager.json"
        backup_dir = d / "backups"
        return storage, backup_dir

    def test_init_creates_dirs(self):
        storage, backup_dir = self._tmp()
        with mock.patch("pathlib.Path.mkdir") as mk:
            m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        # _ensure_directories calls mkdir twice
        self.assertGreaterEqual(mk.call_count, 2)

    def test_init_loads_existing(self):
        storage, backup_dir = self._tmp()
        storage.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        storage.write_text(json.dumps({
            "backups": [{"id": "b1"}],
            "configs": {"custom": {"name": "C"}},
            "stats": {"total": 5, "successful": 4, "failed": 1},
        }), encoding="utf-8")
        m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        self.assertEqual(m.backups, [{"id": "b1"}])
        self.assertIn("custom", m.backup_configs)
        self.assertEqual(m.backup_stats, {"total": 5, "successful": 4, "failed": 1})

    def test_init_load_corrupt(self):
        storage, backup_dir = self._tmp()
        storage.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        storage.write_text("{bad", encoding="utf-8")
        with mock.patch.object(bm, "logger") as lg:
            m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        lg.error.assert_called_once()
        # defaults still set
        self.assertIn("orbit_data", m.backup_configs)

    def test_init_load_missing(self):
        storage, backup_dir = self._tmp()
        backup_dir.mkdir(parents=True, exist_ok=True)
        m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        self.assertEqual(m.backups, [])

    def test_setup_default_configs(self):
        storage, backup_dir = self._tmp()
        backup_dir.mkdir(parents=True, exist_ok=True)
        m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        self.assertIn("orbit_data", m.backup_configs)
        self.assertIn("orbit_config", m.backup_configs)
        self.assertEqual(m.backup_configs["orbit_data"]["name"], "ORBIT Data")
        self.assertEqual(m.backup_configs["orbit_data"]["retention_days"], 30)
        self.assertEqual(m.backup_configs["orbit_config"]["retention_days"], 90)

    def test_setup_does_not_overwrite_existing(self):
        storage, backup_dir = self._tmp()
        storage.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        storage.write_text(json.dumps({
            "backups": [],
            "configs": {"orbit_data": {"name": "Custom"}},
            "stats": {"total": 0, "successful": 0, "failed": 0},
        }), encoding="utf-8")
        m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        self.assertEqual(m.backup_configs["orbit_data"]["name"], "Custom")

    def test_save_success(self):
        storage, backup_dir = self._tmp()
        backup_dir.mkdir(parents=True, exist_ok=True)
        m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        m.backups = [{"id": "b1"}]
        m._save_data()
        self.assertTrue(storage.exists())
        data = json.loads(storage.read_text("utf-8"))
        self.assertEqual(data["backups"], [{"id": "b1"}])

    def test_save_failure_logged(self):
        storage, backup_dir = self._tmp()
        backup_dir.mkdir(parents=True, exist_ok=True)
        m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        with mock.patch("builtins.open", side_effect=OSError("boom")), \
                mock.patch.object(bm, "logger") as lg:
            m._save_data()
        lg.error.assert_called_once()


class CreateBackupTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "backup_manager.json"
        backup_dir = d / "backups"
        # create source files
        (d / "orbit").mkdir(exist_ok=True)
        (d / "orbit" / "x.py").write_text("x", encoding="utf-8")
        (d / "config").mkdir(exist_ok=True)
        (d / "config" / "c.json").write_text("{}", encoding="utf-8")
        (d / "requirements.txt").write_text("req", encoding="utf-8")
        with mock.patch("orbit.orbit.core.backup_manager.app_root", return_value=d), \
                mock.patch("orbit.orbit.core.backup_manager.data_dir", return_value=d / "data"):
            m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        return m, d, backup_dir

    def test_unknown_config(self):
        m, d, bd = self._make()
        r = m.create_backup("nope")
        self.assertEqual(r, {"error": "Config not found: nope"})

    def test_success(self):
        m, d, bd = self._make()
        with mock.patch.object(m, "_calculate_hash", return_value="hash1"):
            r = m.create_backup("orbit_data", bm.BackupType.FULL)
        self.assertEqual(r["config_name"], "orbit_data")
        self.assertEqual(r["type"], "full")
        self.assertEqual(r["status"], "completed")
        self.assertTrue(r["size_bytes"] > 0)
        self.assertEqual(r["hash"], "hash1")
        self.assertIn("timestamp", r)
        self.assertIn("path", r)
        # persisted
        self.assertEqual(m.backup_stats["total"], 1)
        self.assertEqual(m.backup_stats["successful"], 1)
        self.assertEqual(len(m.backups), 1)
        # backup file exists
        self.assertTrue(Path(r["path"]).exists())

    def test_exception_returns_error(self):
        m, d, bd = self._make()
        # make _add_directory_to_zip raise
        with mock.patch.object(m, "_add_directory_to_zip", side_effect=RuntimeError("boom")), \
                mock.patch.object(bm, "logger") as lg:
            r = m.create_backup("orbit_data")
        self.assertEqual(r["status"] if "status" in r else None, None)
        self.assertIn("error", r)
        self.assertEqual(r["error"], "boom")
        self.assertEqual(m.backup_stats["failed"], 1)
        lg.error.assert_called_once()

    def test_backup_type_default(self):
        m, d, bd = self._make()
        with mock.patch.object(m, "_calculate_hash", return_value="h"):
            r = m.create_backup("orbit_data")
        self.assertEqual(r["type"], "full")

    def test_nonexistent_source_skipped(self):
        m, d, bd = self._make()
        # add a config with nonexistent source
        m.backup_configs["empty"] = {"name": "E", "source_paths": [str(d / "nope")],
                                     "exclude_patterns": [], "retention_days": 30}
        with mock.patch.object(m, "_calculate_hash", return_value="h"):
            r = m.create_backup("empty")
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["size_bytes"], 22)  # empty zip ~22 bytes


class AddFileToZipTests(unittest.TestCase):
    def test(self):
        import tempfile, zipfile
        d = Path(tempfile.mkdtemp())
        src = d / "f.txt"
        src.write_text("hi", encoding="utf-8")
        zip_path = Path(tempfile.gettempdir()) / "out.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            m = bm.BackupManager.__new__(bm.BackupManager)
            m._add_file_to_zip(zf, src, d)
        with zipfile.ZipFile(zip_path) as zf:
            self.assertEqual(zf.namelist(), ["f.txt"])


class AddDirectoryToZipTests(unittest.TestCase):
    def test_excludes_patterns(self):
        import tempfile, zipfile
        d = Path(tempfile.mkdtemp())
        (d / "a.py").write_text("x", encoding="utf-8")
        (d / "b.pyc").write_text("x", encoding="utf-8")
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "c.pyc").write_text("x", encoding="utf-8")
        (d / "sub").mkdir()
        (d / "sub" / "d.txt").write_text("x", encoding="utf-8")
        zip_path = Path(tempfile.gettempdir()) / "out.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            m = bm.BackupManager.__new__(bm.BackupManager)
            m._add_directory_to_zip(zf, d, ["*.pyc", "__pycache__"])
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        self.assertTrue(any(n.endswith("a.py") for n in names))
        self.assertTrue(any(n.endswith("d.txt") for n in names))
        # pyc excluded
        self.assertFalse(any(n.endswith(".pyc") for n in names))
        # __pycache__ excluded
        self.assertFalse(any("__pycache__" in n for n in names))

    def test_no_excludes(self):
        import tempfile, zipfile
        d = Path(tempfile.mkdtemp())
        (d / "a.py").write_text("x", encoding="utf-8")
        zip_path = Path(tempfile.gettempdir()) / "out.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            m = bm.BackupManager.__new__(bm.BackupManager)
            m._add_directory_to_zip(zf, d, [])
        with zipfile.ZipFile(zip_path) as zf:
            self.assertTrue(any(n.endswith("a.py") for n in zf.namelist()))


class CalculateHashTests(unittest.TestCase):
    def test(self):
        import tempfile, hashlib
        d = Path(tempfile.mkdtemp())
        f = d / "f.txt"
        f.write_text("hello", encoding="utf-8")
        m = bm.BackupManager.__new__(bm.BackupManager)
        self.assertEqual(m._calculate_hash(f), hashlib.sha256(b"hello").hexdigest())


class RestoreBackupTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "backup_manager.json"
        backup_dir = d / "backups"
        storage.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.backup_manager.app_root", return_value=d), \
                mock.patch("orbit.orbit.core.backup_manager.data_dir", return_value=d / "data"):
            m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        return m, d, backup_dir, storage

    def test_not_found(self):
        m, d, bd, st = self._make()
        self.assertEqual(m.restore_backup("nope"), {"error": "Backup not found: nope"})

    def test_file_missing(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "b1", "path": str(bd / "missing.zip")}]
        self.assertEqual(m.restore_backup("b1"), {"error": "Backup file not found"})

    def test_success(self):
        m, d, bd, st = self._make()
        # create a backup zip
        bp = bd / "b1.zip"
        bd.mkdir(parents=True, exist_ok=True)
        import zipfile
        with zipfile.ZipFile(bp, "w") as zf:
            zf.writestr("f.txt", "restored")
        m.backups = [{"id": "b1", "path": str(bp)}]
        restore_to = d / "restore"
        with mock.patch("orbit.orbit.core.safe_archive.safe_extract_zip") as se:
            r = m.restore_backup("b1", str(restore_to))
        self.assertEqual(r, {"status": "restored", "backup_id": "b1", "path": str(restore_to)})
        se.assert_called_once_with(bp, str(restore_to))

    def test_success_default_restore_path(self):
        m, d, bd, st = self._make()
        bp = bd / "b1.zip"
        bd.mkdir(parents=True, exist_ok=True)
        import zipfile
        with zipfile.ZipFile(bp, "w") as zf:
            zf.writestr("f.txt", "x")
        m.backups = [{"id": "b1", "path": str(bp)}]
        with mock.patch("orbit.orbit.core.safe_archive.safe_extract_zip"), \
                mock.patch("orbit.orbit.core.backup_manager.app_root", return_value=d):
            r = m.restore_backup("b1")
        self.assertEqual(r["path"], str(d))

    def test_exception(self):
        m, d, bd, st = self._make()
        bp = bd / "b1.zip"
        bd.mkdir(parents=True, exist_ok=True)
        bp.write_text("x", encoding="utf-8")
        m.backups = [{"id": "b1", "path": str(bp)}]
        with mock.patch("orbit.orbit.core.safe_archive.safe_extract_zip",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(bm, "logger") as lg:
            r = m.restore_backup("b1")
        self.assertEqual(r, {"error": "boom"})
        lg.error.assert_called_once()


class VerifyBackupTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "backup_manager.json"
        backup_dir = d / "backups"
        storage.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.backup_manager.app_root", return_value=d), \
                mock.patch("orbit.orbit.core.backup_manager.data_dir", return_value=d / "data"):
            m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        return m, d, backup_dir, storage

    def test_not_found(self):
        m, d, bd, st = self._make()
        self.assertEqual(m.verify_backup("nope"), {"error": "Backup not found: nope"})

    def test_file_missing(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "b1", "path": str(bd / "missing.zip"), "hash": "h"}]
        self.assertEqual(m.verify_backup("b1"), {"status": "invalid", "error": "File not found"})

    def test_valid(self):
        m, d, bd, st = self._make()
        bp = bd / "b1.zip"
        bp.write_text("x", encoding="utf-8")
        import hashlib
        h = hashlib.sha256(b"x").hexdigest()
        m.backups = [{"id": "b1", "path": str(bp), "hash": h}]
        with mock.patch.object(m, "_calculate_hash", return_value=h):
            self.assertEqual(m.verify_backup("b1"), {"status": "valid", "backup_id": "b1"})

    def test_corrupted(self):
        m, d, bd, st = self._make()
        bp = bd / "b1.zip"
        bp.write_text("x", encoding="utf-8")
        m.backups = [{"id": "b1", "path": str(bp), "hash": "other"}]
        with mock.patch.object(m, "_calculate_hash", return_value="different"):
            self.assertEqual(m.verify_backup("b1"), {"status": "corrupted", "backup_id": "b1"})

    def test_exception(self):
        m, d, bd, st = self._make()
        bp = bd / "b1.zip"
        bp.write_text("x", encoding="utf-8")
        m.backups = [{"id": "b1", "path": str(bp), "hash": "h"}]
        with mock.patch.object(m, "_calculate_hash", side_effect=RuntimeError("boom")):
            self.assertEqual(m.verify_backup("b1"), {"status": "error", "error": "boom"})


class ListDeleteBackupsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "backup_manager.json"
        backup_dir = d / "backups"
        storage.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.backup_manager.app_root", return_value=d), \
                mock.patch("orbit.orbit.core.backup_manager.data_dir", return_value=d / "data"):
            m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        return m, d, backup_dir, storage

    def test_list_all(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "b1", "config_name": "c1"}, {"id": "b2", "config_name": "c2"}]
        self.assertEqual(len(m.list_backups()), 2)

    def test_list_filtered(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "b1", "config_name": "c1"}, {"id": "b2", "config_name": "c2"}]
        r = m.list_backups("c1")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["id"], "b1")

    def test_list_returns_copy(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "b1"}]
        r = m.list_backups()
        self.assertIsNot(r, m.backups)
        self.assertEqual(len(r), 1)

    def test_delete_success(self):
        m, d, bd, st = self._make()
        bp = bd / "b1.zip"
        bp.write_text("x", encoding="utf-8")
        m.backups = [{"id": "b1", "path": str(bp)}]
        self.assertTrue(m.delete_backup("b1"))
        self.assertEqual(m.backups, [])
        self.assertFalse(bp.exists())

    def test_delete_missing(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "b1", "path": "/tmp/x.zip"}]
        self.assertFalse(m.delete_backup("b2"))

    def test_delete_file_missing_ok(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "b1", "path": str(bd / "missing.zip")}]
        self.assertTrue(m.delete_backup("b1"))
        self.assertEqual(m.backups, [])

    def test_cleanup_old_backups(self):
        m, d, bd, st = self._make()
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        recent_date = datetime.now().isoformat()
        bp_old = bd / "old.zip"
        bp_old.write_text("x", encoding="utf-8")
        bp_new = bd / "new.zip"
        bp_new.write_text("x", encoding="utf-8")
        m.backups = [
            {"id": "old", "timestamp": old_date, "path": str(bp_old)},
            {"id": "new", "timestamp": recent_date, "path": str(bp_new)},
        ]
        m.cleanup_old_backups(30)
        self.assertEqual(len(m.backups), 1)
        self.assertEqual(m.backups[0]["id"], "new")
        self.assertFalse(bp_old.exists())
        self.assertTrue(bp_new.exists())

    def test_cleanup_no_old(self):
        m, d, bd, st = self._make()
        recent_date = datetime.now().isoformat()
        m.backups = [{"id": "new", "timestamp": recent_date, "path": "/tmp/x.zip"}]
        m.cleanup_old_backups(30)
        self.assertEqual(len(m.backups), 1)

    def test_cleanup_invalid_date_skipped(self):
        m, d, bd, st = self._make()
        m.backups = [{"id": "bad", "timestamp": "not-a-date", "path": "/tmp/x.zip"}]
        m.cleanup_old_backups(30)
        self.assertEqual(len(m.backups), 1)

    def test_cleanup_logs(self):
        m, d, bd, st = self._make()
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        m.backups = [{"id": "old", "timestamp": old_date, "path": "/tmp/x.zip"}]
        with mock.patch.object(bm, "logger") as lg:
            m.cleanup_old_backups(30)
        lg.info.assert_called_once()


class GetStatisticsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        storage = d / "backup_manager.json"
        backup_dir = d / "backups"
        storage.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.backup_manager.app_root", return_value=d), \
                mock.patch("orbit.orbit.core.backup_manager.data_dir", return_value=d / "data"):
            m = bm.BackupManager(storage_file=str(storage), backup_dir=str(backup_dir))
        return m, d, backup_dir, storage

    def test_empty(self):
        m, d, bd, st = self._make()
        s = m.get_statistics()
        self.assertEqual(s["total_backups"], 0)
        self.assertEqual(s["total_size_bytes"], 0)
        self.assertEqual(s["total_size_mb"], 0.0)
        self.assertEqual(s["by_config"], {})
        self.assertEqual(s["stats"], {"total": 0, "successful": 0, "failed": 0})
        self.assertEqual(s["backup_dir"], str(bd))

    def test_with_backups(self):
        m, d, bd, st = self._make()
        m.backups = [
            {"id": "b1", "config_name": "c1", "size_bytes": 1024 * 1024},
            {"id": "b2", "config_name": "c1", "size_bytes": 1024 * 1024},
            {"id": "b3", "config_name": "c2", "size_bytes": 0},
        ]
        s = m.get_statistics()
        self.assertEqual(s["total_backups"], 3)
        self.assertEqual(s["total_size_bytes"], 2 * 1024 * 1024)
        self.assertEqual(s["total_size_mb"], 2.0)
        self.assertEqual(s["by_config"], {"c1": 2, "c2": 1})


class ModuleLevelTests(unittest.TestCase):
    def test_get_backup_manager_singleton(self):
        bm._backup_manager = None
        a = bm.get_backup_manager()
        b = bm.get_backup_manager()
        self.assertIs(a, b)
        bm._backup_manager = None

    def test_create_backup_module(self):
        with mock.patch.object(bm, "get_backup_manager") as g:
            m = mock.MagicMock()
            m.create_backup.return_value = {"ok": True}
            g.return_value = m
            r = bm.create_backup("c", "full")
        self.assertEqual(r, {"ok": True})
        m.create_backup.assert_called_once_with("c", "full")

    def test_restore_backup_module(self):
        with mock.patch.object(bm, "get_backup_manager") as g:
            m = mock.MagicMock()
            m.restore_backup.return_value = {"ok": True}
            g.return_value = m
            r = bm.restore_backup("b1", "/tmp")
        self.assertEqual(r, {"ok": True})
        m.restore_backup.assert_called_once_with("b1", "/tmp")

    def test_verify_backup_module(self):
        with mock.patch.object(bm, "get_backup_manager") as g:
            m = mock.MagicMock()
            m.verify_backup.return_value = {"ok": True}
            g.return_value = m
            r = bm.verify_backup("b1")
        self.assertEqual(r, {"ok": True})

    def test_list_backups_module(self):
        with mock.patch.object(bm, "get_backup_manager") as g:
            m = mock.MagicMock()
            m.list_backups.return_value = [{"id": 1}]
            g.return_value = m
            r = bm.list_backups("c")
        self.assertEqual(r, [{"id": 1}])
        m.list_backups.assert_called_once_with("c")

    def test_get_statistics_module(self):
        with mock.patch.object(bm, "get_backup_manager") as g:
            m = mock.MagicMock()
            m.get_statistics.return_value = {"t": 1}
            g.return_value = m
            r = bm.get_statistics()
        self.assertEqual(r, {"t": 1})


if __name__ == "__main__":
    unittest.main()
