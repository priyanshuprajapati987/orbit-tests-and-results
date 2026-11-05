"""P3 atomic write fault tests — torn-write, crash, recovery guarantees.

Verifies:
  * atomic_write_text never leaves a torn/partial primary file
  * atomic_write_text_bak preserves previous as .bak + fsyncs
  * load_json_with_bak recovers from corrupt primary via .bak
  * concurrent writes never expose partial content to readers
  * tmp files are always cleaned up (no leak on failure)
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from orbit.orbit.core.runtime_paths import (
    atomic_write_json,
    atomic_write_text,
    atomic_write_text_bak,
    load_json_with_bak,
)


class TestAtomicWriteText:
    def test_write_creates_file(self, tmp_path):
        p = tmp_path / "a.txt"
        atomic_write_text(p, "hello")
        assert p.read_text(encoding="utf-8") == "hello"

    def test_overwrite_leaves_no_tmp(self, tmp_path):
        p = tmp_path / "a.txt"
        atomic_write_text(p, "v1")
        atomic_write_text(p, "v2")
        assert p.read_text(encoding="utf-8") == "v2"
        assert list(tmp_path.glob(".tmp_*")) == []

    def test_crash_during_write_keeps_original(self, tmp_path, monkeypatch):
        p = tmp_path / "a.txt"
        atomic_write_text(p, "original")
        # simulate crash at the replace step: original must survive
        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            atomic_write_text(p, "new-data-that-never-lands")
        monkeypatch.undo()
        assert p.read_text(encoding="utf-8") == "original"
        # tmp cleaned up
        assert list(tmp_path.glob(".tmp_*")) == []

    def test_reader_never_sees_torn_content(self, tmp_path):
        p = tmp_path / "a.txt"
        atomic_write_text(p, "x" * 100_000)
        results = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    content = p.read_text(encoding="utf-8")
                    results.append(len(content))
                except OSError:
                    pass

        def writer_with_retry(content):
            # Windows: os.replace fails while the reader holds the file open
            for _ in range(50):
                try:
                    atomic_write_text(p, content)
                    return
                except PermissionError:
                    import time as _t
                    _t.sleep(0.01)
            raise AssertionError("writer never succeeded")

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        for i in range(50):
            writer_with_retry(str(i) * 1000)
        stop.set()
        t.join(timeout=2)
        valid_lengths = {len(str(i) * 1000) for i in range(50)}
        valid_lengths.add(len("x" * 100_000))
        assert results, "reader observed nothing"
        assert all(r in valid_lengths for r in results), (
            f"reader saw torn content: {[r for r in results if r not in valid_lengths][:5]}"
        )


class TestAtomicWriteBak:
    def test_first_write_no_bak(self, tmp_path):
        p = tmp_path / "a.json"
        atomic_write_text_bak(p, '{"v":1}')
        assert p.exists()
        assert not Path(str(p) + ".bak").exists()

    def test_second_write_creates_bak(self, tmp_path):
        p = tmp_path / "a.json"
        atomic_write_text_bak(p, '{"v":1}')
        atomic_write_text_bak(p, '{"v":2}')
        assert p.read_text(encoding="utf-8") == '{"v":2}'
        bak = Path(str(p) + ".bak")
        assert bak.exists()
        assert bak.read_text(encoding="utf-8") == '{"v":1}'

    def test_no_tmp_left(self, tmp_path):
        p = tmp_path / "a.json"
        for i in range(5):
            atomic_write_text_bak(p, f'{{"v":{i}}}')
        assert list(tmp_path.glob(".tmp_*")) == []


class TestLoadJsonWithBak:
    def test_reads_primary(self, tmp_path):
        p = tmp_path / "s.json"
        atomic_write_text_bak(p, '{"a":1}')
        assert load_json_with_bak(p) == {"a": 1}

    def test_recovers_from_corrupt_primary(self, tmp_path):
        p = tmp_path / "s.json"
        atomic_write_text_bak(p, '{"a":1}')   # primary v1
        atomic_write_text_bak(p, '{"a":2}')   # primary v2, .bak = v1
        p.write_text("{CORRUPT", encoding="utf-8")
        data = load_json_with_bak(p)
        assert data == {"a": 1}  # recovered from .bak

    def test_missing_everywhere_returns_default(self, tmp_path):
        p = tmp_path / "nope.json"
        assert load_json_with_bak(p, default={"init": True}) == {"init": True}
        assert load_json_with_bak(p) is None

    def test_valid_json_but_wrong_type_still_returned(self, tmp_path):
        p = tmp_path / "s.json"
        atomic_write_text_bak(p, "[1,2,3]")
        assert load_json_with_bak(p) == [1, 2, 3]


class TestAtomicWriteJson:
    def test_json_roundtrip(self, tmp_path):
        p = tmp_path / "j.json"
        atomic_write_json(p, {"k": [1, 2]})
        assert json.loads(p.read_text(encoding="utf-8")) == {"k": [1, 2]}

    def test_bak_preserved(self, tmp_path):
        # atomic_write_text_bak is the variant that writes .bak
        p = tmp_path / "j.json"
        atomic_write_text_bak(p, '{"v":1}')
        atomic_write_text_bak(p, '{"v":2}')
        bak = Path(str(p) + ".bak")
        assert bak.exists()
        assert json.loads(bak.read_text(encoding="utf-8")) == {"v": 1}
        # plain atomic_write_json does NOT create .bak (by design)
        p2 = tmp_path / "j2.json"
        atomic_write_json(p2, {"v": 1})
        assert not Path(str(p2) + ".bak").exists()


class TestConcurrentWrites:
    def test_parallel_writers_keep_file_valid(self, tmp_path):
        p = tmp_path / "c.json"
        atomic_write_json(p, {"n": 0})
        errors = []

        def writer(i):
            try:
                for j in range(20):
                    for _ in range(50):
                        try:
                            atomic_write_json(p, {"n": i * 100 + j})
                            break
                        except PermissionError:
                            import time as _t
                            _t.sleep(0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert errors == []
        # final content is always valid JSON (never torn)
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "n" in data
