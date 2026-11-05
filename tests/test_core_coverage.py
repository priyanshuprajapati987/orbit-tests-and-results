"""Tests for critical core modules that lack test coverage."""



class TestSmartRouter:
    def test_import(self):
        from orbit.orbit.core.smart_router import SmartRouter

        assert SmartRouter is not None

    def test_route_general_query(self):
        from orbit.orbit.core.smart_router import SmartRouter

        router = SmartRouter()
        r = router.route("hello how are you")
        assert r.intent in ("general", "chat", "none")

    def test_route_file_query(self):
        from orbit.orbit.core.smart_router import SmartRouter

        router = SmartRouter()
        r = router.route("read file test.txt")
        assert r.is_tool_command

    def test_route_code_query(self):
        from orbit.orbit.core.smart_router import SmartRouter

        router = SmartRouter()
        r = router.route("write a python function to sort a list")
        assert any(a.label == "COD" for a in r.agents)

    def test_route_research_query(self):
        from orbit.orbit.core.smart_router import SmartRouter

        router = SmartRouter()
        r = router.route("search google for quantum computing news")
        assert any(a.label == "RES" for a in r.agents)

    def test_route_security_query(self):
        from orbit.orbit.core.smart_router import SmartRouter

        router = SmartRouter()
        r = router.route("run a security scan on ports")
        assert r.is_tool_command

    def test_negation_detection(self):
        from orbit.orbit.core.smart_router import SmartRouter, _has_negation

        router = SmartRouter()
        # Negation within 5 words before keyword is detected
        assert _has_negation("do not write a python script", 7)
        assert not _has_negation("please write a python script", 7)
        assert _has_negation("never search for that", 9)

    def test_route_result_to_dict(self):
        from orbit.orbit.core.smart_router import RouteResult

        r = RouteResult()
        d = r.to_dict()
        assert isinstance(d, dict)
        assert "intent" in d

    def test_topic_followup_boost(self):
        from orbit.orbit.core.smart_router import SmartRouter

        router = SmartRouter()
        # First query establishes topic
        r1 = router.route("write a python function to sort a list")
        # Follow-up should boost the same agent
        r2 = router.route("and also make it handle edge cases")
        if r1.agents and r2.agents:
            # topic_followup should appear in reason if same agent
            if r1.agents[0].label == r2.agents[0].label:
                assert (
                    "topic_followup" in r2.agents[0].reason
                    or r2.agents[0].score >= r1.agents[0].score
                )

    def test_topic_memory_persistence(self):
        from orbit.orbit.core.smart_router import SmartRouter

        router = SmartRouter()
        router.route("write a python function")
        router.route("search the web for docs")
        assert len(router._recent_topics) == 2
        assert router._recent_topics[-1] in ("RES", "COD")


class TestConversationOptimizer:
    def test_import(self):
        from orbit.orbit.core.conversation_optimizer import ConversationOptimizer

        assert ConversationOptimizer is not None

    def test_singleton(self):
        from orbit.orbit.core.conversation_optimizer import get_conversation_optimizer

        a = get_conversation_optimizer()
        b = get_conversation_optimizer()
        assert a is b


class TestContextManager:
    def test_import(self):
        from orbit.orbit.core.context_manager import ContextManager

        assert ContextManager is not None


class TestTokenBudget:
    def test_import(self):
        from orbit.orbit.core.token_budget import estimate_tokens

        assert estimate_tokens is not None

    def test_estimate_tokens(self):
        from orbit.orbit.core.token_budget import estimate_tokens

        assert estimate_tokens("hello world") > 0
        assert estimate_tokens("") == 0


class TestSemanticSimilarity:
    def test_import(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        assert semantic_similarity is not None

    def test_identical_text(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        score = semantic_similarity("hello world", "hello world")
        assert score >= 0.99

    def test_disjoint_text(self):
        from orbit.orbit.core.semantic_similarity import semantic_similarity

        score = semantic_similarity("cats are furry", "math is abstract")
        assert score < 0.5


class TestReasoningDepth:
    def test_import(self):
        from orbit.orbit.core.reasoning_depth import analyze_reasoning

        assert analyze_reasoning is not None

    def test_analyze_simple(self):
        from orbit.orbit.core.reasoning_depth import analyze_reasoning

        result = analyze_reasoning(
            "The answer is 42 because it is the answer to everything."
        )
        assert "depth_score" in result


class TestFallbackChain:
    def test_import(self):
        from orbit.orbit.core.fallback_chain import FallbackChain

        assert FallbackChain is not None


class TestReliability:
    def test_import(self):
        from orbit.orbit.core.reliability import QuotaTracker

        assert QuotaTracker is not None


class TestCircuitBreaker:
    def test_import(self):
        from orbit.orbit.core.circuit_breaker import CircuitBreaker

        assert CircuitBreaker is not None


class TestMonitoring:
    def test_import(self):
        from orbit.orbit.core.monitoring import UptimeTracker

        assert UptimeTracker is not None


class TestGroundTruth:
    def test_import(self):
        from orbit.orbit.core.ground_truth import GROUND_TRUTH

        assert len(GROUND_TRUTH) > 0

    def test_answer_matching(self):
        from orbit.orbit.core.ground_truth import GROUND_TRUTH

        # Find a math item
        math_items = [item for item in GROUND_TRUTH if item.category == "math"]
        assert len(math_items) > 0


class TestBattle:
    def test_import(self):
        from orbit.orbit.core.battle import load_prompts

        assert load_prompts is not None

    def test_load_prompts(self):
        from orbit.orbit.core.battle import load_prompts

        prompts = load_prompts(quick=True)
        assert len(prompts) > 0
        assert len(prompts) <= 30


class TestOptimization:
    def test_import(self):
        from orbit.orbit.core.optimization import get_optimizer

        assert get_optimizer is not None

    def test_feed_battle_to_router(self):
        from orbit.orbit.core.optimization import CompetitiveOptimizer

        opt = CompetitiveOptimizer()
        payload = {
            "categories": {
                "coding": {
                    "results": [
                        {"prompt": "sort a list", "composite": {"winner": "jarvus"}},
                        {
                            "prompt": "reverse a string",
                            "composite": {"winner": "opponent"},
                        },
                    ]
                }
            }
        }
        fed = opt.feed_battle_to_router(payload)
        assert fed == 2


class TestSelfImprovement:
    def test_repeated_failures(self):
        from orbit.orbit.core.self_improvement_v2 import FailureAnalyzer

        fa = FailureAnalyzer()
        # Record multiple failures to trigger pattern
        for i in range(4):
            fa.analyze(
                failure_id=f"test_{i}",
                agent_id="COD",
                input_text="write code",
                actual_output="error occurred",
                error_message="tool failure timeout",
            )
        repeated = fa.get_repeated_failures(min_count=3)
        assert len(repeated) >= 1
        assert repeated[0]["agent"] == "COD"
        assert repeated[0]["count"] >= 3
        assert "suggestion" in repeated[0]


class TestProactiveAssistant:
    def test_topic_tracking(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        pa.record_topic("coding task")
        assert pa._current_topic == "coding task"
        assert pa._topic_start is not None
        pa.record_topic("research task")
        assert pa._current_topic == "research task"
        assert len(pa._work_sessions) == 1

    def test_error_tracking(self):
        from orbit.orbit.core.proactive_assistant import ProactiveAssistant

        pa = ProactiveAssistant()
        pa.record_error("timeout error")
        assert len(pa._error_log) == 1
        assert not pa._error_log[0][2]  # not resolved
        pa.mark_error_resolved("timeout error")
        assert pa._error_log[0][2]  # resolved
