"""Tests for Future-Proof systems: Quant Router + Agent Identity + World State."""

from __future__ import annotations

import json
import os

import pytest


# ── Quant Router ──────────────────────────────────────────────────────────


class TestQuantRouterDetection:
    """is_quant_query detection."""

    def test_arithmetic_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        assert is_quant_query("what is 2 + 2")
        assert is_quant_query("calculate 15 * 240")
        assert is_quant_query("100 - 47")
        assert is_quant_query("2^10")

    def test_percent_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        assert is_quant_query("what is 15% of 240")
        assert is_quant_query("25 percent of 80")

    def test_square_root_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        assert is_quant_query("square root of 144")
        assert is_quant_query("sqrt(169)")

    def test_factorial_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        assert is_quant_query("factorial of 5")
        assert is_quant_query("what is 7!")

    def test_prime_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        assert is_quant_query("is 97 a prime number")

    def test_conceptual_math_not_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        # Conceptual questions go to LLM, not code
        assert not is_quant_query("explain what calculus is")
        assert not is_quant_query("what is the theorem of pythagoras")

    def test_chitchat_not_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        assert not is_quant_query("hello how are you")
        assert not is_quant_query("tell me a joke")

    def test_empty_not_detected(self):
        from orbit.orbit.core.quant_router import is_quant_query

        assert not is_quant_query("")
        assert not is_quant_query("   ")


class TestQuantRouterCodeGen:
    """_generate_code from natural language."""

    def test_percent_code(self):
        from orbit.orbit.core.quant_router import _generate_code

        code = _generate_code("what is 15% of 240")
        assert code is not None
        assert "print" in code

    def test_sqrt_code(self):
        from orbit.orbit.core.quant_router import _generate_code

        code = _generate_code("square root of 144")
        assert code is not None
        assert "math.sqrt" in code or "sqrt" in code

    def test_factorial_code(self):
        from orbit.orbit.core.quant_router import _generate_code

        code = _generate_code("factorial of 5")
        assert code is not None
        assert "factorial" in code

    def test_prime_code(self):
        from orbit.orbit.core.quant_router import _generate_code

        code = _generate_code("is 97 a prime number")
        assert code is not None
        assert "prime" in code

    def test_direct_arithmetic(self):
        from orbit.orbit.core.quant_router import _generate_code

        code = _generate_code("2 + 2")
        assert code is not None
        assert "print" in code


class TestQuantRouterSolve:
    """solve() via code interpreter."""

    def test_solve_arithmetic(self):
        from orbit.orbit.core.quant_router import get_quant_router

        r = get_quant_router().solve("what is 2 + 2")
        assert r.success
        assert "4" in r.output
        assert r.exact is True
        assert r.source == "code"

    def test_solve_percent(self):
        from orbit.orbit.core.quant_router import get_quant_router

        r = get_quant_router().solve("what is 15% of 240")
        assert r.success
        assert "36" in r.output

    def test_solve_sqrt(self):
        from orbit.orbit.core.quant_router import get_quant_router

        r = get_quant_router().solve("square root of 144")
        assert r.success
        assert "12" in r.output

    def test_solve_factorial(self):
        from orbit.orbit.core.quant_router import get_quant_router

        r = get_quant_router().solve("factorial of 5")
        assert r.success
        assert "120" in r.output

    def test_solve_prime(self):
        from orbit.orbit.core.quant_router import get_quant_router

        r = get_quant_router().solve("is 97 a prime number")
        assert r.success
        assert "prime" in r.output.lower()

    def test_solve_unsolvable(self):
        from orbit.orbit.core.quant_router import get_quant_router

        r = get_quant_router().solve("what is the meaning of life")
        assert not r.success
        assert r.exact is False

    def test_cache_hit(self):
        from orbit.orbit.core.quant_router import get_quant_router

        router = get_quant_router()
        r1 = router.solve("what is 7 * 8")
        r2 = router.solve("what is 7 * 8")
        assert r1.success
        assert r2.success
        assert r1.output == r2.output

    def test_stats(self):
        from orbit.orbit.core.quant_router import get_quant_router

        router = get_quant_router()
        stats = router.get_stats()
        assert "total" in stats
        assert "code_routed" in stats


class TestQuantRouterConvenience:
    """route_quant convenience function."""

    def test_route_quant_math(self):
        from orbit.orbit.core.quant_router import route_quant

        r = route_quant("what is 3 * 3")
        assert r is not None
        assert r.success
        assert "9" in r.output

    def test_route_quant_chitchat(self):
        from orbit.orbit.core.quant_router import route_quant

        r = route_quant("hello there")
        assert r is None


# ── Agent Identity ────────────────────────────────────────────────────────


class TestAgentIdentity:
    """AgentIdentity card."""

    def test_identity_creation(self):
        from orbit.orbit.core.agent_identity import AgentIdentity

        ident = AgentIdentity(
            code="TAS",
            name="TaskAgent",
            role="System + file operations",
            trust_level="HIGH",
            capabilities=["file_read", "file_write"],
        )
        assert ident.code == "TAS"
        assert ident.agent_id.startswith("did:orbit:")

    def test_identity_sign_verify(self):
        from orbit.orbit.core.agent_identity import AgentIdentity

        ident = AgentIdentity(
            code="COD", name="CodeAgent", role="Code gen", trust_level="HIGH"
        )
        sig = ident.sign()
        assert sig
        assert ident.verify()

    def test_identity_tamper_detected(self):
        from orbit.orbit.core.agent_identity import AgentIdentity

        ident = AgentIdentity(
            code="SEC", name="SecurityAgent", role="Threats", trust_level="CRITICAL"
        )
        ident.sign()
        assert ident.verify()
        # Tamper with trust level
        ident.trust_level = "BLOCKED"
        assert not ident.verify()

    def test_identity_to_dict(self):
        from orbit.orbit.core.agent_identity import AgentIdentity

        ident = AgentIdentity(
            code="RES", name="ResearchAgent", role="Research", trust_level="MEDIUM"
        )
        ident.sign()
        d = ident.to_dict()
        assert d["code"] == "RES"
        assert d["agent_id"].startswith("did:orbit:")
        assert d["signature"]


class TestAgentIdentityManager:
    """AgentIdentityManager registry."""

    def test_registry_has_all_agents(self):
        from orbit.orbit.core.agent_identity import get_identity_manager

        mgr = get_identity_manager()
        agents = mgr.get_all()
        codes = {a.code for a in agents}
        # All 25 agents + QUEEN + SECG + ROUTER
        assert "TAS" in codes
        assert "QUEEN" in codes
        assert "SECG" in codes
        assert "ROUTER" in codes
        assert len(agents) >= 25

    def test_get_identity(self):
        from orbit.orbit.core.agent_identity import get_identity_manager

        ident = get_identity_manager().get("TAS")
        assert ident is not None
        assert ident.name == "TaskAgent"

    def test_get_verified(self):
        from orbit.orbit.core.agent_identity import get_identity_manager

        ident = get_identity_manager().get_verified("QUEEN")
        assert ident is not None
        assert ident.verify()

    def test_record_action(self):
        from orbit.orbit.core.agent_identity import get_identity_manager

        mgr = get_identity_manager()
        before = mgr.get("TAS").actions_count
        entry = mgr.record_action("TAS", "file_write", "wrote test.txt")
        assert entry["agent_code"] == "TAS"
        assert entry["action"] == "file_write"
        after = mgr.get("TAS").actions_count
        assert after == before + 1

    def test_audit_trail(self):
        from orbit.orbit.core.agent_identity import get_identity_manager

        mgr = get_identity_manager()
        mgr.record_action("COD", "code_gen", "generated function")
        trail = mgr.get_audit_trail(code="COD", limit=5)
        assert len(trail) >= 1
        assert trail[-1]["agent_code"] == "COD"

    def test_stats(self):
        from orbit.orbit.core.agent_identity import get_identity_manager

        stats = get_identity_manager().get_stats()
        assert stats["total_agents"] >= 25
        assert stats["verified"] >= 25
        assert "trust_distribution" in stats

    def test_export_registry(self):
        from orbit.orbit.core.agent_identity import get_identity_manager

        reg = get_identity_manager().export_registry()
        assert reg["version"] == "1.0"
        assert len(reg["agents"]) >= 25


# ── World State ───────────────────────────────────────────────────────────


class TestWorldState:
    """WorldState snapshot."""

    def test_snapshot(self):
        from orbit.orbit.core.world_state import get_world_state

        state = get_world_state()
        assert state.timestamp
        assert state.local_time
        assert state.day_of_week
        assert state.time_of_day in ("morning", "afternoon", "evening", "night")
        assert state.os_info
        assert state.python_version

    def test_to_dict(self):
        from orbit.orbit.core.world_state import get_world_state

        d = get_world_state().to_dict()
        assert "time" in d
        assert "system" in d
        assert "network" in d
        assert "agents" in d
        assert d["time"]["day_of_week"]
        assert d["time"]["period"]

    def test_brief(self):
        from orbit.orbit.core.world_state import get_world_state

        brief = get_world_state().brief()
        assert "Time:" in brief
        assert "System:" in brief

    def test_cache(self):
        from orbit.orbit.core.world_state import get_world_state_manager

        mgr = get_world_state_manager()
        s1 = mgr.snapshot()
        s2 = mgr.snapshot()  # cached
        assert s1.timestamp == s2.timestamp

    def test_force_fresh(self):
        from orbit.orbit.core.world_state import get_world_state_manager

        mgr = get_world_state_manager()
        s1 = mgr.snapshot()
        s2 = mgr.snapshot(force=True)
        # Forced snapshot is a new object (timestamp may be same if instant)
        assert s2 is not None

    def test_stats(self):
        from orbit.orbit.core.world_state import get_world_state_manager

        stats = get_world_state_manager().get_stats()
        assert "snapshots_taken" in stats


# ── Future Blueprint API ──────────────────────────────────────────────────


class TestFutureBlueprint:
    """Flask API endpoints for all 3 systems."""

    @pytest.fixture()
    def client(self):
        os.environ["ORBIT_API_AUTH_ENABLED"] = "0"
        from orbit.orbit.server import create_app

        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()

    def test_quant_solve_api(self, client):
        resp = client.post(
            "/api/future/quant/solve",
            json={"query": "what is 2 + 2"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "4" in data["output"]

    def test_quant_solve_empty(self, client):
        resp = client.post("/api/future/quant/solve", json={"query": ""})
        assert resp.status_code == 400

    def test_quant_check_api(self, client):
        resp = client.post(
            "/api/future/quant/check",
            json={"query": "what is 15% of 240"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_quant"] is True
        assert data["generated_code"]

    def test_quant_stats_api(self, client):
        resp = client.get("/api/future/quant/stats")
        assert resp.status_code == 200

    def test_identity_registry_api(self, client):
        resp = client.get("/api/future/identity")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["version"] == "1.0"
        assert len(data["agents"]) >= 25

    def test_identity_card_api(self, client):
        resp = client.get("/api/future/identity/TAS")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["code"] == "TAS"
        assert data["signature_valid"] is True

    def test_identity_card_unknown(self, client):
        resp = client.get("/api/future/identity/NOPE")
        assert resp.status_code == 404

    def test_identity_stats_api(self, client):
        resp = client.get("/api/future/identity/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_agents"] >= 25

    def test_identity_audit_api(self, client):
        resp = client.get("/api/future/identity/audit?limit=5")
        assert resp.status_code == 200

    def test_world_state_api(self, client):
        resp = client.get("/api/future/world")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "time" in data
        assert "system" in data

    def test_world_brief_api(self, client):
        resp = client.get("/api/future/world/brief")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "brief" in data

    def test_future_status_api(self, client):
        resp = client.get("/api/future/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "quant_router" in data
        assert "agent_identity" in data
        assert "world_state" in data


# ── Agentic Integration ───────────────────────────────────────────────────


class TestQuantInAgentic:
    """Quant Router wired into agentic chat."""

    def test_quant_tool_registered(self):
        from orbit.orbit.core.agentic_chat import TOOL_REGISTRY

        assert "quant_solve" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["quant_solve"]["fn"])

    def test_quant_tool_execution(self):
        from orbit.orbit.core.agentic_chat import execute_tool

        result = execute_tool("quant_solve", {"query": "what is 3 * 3"})
        assert "9" in result
        assert "EXACT ANSWER" in result

    def test_quant_trigger_agentic(self):
        from orbit.orbit.core.agentic_chat import should_go_agentic

        assert should_go_agentic("what is 15% of 240")
        assert should_go_agentic("calculate 2^10")
        assert should_go_agentic("square root of 256")
