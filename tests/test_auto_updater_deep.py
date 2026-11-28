"""Deep tests for orbit/orbit/core/auto_updater.py (Loop 22/2)."""

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import auto_updater as au


class GetLocalVersionTests(unittest.TestCase):
    def test_imports_version(self):
        # _get_local_version already ran at import; just check LOCAL_VERSION set
        self.assertIsInstance(au.LOCAL_VERSION, str)
        self.assertTrue(au.LOCAL_VERSION)

    def test_fallback_on_import_error(self):
        with mock.patch("builtins.__import__", side_effect=ImportError("no")):
            # calling _get_local_version directly with import failing
            # It does `from ... import __version__` -> ImportError -> fallback
            v = au._get_local_version()
        self.assertEqual(v, "3.7.0")


class InitTests(unittest.TestCase):
    def test_init_creates_dirs(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        data_dir = d / "data"
        backup_dir = data_dir / "backups"
        with mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", data_dir), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", backup_dir), \
                mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE",
                           d / "VERSION"), \
                mock.patch("pathlib.Path.mkdir") as mk:
            au.AutoUpdater()
        # mkdir called for DATA_DIR and BACKUP_DIR
        self.assertGreaterEqual(mk.call_count, 2)

    def test_load_version_existing(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        vf.write_text("  4.0.0  ", encoding="utf-8")
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf):
            u = au.AutoUpdater.__new__(au.AutoUpdater)
            # manually call _load_version
            u._version = u._load_version()
        self.assertEqual(u._version, "4.0.0")

    def test_load_version_missing(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf):
            v = u._load_version()
        self.assertEqual(v, au.LOCAL_VERSION)

    def test_load_version_corrupt(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        vf.write_text("", encoding="utf-8")
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf):
            v = u._load_version()
        self.assertEqual(v, au.LOCAL_VERSION)

    def test_load_version_exception(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        vf.write_text("x", encoding="utf-8")
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch.object(Path, "read_text", side_effect=OSError("boom")), \
                mock.patch.object(au, "logger") as lg:
            v = u._load_version()
        self.assertEqual(v, au.LOCAL_VERSION)
        lg.warning.assert_called_once()

    def test_save_version_success(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf):
            ok = u._save_version("5.0.0")
        self.assertIsNone(ok)
        self.assertEqual(vf.read_text("utf-8"), "5.0.0")
        self.assertEqual(u._version, "5.0.0")

    def test_save_version_failure(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch.object(Path, "with_name", side_effect=OSError("boom")), \
                mock.patch.object(au, "logger") as lg:
            ok = u._save_version("5.0.0")
        self.assertFalse(ok)
        lg.error.assert_called_once()


class CheckForUpdatesTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", d / "data"), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"), \
                mock.patch("pathlib.Path.mkdir"):
            u = au.AutoUpdater()
        return u, d

    def test_error_status(self):
        u, d = self._make()
        resp = mock.MagicMock(status_code=500)
        with mock.patch("requests.get", return_value=resp):
            r = u.check_for_updates()
        self.assertEqual(r, {"status": "error", "message": "GitHub API returned 500"})

    def test_no_commits(self):
        u, d = self._make()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = []
        with mock.patch("requests.get", return_value=resp):
            r = u.check_for_updates()
        self.assertEqual(r, {"status": "ok", "update_available": False,
                             "message": "No commits found"})

    def test_update_available(self):
        u, d = self._make()
        commits = [
            {"sha": "a" * 40, "commit": {"message": "msg1\nbody", "author": {"name": "dev", "date": "2026-01-01"}}},
        ]
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = commits
        with mock.patch("requests.get", return_value=resp), \
                mock.patch.object(u, "_local_sha", return_value="b" * 40):
            r = u.check_for_updates()
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["update_available"])
        self.assertEqual(r["latest_sha"], "a" * 8)
        self.assertEqual(r["latest_message"], "msg1")
        self.assertEqual(r["latest_date"], "2026-01-01")
        self.assertEqual(r["author"], "dev")
        self.assertEqual(r["changelog"][0]["sha"], "a" * 8)
        self.assertEqual(r["changelog"][0]["message"], "msg1")
        self.assertEqual(len(r["changelog"]), 1)
        self.assertEqual(r["repo"], f"{au.REPO_OWNER}/{au.REPO_NAME}")

    def test_up_to_date(self):
        u, d = self._make()
        sha = "a" * 40
        commits = [{"sha": sha, "commit": {"message": "msg", "author": {"name": "dev", "date": "2026-01-01"}}}]
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = commits
        with mock.patch("requests.get", return_value=resp), \
                mock.patch.object(u, "_local_sha", return_value=sha):
            r = u.check_for_updates()
        self.assertFalse(r["update_available"])
        self.assertEqual(r["message"], "Already up to date")

    def test_unknown_local_sha(self):
        u, d = self._make()
        commits = [{"sha": "a" * 40, "commit": {"message": "msg", "author": {"name": "dev", "date": "2026-01-01"}}}]
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = commits
        with mock.patch("requests.get", return_value=resp), \
                mock.patch.object(u, "_local_sha", return_value=""):
            r = u.check_for_updates()
        self.assertIsNone(r["update_available"])
        self.assertEqual(r["message"], "Could not determine local version (no git metadata)")
        self.assertEqual(r["local_sha"], "")

    def test_exception(self):
        u, d = self._make()
        with mock.patch("requests.get", side_effect=Exception("net")):
            r = u.check_for_updates()
        self.assertEqual(r, {"status": "error", "message": "net"})

    def test_changelog_capped_10(self):
        u, d = self._make()
        commits = [{"sha": f"{'a'*8}{i}", "commit": {"message": f"msg{i}", "author": {"name": "dev", "date": "2026-01-01"}}}
                   for i in range(15)]
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = commits
        with mock.patch("requests.get", return_value=resp), \
                mock.patch.object(u, "_local_sha", return_value=""):
            r = u.check_for_updates()
        self.assertEqual(len(r["changelog"]), 10)


class LocalShaTests(unittest.TestCase):
    def test_success(self):
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        r = mock.MagicMock(stdout="a" * 40 + "\n", returncode=0)
        with mock.patch("subprocess.run", return_value=r), \
                mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=Path("/tmp")):
            self.assertEqual(u._local_sha(), "a" * 40)

    def test_short_sha_returns_empty(self):
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        r = mock.MagicMock(stdout="short", returncode=0)
        with mock.patch("subprocess.run", return_value=r), \
                mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=Path("/tmp")):
            self.assertEqual(u._local_sha(), "")

    def test_exception_returns_empty(self):
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        with mock.patch("subprocess.run", side_effect=Exception("boom")):
            self.assertEqual(u._local_sha(), "")


class ApplyUpdateTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", d / "data"), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"), \
                mock.patch("pathlib.Path.mkdir"):
            u = au.AutoUpdater()
        return u, d

    def test_no_changed_files(self):
        u, d = self._make()
        with mock.patch.object(u, "_create_backup", return_value=Path("/tmp/b")), \
                mock.patch.object(u, "_get_changed_files", return_value=[]):
            r = u.apply_update()
        self.assertEqual(r, {"status": "ok", "message": "Already up to date",
                             "files_updated": []})

    def test_downloads_updated_and_added(self):
        u, d = self._make()
        root = d / "root"
        root.mkdir(parents=True, exist_ok=True)
        (root / "existing.py").write_text("old", encoding="utf-8")
        with mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=root), \
                mock.patch.object(u, "_create_backup", return_value=Path("/tmp/b")), \
                mock.patch.object(u, "_get_changed_files", return_value=["existing.py", "new.py"]), \
                mock.patch.object(u, "_get_latest_commits", return_value=[]), \
                mock.patch.object(u, "_generate_changelog", return_value="CL"), \
                mock.patch.object(u, "check_for_updates", return_value={"latest_sha": "abc123"}), \
                mock.patch.object(u, "_save_version") as sv, \
                mock.patch("requests.get") as rg:
            def fake_get(url, timeout=15):
                r = mock.MagicMock(status_code=200)
                r.content = b"new content"
                return r
            rg.side_effect = fake_get
            r = u.apply_update()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["files_updated"], ["existing.py"])
        self.assertEqual(r["files_added"], ["new.py"])
        self.assertEqual(r["backup_path"], str(Path("/tmp/b")))
        self.assertEqual(r["changelog"], "CL")
        self.assertEqual(r["message"], "Updated 1 files, added 1 files")
        sv.assert_called_once_with("abc123")
        self.assertTrue((root / "existing.py").exists())
        self.assertTrue((root / "new.py").exists())

    def test_download_failure_skipped(self):
        u, d = self._make()
        root = d / "root"
        root.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=root), \
                mock.patch.object(u, "_create_backup", return_value=Path("/tmp/b")), \
                mock.patch.object(u, "_get_changed_files", return_value=["f.py"]), \
                mock.patch.object(u, "_get_latest_commits", return_value=[]), \
                mock.patch.object(u, "_generate_changelog", return_value="CL"), \
                mock.patch.object(u, "check_for_updates", return_value={}), \
                mock.patch("requests.get", side_effect=Exception("net")), \
                mock.patch.object(au, "logger") as lg:
            r = u.apply_update()
        self.assertEqual(r["files_updated"], [])
        self.assertEqual(r["files_added"], [])
        lg.warning.assert_called()

    def test_no_update_no_save_version(self):
        u, d = self._make()
        root = d / "root"
        root.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=root), \
                mock.patch.object(u, "_create_backup", return_value=Path("/tmp/b")), \
                mock.patch.object(u, "_get_changed_files", return_value=["f.py"]), \
                mock.patch.object(u, "_get_latest_commits", return_value=[]), \
                mock.patch.object(u, "_generate_changelog", return_value="CL"), \
                mock.patch.object(u, "check_for_updates", return_value={}), \
                mock.patch("requests.get", return_value=mock.MagicMock(status_code=404)):
            r = u.apply_update()
        self.assertEqual(r["files_updated"], [])
        self.assertEqual(r["files_added"], [])
        self.assertEqual(r["message"], "Updated 0 files, added 0 files")

    def test_exception_returns_error(self):
        u, d = self._make()
        with mock.patch.object(u, "_create_backup", side_effect=RuntimeError("boom")):
            r = u.apply_update()
        self.assertEqual(r, {"status": "error", "message": "boom"})

    def test_download_non_200_skipped(self):
        u, d = self._make()
        root = d / "root"
        root.mkdir(parents=True, exist_ok=True)
        (root / "f.py").write_text("old", encoding="utf-8")
        with mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=root), \
                mock.patch.object(u, "_create_backup", return_value=Path("/tmp/b")), \
                mock.patch.object(u, "_get_changed_files", return_value=["f.py"]), \
                mock.patch.object(u, "_get_latest_commits", return_value=[]), \
                mock.patch.object(u, "_generate_changelog", return_value="CL"), \
                mock.patch.object(u, "check_for_updates", return_value={"latest_sha": "abc"}), \
                mock.patch.object(u, "_save_version") as sv, \
                mock.patch("requests.get", return_value=mock.MagicMock(status_code=404)):
            r = u.apply_update()
        self.assertEqual(r["files_updated"], [])
        self.assertEqual(r["files_added"], [])
        sv.assert_not_called()


class RollbackTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", d / "data"), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"), \
                mock.patch("pathlib.Path.mkdir"):
            u = au.AutoUpdater()
        return u, d

    def test_no_backups(self):
        u, d = self._make()
        with mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"):
            r = u.rollback()
        self.assertEqual(r, {"status": "error", "message": "No backups available"})

    def test_rollback_restores(self):
        u, d = self._make()
        backup_dir = d / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        b = backup_dir / "backup_1_abc"
        b.mkdir()
        (b / "f.py").write_text("restored", encoding="utf-8")
        root = d / "root"
        root.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", backup_dir), \
                mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=root):
            r = u.rollback()
        self.assertEqual(r["status"], "ok")
        self.assertIn("Rolled back from", r["message"])
        self.assertEqual(r["files_restored"], 1)
        self.assertEqual((root / "f.py").read_text("utf-8"), "restored")


class CreateBackupTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", d / "data"), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"), \
                mock.patch("pathlib.Path.mkdir"):
            u = au.AutoUpdater()
        return u, d

    def test_backup_copies_files_and_dirs(self):
        u, d = self._make()
        root = d / "root"
        root.mkdir(parents=True, exist_ok=True)
        (root / "requirements.txt").write_text("req", encoding="utf-8")
        (root / "orbit").mkdir()
        (root / "orbit" / "x.py").write_text("x", encoding="utf-8")
        backup_dir = d / "backups"
        with mock.patch("orbit.orbit.core.auto_updater.app_root", return_value=root), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", backup_dir):
            bp = u._create_backup()
        self.assertTrue((bp / "requirements.txt").exists())
        self.assertTrue((bp / "orbit" / "x.py").exists())
        self.assertTrue(bp.name.startswith("backup_"))


class GetChangedFilesTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", d / "data"), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"), \
                mock.patch("pathlib.Path.mkdir"):
            u = au.AutoUpdater()
        return u, d

    def test_compare_success(self):
        u, d = self._make()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = {"files": [{"filename": "a.py"}, {"filename": "b.py"}]}
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(u._get_changed_files(), ["a.py", "b.py"])

    def test_compare_non_200_falls_back(self):
        u, d = self._make()
        resp1 = mock.MagicMock(status_code=404)
        commits = [{"sha": "a" * 40}]
        resp2 = mock.MagicMock(status_code=200)
        resp2.json.return_value = commits
        resp3 = mock.MagicMock(status_code=200)
        resp3.json.return_value = {"files": [{"filename": "c.py"}]}
        with mock.patch("requests.get", side_effect=[resp1, resp2, resp3]):
            self.assertEqual(u._get_changed_files(), ["c.py"])

    def test_compare_exception_falls_back(self):
        u, d = self._make()
        with mock.patch("requests.get", side_effect=Exception("net")), \
                mock.patch.object(au, "logger") as lg:
            r = u._get_changed_files()
        self.assertEqual(r, [])
        lg.exception.assert_called()

    def test_latest_commit_files_no_commits(self):
        u, d = self._make()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = []
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(u._get_latest_commit_files(), [])

    def test_latest_commit_files_non_200(self):
        u, d = self._make()
        resp = mock.MagicMock(status_code=404)
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(u._get_latest_commit_files(), [])

    def test_latest_commit_files_exception(self):
        u, d = self._make()
        with mock.patch("requests.get", side_effect=Exception("net")), \
                mock.patch.object(au, "logger") as lg:
            r = u._get_latest_commit_files()
        self.assertEqual(r, [])
        lg.exception.assert_called()

    def test_latest_commit_files_second_non_200(self):
        u, d = self._make()
        resp1 = mock.MagicMock(status_code=200)
        resp1.json.return_value = [{"sha": "a" * 40}]
        resp2 = mock.MagicMock(status_code=404)
        with mock.patch("requests.get", side_effect=[resp1, resp2]):
            self.assertEqual(u._get_latest_commit_files(), [])


class GetLatestCommitsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", d / "data"), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"), \
                mock.patch("pathlib.Path.mkdir"):
            u = au.AutoUpdater()
        return u, d

    def test_success(self):
        u, d = self._make()
        commits = [{"sha": "a" * 40, "commit": {"message": "msg\nbody", "author": {"name": "dev", "date": "2026-01-01"}}}]
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = commits
        with mock.patch("requests.get", return_value=resp):
            r = u._get_latest_commits()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["sha"], "a" * 8)
        self.assertEqual(r[0]["message"], "msg")
        self.assertEqual(r[0]["date"], "2026-01-01")

    def test_non_200(self):
        u, d = self._make()
        resp = mock.MagicMock(status_code=404)
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(u._get_latest_commits(), [])

    def test_exception(self):
        u, d = self._make()
        with mock.patch("requests.get", side_effect=Exception("net")), \
                mock.patch.object(au, "logger") as lg:
            r = u._get_latest_commits()
        self.assertEqual(r, [])
        lg.exception.assert_called()


class GenerateChangelogTests(unittest.TestCase):
    def test(self):
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        commits = [{"sha": "abc", "message": "msg", "date": "2026-01-15T10:00:00"}]
        r = u._generate_changelog(commits)
        self.assertIn("# ORBIT Changelog", r)
        self.assertIn("`abc` msg (2026-01-15)", r)

    def test_empty(self):
        u = au.AutoUpdater.__new__(au.AutoUpdater)
        r = u._generate_changelog([])
        self.assertIn("# ORBIT Changelog", r)


class GetBackupsTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        vf = d / "VERSION"
        with mock.patch("orbit.orbit.core.auto_updater.VERSION_FILE", vf), \
                mock.patch("orbit.orbit.core.auto_updater.DATA_DIR", d / "data"), \
                mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"), \
                mock.patch("pathlib.Path.mkdir"):
            u = au.AutoUpdater()
        return u, d

    def test_no_backups(self):
        u, d = self._make()
        with mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", d / "backups"):
            self.assertEqual(u.get_backups(), [])

    def test_with_backups(self):
        u, d = self._make()
        backup_dir = d / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        b = backup_dir / "backup_1_abc"
        b.mkdir()
        (b / "f.py").write_text("x", encoding="utf-8")
        with mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", backup_dir):
            r = u.get_backups()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["name"], "backup_1_abc")
        self.assertIn("path", r[0])
        self.assertIn("size_mb", r[0])

    def test_caps_10(self):
        u, d = self._make()
        backup_dir = d / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for i in range(15):
            (backup_dir / f"backup_{i}_x").mkdir()
        with mock.patch("orbit.orbit.core.auto_updater.BACKUP_DIR", backup_dir):
            r = u.get_backups()
        self.assertEqual(len(r), 10)


class GetUpdaterTests(unittest.TestCase):
    def test_singleton(self):
        au._instance = None
        a = au.get_updater()
        b = au.get_updater()
        self.assertIs(a, b)
        au._instance = None


if __name__ == "__main__":
    unittest.main()
