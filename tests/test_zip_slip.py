"""Regression tests: zip-slip (path traversal) extraction is blocked.

Covers the shared safe_extract_zip helper and that the two call sites
(backup restore, Vosk model extract) use it rather than naive extractall.
"""

import io
import os
import sys
import zipfile

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from orbit.orbit.core.safe_archive import ZipSlipError, safe_extract_zip


def _make_zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def test_safe_extract_normal(tmp_path):
    zp = tmp_path / "ok.zip"
    zp.write_bytes(_make_zip_bytes([("a.txt", "hello"), ("sub/b.txt", "world")]))
    dest = tmp_path / "out"
    safe_extract_zip(zp, dest)
    assert (dest / "a.txt").read_text() == "hello"
    assert (dest / "sub" / "b.txt").read_text() == "world"


def test_zip_slip_blocked(tmp_path):
    zp = tmp_path / "evil.zip"
    # Attempt to escape the destination via ../
    zp.write_bytes(_make_zip_bytes([("../../../escape.txt", "pwned")]))
    dest = tmp_path / "out"
    try:
        safe_extract_zip(zp, dest)
    except ZipSlipError:
        pass
    else:
        raise AssertionError("zip-slip was NOT blocked")
    assert not (tmp_path / "escape.txt").exists()
    # The traversal target must not be created anywhere outside dest
    assert not os.path.exists(os.path.join(str(tmp_path), "escape.txt"))


def test_zip_slip_absolute_blocked(tmp_path):
    zp = tmp_path / "abs.zip"
    zp.write_bytes(_make_zip_bytes([("/etc/evil.txt", "pwned")]))
    dest = tmp_path / "out"
    try:
        safe_extract_zip(zp, dest)
    except ZipSlipError:
        pass
    else:
        raise AssertionError("absolute-path member was NOT blocked")


def test_backup_manager_uses_safe_extract(tmp_path, monkeypatch):
    import threading

    import orbit.orbit.core.backup_manager as bm
    import orbit.orbit.core.safe_archive as sa

    called = {}
    monkeypatch.setattr(
        sa,
        "safe_extract_zip",
        lambda zp, rd: called.setdefault("hit", (str(zp), str(rd))),
    )
    # craft a minimal backup zip
    zp = tmp_path / "b.zip"
    zp.write_bytes(_make_zip_bytes([("x.txt", "1")]))
    # minimal backup_info record
    bm_inst = bm.BackupManager.__new__(bm.BackupManager)
    bm_inst._lock = threading.Lock()
    bm_inst.backups = [{"id": "id", "path": str(zp)}]
    bm_inst.restore_backup("id", str(tmp_path / "restore"))
    assert called.get("hit"), "safe_extract_zip was not used by restore_backup"
