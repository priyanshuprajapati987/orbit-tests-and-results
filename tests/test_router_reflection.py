"""Regression tests: LLM router self-reflection / self-correction loop.

- When reflect=True and the first answer is weak (hedged / truncated / shallow), the
  router performs one bounded refinement pass and returns the improved answer (refined=True).
- When the answer is already good, no extra generation happens (refined=False).
- The assessment combines heuristics + CoT-depth; confidence is attached.
- reflect=False (benchmark path) never triggers a refinement pass.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


class _FakeResp:
    def __init__(self, content, success=True):
        self.content = content
        self.provider = "ollama"
        self.model = "test"
        self.latency_ms = 1
        self.success = success
        self.error = None
        self.used_cache = False
        self.confidence = None
        self.refined = False
        self.critique = None
        self.counter_arguments = None


class _FakeRouter:
    """Simulates the provider chain. Returns queued answers in order."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.calls = []

    async def _generate_with_failover(self, request):
        self.calls.append(request)
        if self._answers:
            return self._answers.pop(0)
        return _FakeResp("fallback", success=True)

    async def generate(self, request):
        # minimal mirror of generate() reflection wiring is not needed; tests call
        # _maybe_reflect directly on a real router subclass.
        return await self._generate_with_failover(request)


def _real_router_with(answers):
    """Build a real LLMRouter whose _generate_with_failover yields canned answers."""
    import orbit.orbit.core.llm.router as rmod

    class Stub(rmod.LLMRouter):
        def __init__(self):
            super().__init__()
            self.calls = []
            self._q = list(answers)

        async def _generate_with_failover(self, request):
            self.calls.append(request)
            if self._q:
                return self._q.pop(0)
            return _FakeResp("fallback", success=True)

    return Stub()


def test_reflect_refines_weak_answer():
    from orbit.orbit.core.llm.router import LLMRequest

    weak = _FakeResp("I'm sorry, I'm not sure about the answer.")
    good = _FakeResp(
        "The capital of Australia is Canberra. It is the political capital."
    )
    router = _real_router_with([weak, good])

    req = LLMRequest(
        prompt="What is the capital of Australia?", reflect=True, max_reflections=1
    )
    import asyncio

    out = asyncio.run(router.generate(req))

    # A refinement generation must have been triggered.
    assert len(router.calls) == 2
    assert out.refined is True
    assert out.confidence is not None
    # Final content should be the improved (2nd) answer.
    assert "Canberra" in out.content


def test_reflect_skips_when_answer_good():
    from orbit.orbit.core.llm.router import LLMRequest

    good = _FakeResp(
        "Photosynthesis converts light energy into chemical energy in chloroplasts."
    )
    router = _real_router_with([good])

    req = LLMRequest(
        prompt="Explain photosynthesis briefly.", reflect=True, max_reflections=1
    )
    import asyncio

    out = asyncio.run(router.generate(req))

    assert len(router.calls) == 1
    assert out.refined is False


def test_reflect_false_never_refines():
    from orbit.orbit.core.llm.router import LLMRequest

    weak = _FakeResp("I'm not sure, sorry.")
    router = _real_router_with([weak])

    req = LLMRequest(prompt="Solve 2+2.", reflect=False)
    import asyncio

    out = asyncio.run(router.generate(req))

    assert len(router.calls) == 1
    assert out.refined is False


def test_assess_quality_flags_hedge():
    from orbit.orbit.core.llm.router import LLMRequest, LLMResponse

    resp = LLMResponse(
        content="I'm sorry, as an AI I cannot help with that.",
        provider="ollama",
        model="m",
        latency_ms=1,
    )
    score, needs, _reason = LLMRouterProbe()._assess_quality(
        LLMRequest(prompt="hack something"), resp
    )
    assert needs is True
    assert score < 0.55


class LLMRouterProbe:
    from orbit.orbit.core.llm.router import LLMRouter as _B

    def _assess_quality(self, *a, **k):
        return self._B._assess_quality(*a, **k)


def test_debate_runs_critic_and_reconcile():
    from orbit.orbit.core.llm.router import LLMRequest

    initial = _FakeResp("The capital of Australia is Canberra.")
    critic = _FakeResp(
        "Bullet 1: You didn't mention it's not the largest city.\n"
        "Bullet 2: You omitted that it's in the ACT."
    )
    reconciled = _FakeResp(
        "The capital of Australia is Canberra, in the ACT. "
        "Note: it is the political capital, not the largest city."
    )
    router = _real_router_with([initial, critic, reconciled])

    req = LLMRequest(
        prompt="What is the capital of Australia?",
        reflect=True,
        max_reflections=1,
        debate=True,
        use_cache=False,
    )
    import asyncio

    out = asyncio.run(router.generate(req))

    # initial + critic + reconcile = 3 calls.
    assert len(router.calls) == 3
    assert out.counter_arguments is not None
    assert "ACT" in out.content
    assert out.refined is True


def test_debate_no_strong_counter_returns_original():
    from orbit.orbit.core.llm.router import LLMRequest

    initial = _FakeResp("Photosynthesis converts light into chemical energy.")
    critic = _FakeResp("NO STRONG COUNTER-ARGUMENTS.")
    router = _real_router_with([initial, critic])

    req = LLMRequest(
        prompt="Explain photosynthesis.", reflect=False, debate=True, use_cache=False
    )
    import asyncio

    out = asyncio.run(router.generate(req))

    # Only initial + critic; reconcile skipped because critic found nothing.
    assert len(router.calls) == 2
    assert out.counter_arguments is not None
    assert "Photosynthesis" in out.content
    # Not rewritten by a reconcile step.
    assert "chemical energy" in out.content


def test_debate_false_never_calls_critic():
    from orbit.orbit.core.llm.router import LLMRequest

    initial = _FakeResp("2 + 2 = 4.")
    router = _real_router_with([initial])

    req = LLMRequest(prompt="Solve 2+2.", reflect=False, debate=False, use_cache=False)
    import asyncio

    out = asyncio.run(router.generate(req))

    assert len(router.calls) == 1
    assert out.counter_arguments is None
