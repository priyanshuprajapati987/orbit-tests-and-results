# ORBIT — File Organizer tests (Phase 1)
# Run: python -m pytest tests/test_file_organizer.py -v

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_organizer_categorizes_by_extension():
    from orbit.orbit.core.file_organizer import FileOrganizer
    fo = FileOrganizer()
    assert fo._categorize(Path("a.pdf")) == "Documents"
    assert fo._categorize(Path("b.png")) == "Images"
    assert fo._categorize(Path("c.unknown")) == "Other"


def test_organizer_dry_run_does_not_move(tmp_path):
    (tmp_path / "x.txt").write_text("hi")
    from orbit.orbit.core.file_organizer import FileOrganizer
    fo = FileOrganizer(base_dir=str(tmp_path))
    fo.set_dry_run(True)
    res = fo.organize()
    assert len(res) == 1
    assert res[0].action == "dry-run"
    assert (tmp_path / "x.txt").exists()


def test_organizer_moves_files(tmp_path):
    (tmp_path / "x.txt").write_text("hi")
    from orbit.orbit.core.file_organizer import FileOrganizer
    fo = FileOrganizer(base_dir=str(tmp_path))
    res = fo.organize()
    assert res[0].action == "moved"
    assert (tmp_path / "Documents" / "x.txt").exists()


def test_organizer_skips_existing_dest(tmp_path):
    (tmp_path / "x.txt").write_text("hi")
    dest = tmp_path / "Documents"
    dest.mkdir()
    (dest / "x.txt").write_text("dup")
    from orbit.orbit.core.file_organizer import FileOrganizer
    fo = FileOrganizer(base_dir=str(tmp_path))
    res = fo.organize()
    assert res[0].action == "skipped"


def test_organizer_stats(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    from orbit.orbit.core.file_organizer import FileOrganizer
    fo = FileOrganizer(base_dir=str(tmp_path))
    stats = fo.get_stats()
    assert stats["total_files"] == 1
    assert "Documents" in stats["by_category"]


def test_find_duplicates(tmp_path):
    (tmp_path / "a.txt").write_text("same")
    (tmp_path / "b.txt").write_text("same")
    from orbit.orbit.core.file_organizer import FileOrganizer
    fo = FileOrganizer(base_dir=str(tmp_path))
    dups = fo.find_duplicates()
    assert len(dups) == 1
    assert len(dups[0]["files"]) == 2
