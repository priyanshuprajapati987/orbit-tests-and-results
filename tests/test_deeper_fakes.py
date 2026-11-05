"""Regression tests for deeper faked-feature fixes (security-battle cleanup).

- PatternDetector persists/restores REAL learned entries (not 0.5 placeholders).
- SolutionPatternIndexer.measure_improvement is derived from input + labeled estimated.
- OpportunityScout returns real/empty data (no hardcoded canned trends/gaps/competitors).
- MixtureOfAgents wires real providers and synthesizes from registered callables.
"""

import json
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def test_pattern_detector_persists_real_entries(tmp_path):
    from orbit.orbit.core.realtime_learning import PatternDetector

    pd = PatternDetector()
    pd.record("python loop", "resp a", 0.9)
    pd.record("python loop", "resp b", 0.2)
    pd.record("python loop", "resp c", 0.7)

    p = tmp_path / "patterns.json"
    pd.save(p)
    assert p.exists()

    pd2 = PatternDetector()
    pd2.load(p)
    # Real entries restored (not a constant 0.5 placeholder list).
    assert pd2.query_patterns["python loop"] == [0.9, 0.2, 0.7]
    assert 0.9 in pd2.query_patterns["python loop"]
    assert all(x != 0.5 for x in pd2.query_patterns["python loop"])


def test_measure_improvement_derived_and_labeled():
    from orbit.orbit.core.solution_pattern_indexer import SolutionPatternIndexer

    idx = SolutionPatternIndexer.__new__(SolutionPatternIndexer)  # avoid heavy init
    out = idx.measure_improvement(
        "Use caching and batch retries to optimize",
        {"success_rate": 0.8, "time_taken": 2.0},
    )
    assert out["estimated"] is True
    # Improvement should be positive because the adaptation contains action words.
    assert out["success_rate"] > 0.8
    assert out["time_taken"] < 2.0

    out_empty = idx.measure_improvement("", {"success_rate": 0.8, "time_taken": 2.0})
    # No actionable words -> no improvement over baseline.
    assert out_empty["success_rate"] == 0.8


def test_opportunity_scout_no_hardcoded_data(monkeypatch):
    import orbit.orbit.core.safe_http as safe_http_mod
    from orbit.orbit.core import opportunity_scout as os_mod

    # Force the underlying safe HTTP client to fail -> scanners must return
    # real/empty data, never canned constants.
    def boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(safe_http_mod, "safe_requests_get", boom)

    scout = os_mod.OpportunityScan.__new__(os_mod.OpportunityScan)
    tech = scout.scan_tech_trends(["python", "llm", "agents"])
    gaps = scout.scan_market_gaps()
    comp = scout.scan_competitor_moves()
    # No fabricated "LangGraph"/"$5B opportunity"/"OpenAI o1" artifacts.
    assert tech == []
    assert gaps == []
    assert comp == []
    blob = json.dumps(tech + gaps + comp)
    assert "LangGraph" not in blob and "$5B" not in blob


def test_opportunity_scout_tech_scoring_with_real_item():
    from orbit.orbit.core import opportunity_scout as os_mod

    scout = os_mod.OpportunityScan.__new__(os_mod.OpportunityScan)
    items = [
        {
            "name": "Foo",
            "description": "python llm agents framework",
            "category": "python",
            "stars": 1234,
        }
    ]
    rel = scout._score_relevance(items[0], ["python", "llm", "agents"])
    assert rel >= 0.6  # real scoring works on provided (real) item


def test_moa_synthesizes_from_registered_provider():
    from orbit.orbit.core.mixture_of_agents import EnsembleResult, MixtureOfAgents

    moa = MixtureOfAgents()
    moa.register_provider("fake_a", lambda p: "Answer part A: 42")
    moa.register_provider("fake_b", lambda p: "Answer part B: 42")

    res = moa.query("What is 42?", strategy="voting")
    assert isinstance(res, EnsembleResult)
    assert "42" in res.final_answer
    assert len(res.responses) == 2
    assert res.consensus_score >= 0.0


def test_moa_register_default_providers_wires_real_router(monkeypatch):
    from orbit.orbit.core.mixture_of_agents import MixtureOfAgents

    captured = {}

    class FakeResp:
        success = True
        content = "ok"

    class FakeRouter:
        def generate(self, req):
            captured.setdefault("calls", []).append(req.model)
            return FakeResp()

    import orbit.orbit.core.llm.router as rmod

    monkeypatch.setattr(rmod, "get_router", lambda: FakeRouter())

    moa = MixtureOfAgents()
    moa.register_default_providers()
    providers = moa.get_providers()
    assert "ollama" in providers and "openrouter" in providers
    # Actually invoke one provider through the (mocked) real router.
    out = moa._providers["ollama"]("hi")
    assert out == "ok"
    assert "ollama" in captured["calls"]
