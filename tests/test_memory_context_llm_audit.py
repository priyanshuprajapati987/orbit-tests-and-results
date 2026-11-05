"""Memory + Context + LLM Router audit — pure-logic function tests."""
from datetime import datetime, timedelta

import pytest

# ═══════════════════════════════════════════════════════════════════
#  Context Manager — TF-IDF
# ═══════════════════════════════════════════════════════════════════


class TestTFIDF:
    def _ret(self, **kw):
        from orbit.orbit.core.context_manager import TFIDFRetriever

        return TFIDFRetriever(**kw)

    def test_tokenize(self):
        from orbit.orbit.core.context_manager import _tokenize

        assert _tokenize("Hello, World!") == ["hello", "world"]
        assert _tokenize("ab cd") == ["ab", "cd"]
        assert _tokenize("a b c") == []  # single-char tokens dropped (len>1)
        assert _tokenize("") == []

    def test_tokenize_short_words_filtered(self):
        from orbit.orbit.core.context_manager import _tokenize

        # single-char tokens dropped
        assert "a" not in _tokenize("a bb ccc")

    def test_cosine_identical(self):
        from orbit.orbit.core.context_manager import _cosine

        assert _cosine([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0, abs=1e-6)

    def test_cosine_orthogonal(self):
        from orbit.orbit.core.context_manager import _cosine

        assert _cosine([1, 0], [0, 1]) == 0.0

    def test_cosine_zero(self):
        from orbit.orbit.core.context_manager import _cosine

        assert _cosine([], [1, 2]) == 0.0
        assert _cosine([0, 0], [0, 0]) == 0.0

    def test_cosine_mismatched_length(self):
        from orbit.orbit.core.context_manager import _cosine

        assert _cosine([1, 2], [1, 2, 3]) == 0.0

    def test_add_returns_id(self):
        ret = self._ret()
        r1 = ret.add("hello world")
        assert "id" in r1
        r2 = ret.add("another doc")
        assert r2["id"] != r1["id"]

    def test_search_ranks_relevant_first(self):
        ret = self._ret()
        ret.add("python programming language")
        ret.add("cooking pasta recipe")
        results = ret.search("python", top_k=2)
        assert len(results) >= 1
        assert "python" in results[0]["text"].lower()

    def test_search_empty_index(self):
        ret = self._ret()
        assert ret.search("anything") == []

    def test_search_no_query_match_still_returns(self):
        ret = self._ret()
        ret.add("hello world")
        # TF-IDF search returns ranked docs even with weak match
        results = ret.search("zzz", top_k=1)
        assert isinstance(results, list)

    def test_fifo_bound_evicts_oldest(self):
        ret = self._ret(max_docs=3)
        ret.add("first doc")
        ret.add("second doc")
        ret.add("third doc")
        ret.add("fourth doc")
        results = ret.search("fourth", top_k=5)
        texts = [r["text"] for r in results]
        assert "fourth doc" in texts
        assert "first doc" not in texts  # evicted

    def test_set_embedder_injects_semantic(self):
        ret = self._ret()
        # semantic embedder: "exit" and "quit" share [1,0]; "coffee" gets [0,1]
        def embed(t):
            if "exit" in t or "quit" in t:
                return [1.0, 0.0]
            return [0.0, 1.0]
        ret.set_embedder(embed)
        ret.add("exit the assistant")
        ret.add("make coffee")
        results = ret.search("quit", top_k=2)
        assert "exit" in results[0]["text"]

    def test_embedder_none_falls_back_tfidf(self):
        ret = self._ret()
        ret.set_embedder(None)
        ret.add("hello world")
        results = ret.search("hello")
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════════
#  memory_store — Scorer / Decay / ACL
# ═══════════════════════════════════════════════════════════════════


class TestMemoryEntry:
    def test_defaults(self):
        from orbit.orbit.core.memory_store import MemoryEntry

        e = MemoryEntry(key="k", value="v")
        assert e.id  # auto-generated
        assert e.namespace == "global"
        assert e.access_count == 0
        assert e.strength == 1.0
        assert e.created_at
        assert e.last_accessed

    def test_custom_fields(self):
        from orbit.orbit.core.memory_store import MemoryEntry

        e = MemoryEntry(key="proj", value={"a": 1}, source_agent="COD", tags=["code"])
        assert e.source_agent == "COD"
        assert e.value == {"a": 1}
        assert "code" in e.tags


class TestRelevanceScorer:
    def test_score_bounds(self):
        from orbit.orbit.core.memory_store import MemoryEntry, RelevanceScorer

        scorer = RelevanceScorer()
        e = MemoryEntry(key="k", value="v", source_agent="user", access_count=5)
        s = scorer.score(e, "query words")
        assert 0.0 <= s <= 1.0

    def test_user_source_beats_unknown(self):
        from orbit.orbit.core.memory_store import MemoryEntry, RelevanceScorer

        scorer = RelevanceScorer()
        user = MemoryEntry(key="k", value="v", source_agent="user")
        unk = MemoryEntry(key="k", value="v", source_agent="random")
        assert scorer.score(user) > scorer.score(unk)

    def test_fresh_memory_higher_recency(self):
        from orbit.orbit.core.memory_store import MemoryEntry, RelevanceScorer

        scorer = RelevanceScorer()
        fresh = MemoryEntry(key="k", value="v")
        stale = MemoryEntry(key="k", value="v")
        stale.last_accessed = (datetime.now() - timedelta(days=30)).isoformat()
        assert scorer.score(fresh) > scorer.score(stale)

    def test_text_relevance_boosts(self):
        from orbit.orbit.core.memory_store import MemoryEntry, RelevanceScorer

        scorer = RelevanceScorer()
        match = MemoryEntry(key="python", value="tips", tags=["python"])
        nomatch = MemoryEntry(key="garden", value="flowers", tags=["plants"])
        s_match = scorer.score(match, "python tips")
        s_nomatch = scorer.score(nomatch, "python tips")
        assert s_match > s_nomatch

    def test_frequency_normalization(self):
        from orbit.orbit.core.memory_store import MemoryEntry, RelevanceScorer

        scorer = RelevanceScorer()
        high = MemoryEntry(key="k", value="v", access_count=100)
        low = MemoryEntry(key="k", value="v", access_count=1)
        # Isolate frequency from recency (same last_accessed) and calibrate the
        # normalizer: with the default _max_access=1 both frequencies saturate
        # at 1.0 and the comparison degenerates to microsecond recency noise
        # (was flaky: 0.7899999999958741 >= 0.7899999999967909 by luck).
        low.last_accessed = high.last_accessed
        scorer.update_max_access([high, low])
        assert scorer.score(high) > scorer.score(low)

    def test_bad_date_recency_05(self):
        from orbit.orbit.core.memory_store import MemoryEntry, RelevanceScorer

        scorer = RelevanceScorer()
        e = MemoryEntry(key="k", value="v")
        e.last_accessed = "not-a-date"
        assert scorer._recency_score(e) == 0.5


class TestDecayEngine:
    def test_decay_reduces_strength(self):
        from orbit.orbit.core.memory_store import DecayEngine, MemoryEntry

        eng = DecayEngine()
        e = MemoryEntry(key="k", value="v")
        e.last_accessed = (datetime.now() - timedelta(days=14)).isoformat()
        before = e.strength
        eng.apply_decay(e)
        assert e.strength < before

    def test_decay_no_idle_no_change(self):
        from orbit.orbit.core.memory_store import DecayEngine, MemoryEntry

        eng = DecayEngine()
        e = MemoryEntry(key="k", value="v")  # fresh = now
        before = e.strength
        eng.apply_decay(e)
        assert e.strength == pytest.approx(before, abs=0.05)

    def test_reinforce_boosts(self):
        from orbit.orbit.core.memory_store import DecayEngine, MemoryEntry

        eng = DecayEngine()
        e = MemoryEntry(key="k", value="v")
        e.strength = 0.5
        eng.reinforce(e, boost=0.3)
        assert e.strength == pytest.approx(0.8, abs=0.01)
        assert e.access_count == 1

    def test_reinforce_capped_at_1(self):
        from orbit.orbit.core.memory_store import DecayEngine, MemoryEntry

        eng = DecayEngine()
        e = MemoryEntry(key="k", value="v")
        e.strength = 0.9
        eng.reinforce(e, boost=0.5)
        assert e.strength == 1.0

    def test_should_prune_weak(self):
        from orbit.orbit.core.memory_store import DecayEngine, MemoryEntry

        eng = DecayEngine()
        e = MemoryEntry(key="k", value="v")
        e.strength = 0.05
        assert eng.should_prune(e) is True
        e.strength = 0.5
        assert eng.should_prune(e) is False


class TestAccessControl:
    def test_default_read_write(self):
        from orbit.orbit.core.memory_store import AccessControl

        acl = AccessControl()
        assert acl.can_read("QUEEN", "global") is True
        assert acl.can_write("QUEEN", "global") is True

    def test_grant_read_only(self):
        from orbit.orbit.core.memory_store import AccessControl, Permission

        acl = AccessControl()
        acl.grant("WRI", "private", Permission.READ)
        assert acl.can_read("WRI", "private") is True
        assert acl.can_write("WRI", "private") is False

    def test_grant_write_only(self):
        from orbit.orbit.core.memory_store import AccessControl, Permission

        acl = AccessControl()
        acl.grant("COD", "logs", Permission.WRITE)
        assert acl.can_write("COD", "logs") is True
        assert acl.can_read("COD", "logs") is False

    def test_revoke(self):
        from orbit.orbit.core.memory_store import AccessControl, Permission

        acl = AccessControl()
        acl.grant("SEC", "secrets", Permission.READ)
        acl.revoke("SEC", "secrets")
        assert acl.can_read("SEC", "secrets") is True  # back to default
        assert acl.can_write("SEC", "secrets") is True

    def test_revoke_unknown_agent_graceful(self):
        from orbit.orbit.core.memory_store import AccessControl

        acl = AccessControl()
        acl.revoke("NOBODY", "ns")  # must not raise

    def test_permission_enum_values(self):
        from orbit.orbit.core.memory_store import Permission

        assert Permission.READ.value == "read"
        assert Permission.WRITE.value == "write"
        assert Permission.READ_WRITE.value == "read_write"
        assert Permission.NONE.value == "none"


# ═══════════════════════════════════════════════════════════════════
#  memory_consolidation — Fact extraction / merge / search
# ═══════════════════════════════════════════════════════════════════


class TestMemoryFact:
    def test_fact_defaults(self):
        from orbit.orbit.core.memory_consolidation import MemoryFact

        f = MemoryFact(fact="user likes python")
        assert f.fact == "user likes python"
        assert f.importance >= 0
        assert f.access_count >= 0

    def test_fact_increment(self):
        from orbit.orbit.core.memory_consolidation import MemoryFact

        f = MemoryFact(fact="likes python")
        f.access_count += 1
        assert f.access_count == 1


class TestConsolidation:
    def _mc(self, tmp_path):
        from orbit.orbit.core.memory_consolidation import MemoryConsolidation

        return MemoryConsolidation(storage_file=str(tmp_path / "mc.json"))

    def test_score_importance_high(self, tmp_path):
        mc = self._mc(tmp_path)
        high = mc._score_importance("I love you so much, you're my best friend")
        low = mc._score_importance("the the a an")
        assert high > low

    def test_extract_facts(self, tmp_path):
        mc = self._mc(tmp_path)
        memories = [
            {"content": "User prefers Python over JavaScript", "importance": 0.8},
            {"content": "User likes spicy food", "importance": 0.6},
        ]
        facts = mc.extract_facts(memories)
        assert isinstance(facts, list)
        assert all(hasattr(f, "fact") for f in facts)

    def test_extract_facts_min_importance_filter(self, tmp_path):
        mc = self._mc(tmp_path)
        memories = [
            {"content": "Important preference about coding", "importance": 0.9},
            {"content": "Trivial mention", "importance": 0.1},
        ]
        facts = mc.extract_facts(memories, min_importance=0.5)
        assert all(f.importance >= 0.5 for f in facts)

    def test_merge_duplicates(self, tmp_path):
        mc = self._mc(tmp_path)
        mc.add_memory(content="likes python", importance=0.5)
        mc.add_memory(content="likes python a lot", importance=0.6)
        merged = mc.merge_duplicates(similarity_threshold=0.5)
        assert isinstance(merged, int)

    def test_search_facts(self, tmp_path):
        mc = self._mc(tmp_path)
        mc.add_memory(content="User likes Python programming", importance=0.7)
        mc.add_memory(content="User enjoys gardening on weekends", importance=0.5)
        # extract_facts populates _facts (search_facts searches _facts, not _entries)
        mc.extract_facts(
            [
                {"content": "User likes Python programming", "importance": 0.7},
                {"content": "User enjoys gardening on weekends", "importance": 0.5},
            ]
        )
        results = mc.search_facts("python", top_k=3)
        assert isinstance(results, list)
        assert len(results) >= 1
        assert "python" in str(results[0]).lower()

    def test_add_and_recall(self, tmp_path):
        mc = self._mc(tmp_path)
        mc.add_memory(content="Remember the project deadline is Friday", importance=0.8)
        results = mc.recall("deadline", limit=3)
        assert isinstance(results, list)

    def test_consolidate_empty(self, tmp_path):
        mc = self._mc(tmp_path)
        report = mc.consolidate(memories=[])
        assert report is not None

    def test_prune_low_priority(self, tmp_path):
        mc = self._mc(tmp_path)
        mc.add_memory(content="important thing", importance=0.9)
        mc.add_memory(content="unimportant trivia", importance=0.05)
        pruned = mc.prune_low_priority(min_importance=0.3)
        assert isinstance(pruned, int)

    def test_get_insights(self, tmp_path):
        mc = self._mc(tmp_path)
        mc.add_memory(content="learned something new", importance=0.5)
        insights = mc.get_insights(limit=5)
        assert isinstance(insights, list)


# ═══════════════════════════════════════════════════════════════════
#  LLM Router — LLMRequest / analyze_prompt
# ═══════════════════════════════════════════════════════════════════


class TestLLMRequest:
    def test_defaults(self):
        from orbit.orbit.core.llm.router import LLMRequest

        r = LLMRequest(prompt="hello")
        assert r.prompt == "hello"
        assert r.model is None
        assert r.history is None
        assert r.force_offline is False
        assert r.use_cache is True
        assert r.reflect is False
        assert r.debate is False

    def test_all_fields(self):
        from orbit.orbit.core.llm.router import LLMRequest

        r = LLMRequest(
            prompt="test",
            model="llama3.2",
            history=[{"role": "user", "content": "hi"}],
            system_prompt="be helpful",
            extra_context="ctx",
            force_offline=True,
            max_tokens=100,
            use_cache=False,
            category="coding",
            reflect=True,
            max_reflections=3,
            debate=True,
        )
        assert r.model == "llama3.2"
        assert r.force_offline is True
        assert r.max_tokens == 100
        assert r.category == "coding"
        assert r.max_reflections == 3


class TestAnalyzePrompt:
    def test_returns_expected_keys(self):
        from orbit.orbit.core.llm.router import analyze_prompt

        result = analyze_prompt("What is the weather today?")
        assert "query_type" in result
        assert "complexity" in result
        assert "confidence" in result
        assert "chain" in result
        assert "skipped" in result

    def test_confidence_in_bounds(self):
        from orbit.orbit.core.llm.router import analyze_prompt

        result = analyze_prompt("Write a Python function to sort a list")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_coding_prompt_classification(self):
        from orbit.orbit.core.llm.router import analyze_prompt

        result = analyze_prompt("Write a Python function that sorts a list")
        assert result["query_type"] in ("code", "coding", "complex", "reasoning", "general", "math", "creative")

    def test_chain_is_list(self):
        from orbit.orbit.core.llm.router import analyze_prompt

        result = analyze_prompt("simple question")
        assert isinstance(result["chain"], list)
        assert isinstance(result["skipped"], list)

    def test_empty_prompt_graceful(self):
        from orbit.orbit.core.llm.router import analyze_prompt

        result = analyze_prompt("")
        assert isinstance(result, dict)
        assert "query_type" in result


class TestProviderStatus:
    def test_enum_values(self):
        from orbit.orbit.core.llm.router import ProviderStatus

        vals = [s.value for s in ProviderStatus]
        assert len(vals) >= 2  # at least ONLINE/OFFLINE or similar


# ═══════════════════════════════════════════════════════════════════
#  Ground Truth — LaTeX fraction fix regression
# ═══════════════════════════════════════════════════════════════════


class TestGroundTruthFraction:
    def test_latex_frac_half(self):
        from orbit.orbit.core.ground_truth import GroundTruthItem

        item = GroundTruthItem(
            prompt="What is 1/2?",
            answer="0.5",
            number=0.5,
            category="math",
        )
        result = item.check("\\frac{1}{2} = 0.5")
        assert result["numeric_ok"] is True
        assert result["correct"] is True

    def test_plain_fraction(self):
        from orbit.orbit.core.ground_truth import GroundTruthItem

        item = GroundTruthItem(prompt="half?", answer="0.5", number=0.5, category="math")
        result = item.check("it is 1/2")
        assert result["numeric_ok"] is True

    def test_fraction_with_spaces(self):
        from orbit.orbit.core.ground_truth import GroundTruthItem

        item = GroundTruthItem(prompt="q?", answer="0.5", number=0.5, category="math")
        result = item.check("answer is 1 / 2")
        assert result["numeric_ok"] is True

    def test_no_false_positive_on_dates(self):
        from orbit.orbit.core.ground_truth import GroundTruthItem

        # "3/4" fraction when answer is 3.75 — should still evaluate 0.75
        item = GroundTruthItem(prompt="q?", answer="0.75", number=0.75, category="math")
        result = item.check("3/4")
        assert result["numeric_ok"] is True

    def test_divide_by_zero_safe(self):
        from orbit.orbit.core.ground_truth import GroundTruthItem

        item = GroundTruthItem(prompt="q?", answer="0", number=0, category="math")
        result = item.check("x/0")
        assert result["numeric_ok"] is True  # 0 from regular number extraction
