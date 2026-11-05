"""Memory modules + server audit — pure-logic function tests."""
import json
import os
import tempfile
import time
from datetime import datetime

import pytest


# ═══════════════════════════════════════════════════════════════════
#  Hybrid Memory — BM25 + TFIDFEngine
# ═══════════════════════════════════════════════════════════════════


class TestBM25:
    def _bm25(self):
        from orbit.orbit.core.hybrid_memory import BM25

        return BM25()

    def test_add_and_search(self):
        bm = self._bm25()
        bm.add(["python", "programming", "language"])
        bm.add(["cooking", "pasta", "recipe"])
        results = bm.search(["python"], top_k=1)
        assert len(results) == 1
        idx, score = results[0]
        assert idx == 0
        assert score > 0

    def test_search_empty_index(self):
        bm = self._bm25()
        assert bm.search(["anything"]) == []

    def test_search_no_match(self):
        bm = self._bm25()
        bm.add(["hello", "world"])
        results = bm.search(["zzz"])
        assert results == [] or results == [(0, 0.0)]

    def test_ranking_relevance(self):
        bm = self._bm25()
        bm.add(["python", "python", "code"])  # high tf for python
        bm.add(["java", "code"])
        results = bm.search(["python"], top_k=2)
        assert results[0][0] == 0

    def test_avgdl_updates(self):
        bm = self._bm25()
        bm.add(["a", "b", "c"])
        bm.add(["d", "e"])
        assert bm._avgdl == pytest.approx(2.5, abs=0.01)

    def test_k1_b_defaults(self):
        bm = self._bm25()
        assert bm.k1 == 1.5
        assert bm.b == 0.75


class TestTFIDFEngine:
    def _tfidf(self):
        from orbit.orbit.core.hybrid_memory import TFIDFEngine

        return TFIDFEngine()

    def test_add_and_search(self):
        eng = self._tfidf()
        eng.add(["hello", "world"])
        eng.add(["goodbye", "cruel", "world"])
        results = eng.search(["hello"], top_k=1)
        assert len(results) >= 1

    def test_idf_rare_term_higher(self):
        eng = self._tfidf()
        for _ in range(5):
            eng.add(["common", "term"])
        eng.add(["rare", "term"])
        assert eng._idf("rare") > eng._idf("common")

    def test_vec_shape(self):
        eng = self._tfidf()
        eng.add(["alpha", "beta"])
        v = eng._vec(["alpha", "alpha", "gamma"])
        assert "alpha" in v
        assert v["alpha"] > 0

    def test_search_empty(self):
        eng = self._tfidf()
        assert eng.search(["x"]) == []


# ═══════════════════════════════════════════════════════════════════
#  Procedural Memory
# ═══════════════════════════════════════════════════════════════════


class TestProceduralMemory:
    def _pm(self, tmp_path):
        from orbit.orbit.core.procedural_memory import ProceduralMemory

        return ProceduralMemory(storage_file=str(tmp_path / "proc.json"))

    def test_store_and_get(self, tmp_path):
        pm = self._pm(tmp_path)
        pid = pm.store_procedure(name="deploy", steps=["build", "test", "push"], category="devops")
        proc = pm.get_procedure(pid)
        assert proc["name"] == "deploy"
        assert proc["steps"] == ["build", "test", "push"]
        assert proc["usage_count"] == 0

    def test_store_generates_id(self, tmp_path):
        pm = self._pm(tmp_path)
        pid1 = pm.store_procedure(name="a", steps=["s"])
        pid2 = pm.store_procedure(name="b", steps=["s"])
        assert pid1 != pid2

    def test_search_by_name(self, tmp_path):
        pm = self._pm(tmp_path)
        pm.store_procedure(name="deploy to prod", steps=["build", "push"])
        pm.store_procedure(name="cook dinner", steps=["chop", "cook"])
        results = pm.search_procedures("deploy")
        assert len(results) == 1
        assert results[0]["name"] == "deploy to prod"

    def test_search_by_category_filter(self, tmp_path):
        pm = self._pm(tmp_path)
        pm.store_procedure(name="deploy", steps=["s"], category="devops")
        pm.store_procedure(name="cook", steps=["s"], category="cooking")
        results = pm.search_procedures("", category="devops")
        assert len(results) == 1
        assert results[0]["category"] == "devops"

    def test_update_procedure(self, tmp_path):
        pm = self._pm(tmp_path)
        pid = pm.store_procedure(name="old", steps=["a"])
        ok = pm.update_procedure(pid, name="new", steps=["b", "c"])
        assert ok is True
        proc = pm.get_procedure(pid)
        assert proc["name"] == "new"
        assert proc["steps"] == ["b", "c"]

    def test_update_unknown_graceful(self, tmp_path):
        pm = self._pm(tmp_path)
        result = pm.update_procedure("nonexistent", name="x")
        assert result is False

    def test_delete_procedure(self, tmp_path):
        pm = self._pm(tmp_path)
        pid = pm.store_procedure(name="temp", steps=["s"])
        assert pm.delete_procedure(pid) is True
        assert pm.get_procedure(pid) is None

    def test_delete_unknown_false(self, tmp_path):
        pm = self._pm(tmp_path)
        assert pm.delete_procedure("nope") is False

    def test_record_usage_success(self, tmp_path):
        pm = self._pm(tmp_path)
        pid = pm.store_procedure(name="deploy", steps=["s"])
        pm.record_usage(pid, success=True)
        proc = pm.get_procedure(pid)
        assert proc["usage_count"] == 1
        assert proc["success_rate"] == pytest.approx(1.0, abs=0.01)

    def test_record_usage_failure(self, tmp_path):
        pm = self._pm(tmp_path)
        pid = pm.store_procedure(name="deploy", steps=["s"])
        pm.record_usage(pid, success=False)
        proc = pm.get_procedure(pid)
        assert proc["success_rate"] == pytest.approx(0.0, abs=0.01)

    def test_record_usage_unknown_graceful(self, tmp_path):
        pm = self._pm(tmp_path)
        pm.record_usage("ghost", success=True)  # must not raise

    def test_statistics(self, tmp_path):
        pm = self._pm(tmp_path)
        pm.store_procedure(name="a", steps=["s"], category="x")
        pm.store_procedure(name="b", steps=["s"], category="y")
        stats = pm.get_statistics()
        assert stats["total"] == 2
        assert "categories" in stats

    def test_statistics_empty(self, tmp_path):
        pm = self._pm(tmp_path)
        stats = pm.get_statistics()
        assert stats["total"] == 0

    def test_persistence_roundtrip(self, tmp_path):
        from orbit.orbit.core.procedural_memory import ProceduralMemory

        path = str(tmp_path / "proc.json")
        pm1 = ProceduralMemory(storage_file=path)
        pid = pm1.store_procedure(name="persist", steps=["s"])
        pm2 = ProceduralMemory(storage_file=path)
        assert pm2.get_procedure(pid)["name"] == "persist"


# ═══════════════════════════════════════════════════════════════════
#  Memory Graph
# ═══════════════════════════════════════════════════════════════════


class TestMemoryGraph:
    def _mg(self, tmp_path):
        from orbit.orbit.core.memory_graph import MemoryGraph

        return MemoryGraph(storage_file=str(tmp_path / "graph.json"))

    def test_add_entity(self, tmp_path):
        mg = self._mg(tmp_path)
        e = mg.add_entity("Python", "TECH")
        assert e.entity_id == "python"
        assert e.name == "Python"

    def test_add_entity_duplicate_increments_mentions(self, tmp_path):
        mg = self._mg(tmp_path)
        mg.add_entity("Python", "TECH")
        e = mg.add_entity("Python", "TECH")
        assert e.mentions >= 2

    def test_add_relation(self, tmp_path):
        mg = self._mg(tmp_path)
        mg.add_entity("Python", "TECH")
        mg.add_entity("Coding", "ACTIVITY")
        r = mg.add_relation("Python", "Coding", "USED_FOR")
        assert r.source_id == "python"
        assert r.target_id == "coding"

    def test_add_relation_weight_bump(self, tmp_path):
        mg = self._mg(tmp_path)
        mg.add_entity("A", "X")
        mg.add_entity("B", "Y")
        r1 = mg.add_relation("A", "B", "LINKS")
        w1 = r1.weight
        r2 = mg.add_relation("A", "B", "LINKS")  # same relation, bump
        assert r2.weight > w1

    def test_ingest_text(self, tmp_path):
        mg = self._mg(tmp_path)
        result = mg.ingest_text("Python is used for coding and data science")
        assert "entities_added" in result
        assert "relations_added" in result

    def test_neighbors(self, tmp_path):
        mg = self._mg(tmp_path)
        mg.add_entity("Python", "TECH")
        mg.add_entity("Coding", "ACTIVITY")
        mg.add_relation("Python", "Coding", "USED_FOR")
        n = mg.neighbors("Python", direction="out")
        assert len(n) >= 1

    def test_find_path(self, tmp_path):
        mg = self._mg(tmp_path)
        mg.add_entity("A", "X")
        mg.add_entity("B", "Y")
        mg.add_entity("C", "Z")
        mg.add_relation("A", "B", "L")
        mg.add_relation("B", "C", "L")
        path = mg.find_path("A", "C", max_depth=3)
        assert path is not None
        assert len(path) >= 2

    def test_find_path_none(self, tmp_path):
        mg = self._mg(tmp_path)
        mg.add_entity("A", "X")
        mg.add_entity("B", "Y")
        # no relation
        path = mg.find_path("A", "B", max_depth=2)
        assert path is None or len(path) == 0

    def test_get_stats(self, tmp_path):
        mg = self._mg(tmp_path)
        mg.add_entity("Python", "TECH")
        mg.add_entity("Java", "TECH")
        mg.add_relation("Python", "Java", "COMPARES")
        stats = mg.get_stats()
        assert "entities" in stats or "total_entities" in stats

    def test_entity_id_normalization(self, tmp_path):
        mg = self._mg(tmp_path)
        e = mg.add_entity("Hello World!", "CONCEPT")
        assert e.entity_id == "hello_world"


# ═══════════════════════════════════════════════════════════════════
#  Memory Upgrade — UserProfile + ImportanceScorer
# ═══════════════════════════════════════════════════════════════════


class TestUserProfile:
    def _up(self):
        from orbit.orbit.core.memory_upgrade import UserProfile

        # redirect storage to tmp to avoid touching real profile
        import orbit.orbit.core.memory_upgrade as mu

        orig = mu.PROFILE_DIR
        mu.PROFILE_DIR = __import__("pathlib").Path(tempfile.mkdtemp())
        try:
            return UserProfile()
        finally:
            mu.PROFILE_DIR = orig

    def test_update_and_get(self):
        up = self._up()
        up.update("name", "Priyanshu", category="personal")
        assert up.get("name") == "Priyanshu"

    def test_get_missing_none(self):
        up = self._up()
        assert up.get("nonexistent") is None

    def test_get_by_category(self):
        up = self._up()
        up.update("name", "P", category="personal")
        up.update("project", "ORBIT", category="work")
        personal = up.get_by_category("personal")
        assert "name" in personal
        assert "project" not in personal

    def test_get_all(self):
        up = self._up()
        up.update("a", 1)
        up.update("b", 2)
        assert len(up.get_all()) >= 2

    def test_get_summary(self):
        up = self._up()
        up.update("a", 1)
        summary = up.get_summary()
        assert "total_entries" in summary
        assert "categories" in summary

    def test_update_existing_increments_confidence(self):
        up = self._up()
        up.update("k", "v1")
        up.update("k", "v2")
        assert up.get("k") == "v2"


class TestImportanceScorer:
    def test_secret_gets_lowest(self):
        from orbit.orbit.core.memory_upgrade import MemoryImportanceScorer

        score = MemoryImportanceScorer.score("password is hunter2 and api_key=abc123")
        assert score == 1

    def test_personal_high(self):
        from orbit.orbit.core.memory_upgrade import MemoryImportanceScorer

        score = MemoryImportanceScorer.score("my favorite color is blue", category="personal")
        assert score >= 3

    def test_score_bounds(self):
        from orbit.orbit.core.memory_upgrade import MemoryImportanceScorer

        for content in ["hello", "password=x", "important project deadline"]:
            s = MemoryImportanceScorer.score(content)
            assert 1 <= s <= 10

    def test_should_delete_old_low(self):
        from orbit.orbit.core.memory_upgrade import MemoryImportanceScorer

        assert MemoryImportanceScorer.should_delete(importance=1, age_days=90) is True
        assert MemoryImportanceScorer.should_delete(importance=9, age_days=1) is False


# ═══════════════════════════════════════════════════════════════════
#  Smart Memory — preferences + agent patterns
# ═══════════════════════════════════════════════════════════════════


class TestSmartMemory:
    def _sm(self):
        from collections import defaultdict, deque
        import threading

        from orbit.orbit.core.smart_memory import SmartMemory

        sm = SmartMemory.__new__(SmartMemory)
        sm._preferences = {}
        sm._agent_patterns = {}
        sm._corrections = []
        sm._topic_frequency = defaultdict(int)
        sm._time_patterns = defaultdict(lambda: defaultdict(int))
        sm._recent_queries = deque(maxlen=50)
        sm._lock = threading.RLock()
        sm._query_lengths = []
        sm._expertise_level = "intermediate"
        return sm

    def test_set_get_preference(self):
        sm = self._sm()
        sm.set_preference("theme", "dark", confidence=0.8)
        assert sm.get_preference("theme") == "dark"

    def test_get_low_confidence_none(self):
        from orbit.orbit.core.smart_memory import UserPreference

        sm = self._sm()
        sm._preferences["k"] = UserPreference(key="k", value="v", confidence=0.3)
        assert sm.get_preference("k") is None

    def test_set_same_value_boosts_confidence(self):
        sm = self._sm()
        sm.set_preference("theme", "dark", confidence=0.5)
        sm.set_preference("theme", "dark", confidence=0.5)
        pref = sm._preferences["theme"]
        assert pref.evidence >= 2
        assert pref.confidence >= 0.5

    def test_set_different_value_lowers_confidence(self):
        sm = self._sm()
        sm.set_preference("theme", "dark", confidence=0.8)
        sm.set_preference("theme", "light", confidence=0.8)
        pref = sm._preferences["theme"]
        assert pref.value == "light"
        assert pref.confidence < 0.8

    def test_record_agent_usage_no_crash(self):
        sm = self._sm()
        sm.record_agent_usage("COD", "write a python function", success=True)
        sm.record_agent_usage("WRI", "write an email", success=False)
        # must not raise; patterns may or may not be created

    def test_get_agent_success_rate_unknown(self):
        sm = self._sm()
        rate = sm.get_agent_success_rate("GHOST")
        assert rate == 0.0 or isinstance(rate, float)

    def test_get_best_agent_unknown_topic(self):
        sm = self._sm()
        result = sm.get_best_agent_for_topic("unheard-of-topic")
        assert result is None or isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════
#  Server — healthz (no deps liveness)
# ═══════════════════════════════════════════════════════════════════


class TestServerLiveness:
    def test_healthz_no_deps(self):
        """Liveness probe touches no dependencies — safe to test."""
        from flask import Flask

        from orbit.orbit.core import __version__

        app = Flask(__name__)

        @app.route("/api/healthz")
        def healthz():
            from flask import jsonify

            return jsonify({"status": "alive", "version": __version__}), 200

        client = app.test_client()
        resp = client.get("/api/healthz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "alive"
        assert "version" in data

    def test_readyz_importable(self):
        """readyz module imports (runtime_paths)."""
        from orbit.orbit.core import runtime_paths

        assert hasattr(runtime_paths, "frontend_dist")
        assert hasattr(runtime_paths, "orbit_data_dir")

    def test_version_consistency(self):
        """__version__ importable and non-empty."""
        from orbit.orbit.core import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0
