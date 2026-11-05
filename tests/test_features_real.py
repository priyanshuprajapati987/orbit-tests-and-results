"""Regression tests: the "claimed done" features actually work (not stubs).

- Skills Marketplace built-ins perform real work (web scrape / code exec / file organize).
- SolutionPatternIndexer embeds patterns into a real 768-dim vector (not [0.1]*768)
  and the in-memory similarity search returns the matching pattern.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import orbit.orbit.core.skills_marketplace as sm_mod
from orbit.orbit.core.skills_marketplace import SkillsMarketplace
from orbit.orbit.core.solution_pattern_indexer import SolutionPatternIndexer


def _skills_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(sm_mod, "PLUGINS_DIR", tmp_path)
    monkeypatch.setattr(sm_mod, "REGISTRY_PATH", tmp_path / "registry.json")
    return SkillsMarketplace()


def test_builtin_plugins_are_real_not_stubs(tmp_path, monkeypatch):
    sm = _skills_in_tmp(tmp_path, monkeypatch)
    skills = {s["id"]: s for s in sm.list_skills()}
    assert {"web_scraper", "code_executor", "file_organizer"} <= set(skills)
    for sid in ("web_scraper", "code_executor", "file_organizer"):
        content = (tmp_path / skills[sid]["filename"]).read_text(encoding="utf-8")
        assert (
            "safe_requests_get" in content
            or "CodeInterpreter" in content
            or "shutil" in content
        )
        assert '"status": "ready"' not in content  # not the old no-op stub


def test_code_executor_runs_real_code(tmp_path, monkeypatch):
    sm = _skills_in_tmp(tmp_path, monkeypatch)
    result = sm.run_skill("code_executor", code="print(6*7)")
    assert isinstance(result, dict)
    assert "42" in str(result.get("output", ""))


def test_file_organizer_moves_files(tmp_path, monkeypatch):
    sm = _skills_in_tmp(tmp_path, monkeypatch)
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.txt").write_text("x")
    (work / "b.py").write_text("y")
    result = sm.run_skill("file_organizer", path=str(work))
    assert result.get("moved", 0) == 2
    assert (work / "txt" / "a.txt").exists()
    assert (work / "py" / "b.py").exists()


def test_pattern_indexer_embedding_is_real():
    idx = SolutionPatternIndexer()
    empty_vec = idx._embed("")
    assert len(empty_vec) == 768 and sum(empty_vec) == 0.0

    v1 = idx._embed("resize an image with PIL and save it")
    v2 = idx._embed("resize an image with PIL and save it")
    v3 = idx._embed("train a neural network with pytorch")
    assert v1 != [0.0] * 768
    assert v1 == v2  # determinism
    assert abs(sum(a * b for a, b in zip(v1, v2)) - 1.0) < 1e-9
    assert sum(a * b for a, b in zip(v1, v3)) < 1.0


def test_pattern_indexer_find_similar():
    idx = SolutionPatternIndexer()
    p1 = idx.create_pattern(
        "TaskAgent",
        "resize image",
        "Use PIL Image.resize((w,h)) and save",
        {"ok": True},
    )
    p2 = idx.create_pattern(
        "ResearchAgent",
        "web scraping",
        "Use requests to fetch then parse html",
        {"ok": True},
    )
    idx.index_pattern(p1)
    idx.index_pattern(p2)
    found = idx.find_similar_patterns(
        "how do I resize an image using PIL", similarity_threshold=0.1
    )
    found_ids = [f["id"] for f in found]
    assert p1["id"] in found_ids  # the relevant pattern is retrieved


def test_pattern_indexer_qdrant_uses_real_vector():
    class FakeQdrant:
        def __init__(self):
            self.points = {}

        def upsert(self, collection_name, points):
            for p in points:
                self.points[p["id"]] = p

        def search(self, collection_name, query_vector, limit=5):
            class Hit:
                def __init__(self, pid, vec):
                    self.payload = {"id": pid}
                    self.score = sum(a * b for a, b in zip(vec, query_vector))

            return [Hit(pid, p["vector"]) for pid, p in self.points.items()]

    fq = FakeQdrant()
    idx = SolutionPatternIndexer(qdrant_client=fq)
    p = idx.create_pattern("X", "topic", "some real solution text here", {"ok": True})
    idx.index_pattern(p)
    assert fq.points[p["id"]]["vector"] != [0.1] * 768
    assert len(fq.points[p["id"]]["vector"]) == 768
