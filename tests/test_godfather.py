"""Tests for Godfather systems: Swarm Council + Self-Evolution + Predictive Engine."""

from __future__ import annotations

import os

import pytest


# ── Swarm Council ─────────────────────────────────────────────────────────


class TestSwarmCouncilClassification:
    """Query classification for council routing."""

    def test_code_query(self):
        from orbit.orbit.core.swarm_council import _classify_query

        assert _classify_query("write a python function to sort a list") == "code"
        assert _classify_query("debug this API error") == "code"

    def test_research_query(self):
        from orbit.orbit.core.swarm_council import _classify_query

        assert _classify_query("latest news on AI") == "research"
        assert _classify_query("research the current trends") == "research"

    def test_creative_query(self):
        from orbit.orbit.core.swarm_council import _classify_query

        assert _classify_query("write a poem about the sea") == "creative"
        assert _classify_query("create a blog post about AI") == "creative"

    def test_security_query(self):
        from orbit.orbit.core.swarm_council import _classify_query

        assert _classify_query("is this encryption secure") == "security"
        assert _classify_query("vulnerability in my code") == "security"

    def test_planning_query(self):
        from orbit.orbit.core.swarm_council import _classify_query

        assert _classify_query("plan a roadmap for my project") == "planning"
        assert _classify_query("create a strategy for growth") == "planning"

    def test_general_fallback(self):
        from orbit.orbit.core.swarm_council import _classify_query

        assert _classify_query("tell me something interesting") == "general"


class TestSwarmCouncilRouting:
    """Advisor routing based on query type."""

    def test_code_advisors(self):
        from orbit.orbit.core.swarm_council import _COUNCIL_ROUTING

        advisors = _COUNCIL_ROUTING["code"]
        assert "COD" in advisors
        assert "CRT" in advisors

    def test_research_advisors(self):
        from orbit.orbit.core.swarm_council import _COUNCIL_ROUTING

        advisors = _COUNCIL_ROUTING["research"]
        assert "RES" in advisors
        assert "DEC" in advisors

    def test_advisor_profiles_exist(self):
        from orbit.orbit.core.swarm_council import ADVISORS, _COUNCIL_ROUTING

        # Every advisor in routing must have a profile
        for cat, codes in _COUNCIL_ROUTING.items():
            for code in codes:
                assert code in ADVISORS, f"{code} in {cat} routing has no profile"

    def test_advisor_system_prompt(self):
        from orbit.orbit.core.swarm_council import ADVISORS

        adv = ADVISORS["COD"]
        prompt = adv.system_prompt("write a function")
        assert "CodeAgent" in prompt
        assert "code generation" in prompt
        assert "write a function" in prompt


class TestSwarmCouncilExecution:
    """Council execution (with mocked LLM)."""

    @pytest.fixture()
    def mock_generate(self, monkeypatch):
        calls = []

        def fake_generate(prompt, system_prompt=None, **kwargs):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return f"Mock response to: {prompt[:50]}"

        import orbit.orbit.core.swarm_council as sc

        # Patch at the module level where it's imported
        import orbit.orbit.core.llm.legacy_adapter as la

        monkeypatch.setattr(la, "generate", fake_generate)
        return calls

    def test_convene_minimal(self, mock_generate):
        from orbit.orbit.core.swarm_council import convene_council

        result = convene_council(
            "write a python sorting function",
            category="code",
            max_advisors=3,
            with_critic=False,
            with_synthesis=False,
        )
        assert result.category == "code"
        assert len(result.advisors_used) == 3
        assert len(result.responses) == 3
        # Without synthesis, synthesis is empty
        assert result.synthesis == ""

    def test_convene_with_critic(self, mock_generate):
        from orbit.orbit.core.swarm_council import convene_council

        result = convene_council(
            "what is the best security practice?",
            category="security",
            max_advisors=3,
            with_critic=True,
            with_synthesis=False,
        )
        assert result.critic_review
        assert len(result.responses) == 3

    def test_convene_full(self, mock_generate):
        from orbit.orbit.core.swarm_council import convene_council

        result = convene_council(
            "how to plan a project roadmap?",
            category="planning",
            max_advisors=4,
            with_critic=True,
            with_synthesis=True,
        )
        assert result.synthesis
        assert result.critic_review
        assert result.total_latency_ms >= 0

    def test_result_to_dict(self, mock_generate):
        from orbit.orbit.core.swarm_council import convene_council

        result = convene_council("test query", category="general", max_advisors=3)
        d = result.to_dict()
        assert d["category"] == "general"
        assert len(d["responses"]) == 3
        assert "synthesis" in d

    def test_stats_tracking(self, mock_generate):
        from orbit.orbit.core.swarm_council import get_council

        council = get_council()
        before = council.get_stats()["total_convened"]
        council.convene("test query", category="general", max_advisors=3)
        after = council.get_stats()["total_convened"]
        assert after == before + 1


class TestSwarmCouncilNoLLM:
    """Council with LLM unavailable — graceful degradation."""

    def test_convene_no_llm(self, monkeypatch):
        import orbit.orbit.core.llm.legacy_adapter as la

        def fail_generate(*args, **kwargs):
            raise RuntimeError("LLM unavailable")

        monkeypatch.setattr(la, "generate", fail_generate)

        from orbit.orbit.core.swarm_council import convene_council

        result = convene_council(
            "test query", category="general",
            max_advisors=3, with_critic=True, with_synthesis=True,
        )
        # Advisors fail gracefully
        assert all(not r.success for r in result.responses)
        # Synthesis falls back
        assert result.synthesis == "" or "unavailable" in result.synthesis.lower()


# ── Self-Evolution ────────────────────────────────────────────────────────


class TestWeaknessDetection:
    """Weakness detection from data sources."""

    def test_no_data_no_weaknesses(self, tmp_path, monkeypatch):
        from orbit.orbit.core import self_evolution

        # Point data dir to empty tmp
        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        weaknesses = self_evolution._detect_weaknesses()
        assert isinstance(weaknesses, list)
        # Empty data dir → no weaknesses
        assert len(weaknesses) == 0

    def test_weak_gt_detected(self, tmp_path, monkeypatch):
        import json

        from orbit.orbit.core import self_evolution

        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        # Write a GT eval with weak category
        gt = {"per_category": {"math": {"accuracy": 0.65}}}
        (tmp_path / "ground_truth_eval.json").write_text(json.dumps(gt))
        weaknesses = self_evolution._detect_weaknesses()
        gt_weak = [w for w in weaknesses if w.category == "accuracy:math"]
        assert len(gt_weak) == 1
        assert gt_weak[0].current_value == 0.65
        assert gt_weak[0].severity == "critical"  # < 0.7

    def test_strong_gt_no_weakness(self, tmp_path, monkeypatch):
        import json

        from orbit.orbit.core import self_evolution

        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        gt = {"per_category": {"math": {"accuracy": 0.98}}}
        (tmp_path / "ground_truth_eval.json").write_text(json.dumps(gt))
        weaknesses = self_evolution._detect_weaknesses()
        assert len(weaknesses) == 0

    def test_battle_weakness_detected(self, tmp_path, monkeypatch):
        import json

        from orbit.orbit.core import self_evolution

        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        battle = {
            "rounds": [{"winner": "jarvus"}] * 5 + [{"winner": "opponent"}] * 5,
            "by_category": {"creative": {"win_rate": 0.5}},
        }
        (tmp_path / "battle_v2_latest.json").write_text(json.dumps(battle))
        weaknesses = self_evolution._detect_weaknesses()
        assert any(w.category == "battle:overall" for w in weaknesses)
        assert any(w.category == "battle:creative" for w in weaknesses)


class TestActionGeneration:
    """Action generation from weaknesses."""

    def test_accuracy_weakness(self):
        from orbit.orbit.core.self_evolution import Weakness, _generate_actions

        w = Weakness("accuracy:reasoning", "major", "gt_accuracy", 0.7, 0.9)
        actions = _generate_actions([w])
        assert len(actions) == 1
        assert actions[0].action_type == "prompt_rewrite"
        assert "reasoning" in actions[0].payload["category"]

    def test_routing_weakness(self):
        from orbit.orbit.core.self_evolution import Weakness, _generate_actions

        w = Weakness("routing:groq", "major", "provider_success_rate", 0.6, 0.95)
        actions = _generate_actions([w])
        assert len(actions) == 1
        assert actions[0].action_type == "routing_tweak"
        assert actions[0].payload["provider"] == "groq"

    def test_tool_weakness(self):
        from orbit.orbit.core.self_evolution import Weakness, _generate_actions

        w = Weakness("tool:code_interpreter", "major", "tool_success_rate", 0.7, 0.9)
        actions = _generate_actions([w])
        assert len(actions) == 1
        assert actions[0].action_type == "tool_fix"

    def test_deduplication(self):
        from orbit.orbit.core.self_evolution import Weakness, _generate_actions

        w1 = Weakness("accuracy:reasoning", "minor", "gt", 0.8, 0.9)
        w2 = Weakness("accuracy:reasoning", "major", "gt", 0.6, 0.9)
        actions = _generate_actions([w1, w2])
        # Deduplicated — only one action for the same category
        assert len(actions) == 1
        # Higher confidence kept
        assert actions[0].confidence >= 0.5


class TestPromptStore:
    """EvolvedPromptStore CRUD + rollback."""

    def test_set_get(self, tmp_path):
        from orbit.orbit.core.self_evolution import EvolvedPromptStore

        store = EvolvedPromptStore(path=tmp_path / "prompts.json")
        store.set_prompt("reasoning", "Think step by step")
        assert store.get_prompt("reasoning") == "Think step by step"

    def test_get_missing(self, tmp_path):
        from orbit.orbit.core.self_evolution import EvolvedPromptStore

        store = EvolvedPromptStore(path=tmp_path / "prompts.json")
        assert store.get_prompt("nonexistent") is None

    def test_rollback(self, tmp_path):
        from orbit.orbit.core.self_evolution import EvolvedPromptStore

        store = EvolvedPromptStore(path=tmp_path / "prompts.json")
        store.set_prompt("coding", "Original prompt")
        store.set_prompt("coding", "Improved prompt")
        assert store.get_prompt("coding") == "Improved prompt"
        assert store.rollback("coding")
        assert store.get_prompt("coding") == "Original prompt"

    def test_rollback_no_previous(self, tmp_path):
        from orbit.orbit.core.self_evolution import EvolvedPromptStore

        store = EvolvedPromptStore(path=tmp_path / "prompts.json")
        store.set_prompt("coding", "First prompt")
        assert not store.rollback("coding")  # No previous to roll back to

    def test_persistence(self, tmp_path):
        from orbit.orbit.core.self_evolution import EvolvedPromptStore

        path = tmp_path / "prompts.json"
        store = EvolvedPromptStore(path=path)
        store.set_prompt("math", "Show calculation steps")

        # New store from same path
        store2 = EvolvedPromptStore(path=path)
        assert store2.get_prompt("math") == "Show calculation steps"


class TestEvolutionEngine:
    """SelfEvolutionEngine cycle execution."""

    def test_run_cycle_dry(self, tmp_path, monkeypatch):
        from orbit.orbit.core import self_evolution

        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        engine = self_evolution.SelfEvolutionEngine()
        report = engine.run_cycle(dry_run=True)
        assert report["cycle_id"] >= 1
        assert report["dry_run"] is True
        assert report["weaknesses_found"] == 0  # Empty data

    def test_run_cycle_apply(self, tmp_path, monkeypatch):
        from orbit.orbit.core import self_evolution

        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        engine = self_evolution.SelfEvolutionEngine()
        report = engine.run_cycle(dry_run=False)
        assert report["cycle_id"] >= 1
        assert report["dry_run"] is False

    def test_stats(self, tmp_path, monkeypatch):
        from orbit.orbit.core import self_evolution

        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        engine = self_evolution.SelfEvolutionEngine()
        engine.run_cycle(dry_run=True)
        stats = engine.get_stats()
        assert stats["total_cycles"] >= 1

    def test_history(self, tmp_path, monkeypatch):
        from orbit.orbit.core import self_evolution

        monkeypatch.setattr(self_evolution, "_data_dir", lambda: tmp_path)
        engine = self_evolution.SelfEvolutionEngine()
        engine.run_cycle(dry_run=True)
        history = engine.get_history()
        assert len(history) >= 1
        assert history[-1]["cycle_id"] >= 1


# ── Predictive Engine ─────────────────────────────────────────────────────


class TestPatternLearner:
    """PatternLearner time/transition learning."""

    def test_record_action(self):
        from orbit.orbit.core.predictive_engine import PatternLearner

        learner = PatternLearner()
        learner.record("read file")
        stats = learner.get_stats()
        assert stats["total_observations"] == 1

    def test_transition_prediction(self):
        from orbit.orbit.core.predictive_engine import PatternLearner

        learner = PatternLearner()
        # Same transition 3 times
        for _ in range(3):
            learner.record("write file")
            learner.record("run tests")
        preds = learner.predict_next("write file")
        assert len(preds) >= 1
        assert preds[0][0] == "run tests"
        assert preds[0][1] >= 0.5  # High confidence

    def test_time_prediction(self):
        from orbit.orbit.core.predictive_engine import PatternLearner

        learner = PatternLearner()
        # Record actions at current time
        for _ in range(5):
            learner.record("check email")
        preds = learner.predict_by_time()
        assert len(preds) >= 1
        assert preds[0][0] == "check email"

    def test_empty_no_prediction(self):
        from orbit.orbit.core.predictive_engine import PatternLearner

        learner = PatternLearner()
        assert learner.predict_next("unknown") == []
        assert learner.predict_by_time() == []


class TestPredictiveEngine:
    """PredictiveEngine predictions."""

    def test_record_and_predict(self):
        from orbit.orbit.core.predictive_engine import PredictiveEngine

        engine = PredictiveEngine()
        for _ in range(3):
            engine.record_action("write code")
            engine.record_action("run tests")
        preds = engine.get_predictions()
        assert isinstance(preds, list)
        # Should have next_action predictions
        types = {p["type"] for p in preds}
        assert "next_action" in types or len(preds) == 0

    def test_filter_by_type(self):
        from orbit.orbit.core.predictive_engine import PredictiveEngine

        engine = PredictiveEngine()
        engine.record_action("test")
        preds = engine.get_predictions(ptype="nonexistent_type")
        assert preds == []

    def test_min_confidence_filter(self):
        from orbit.orbit.core.predictive_engine import PredictiveEngine

        engine = PredictiveEngine()
        engine.record_action("test")
        preds = engine.get_predictions(min_confidence=0.99)
        assert all(p["confidence"] >= 0.99 for p in preds)

    def test_stats(self):
        from orbit.orbit.core.predictive_engine import PredictiveEngine

        engine = PredictiveEngine()
        engine.record_action("some action")
        stats = engine.get_stats()
        assert stats["total_observations"] == 1
        assert "active_predictions" in stats


# ── Godfather Blueprint API ───────────────────────────────────────────────


class TestGodfatherBlueprint:
    """Flask API for all 3 Godfather systems."""

    @pytest.fixture()
    def client(self):
        os.environ["ORBIT_API_AUTH_ENABLED"] = "0"
        from orbit.orbit.server import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()

    def test_status(self, client):
        resp = client.get("/api/godfather/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "swarm_council" in data
        assert "self_evolution" in data
        assert "predictive_engine" in data

    def test_council_stats(self, client):
        resp = client.get("/api/godfather/council/stats")
        assert resp.status_code == 200

    def test_council_requires_query(self, client):
        resp = client.post("/api/godfather/council", json={"query": ""})
        assert resp.status_code == 400

    def test_evolve_dry_run(self, client):
        resp = client.post("/api/godfather/evolve", json={"dry_run": True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is True

    def test_evolve_stats(self, client):
        resp = client.get("/api/godfather/evolve/stats")
        assert resp.status_code == 200

    def test_evolve_history(self, client):
        resp = client.get("/api/godfather/evolve/history")
        assert resp.status_code == 200

    def test_evolve_prompts(self, client):
        resp = client.get("/api/godfather/evolve/prompts")
        assert resp.status_code == 200

    def test_rollback_requires_category(self, client):
        resp = client.post("/api/godfather/evolve/rollback", json={})
        assert resp.status_code == 400

    def test_predict_empty(self, client):
        resp = client.get("/api/godfather/predict")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "predictions" in data

    def test_predict_record(self, client):
        resp = client.post(
            "/api/godfather/predict/record", json={"action": "test action"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["recorded"] is True

    def test_predict_record_requires_action(self, client):
        resp = client.post("/api/godfather/predict/record", json={})
        assert resp.status_code == 400

    def test_predict_stats(self, client):
        resp = client.get("/api/godfather/predict/stats")
        assert resp.status_code == 200
