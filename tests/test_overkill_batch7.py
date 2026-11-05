"""Tests for Overkill Batch 7: Agent Tool Wiring, New Blueprints, Server Fixes."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestFineTuneAgentWiring(unittest.TestCase):
    """FTN agent now wired to FileTools + WebSearchTool."""

    def test_import(self):
        from orbit.orbit.agents.specialized import FineTuneAgent

        self.assertTrue(FineTuneAgent)

    def test_file_tool_init(self):
        from orbit.orbit.agents.specialized import FineTuneAgent

        agent = FineTuneAgent()
        self.assertTrue(hasattr(agent, "_get_file_tool"))
        ft = agent._get_file_tool()
        self.assertTrue(hasattr(ft, "write"))

    def test_search_tool_init(self):
        from orbit.orbit.agents.specialized import FineTuneAgent

        agent = FineTuneAgent()
        self.assertTrue(hasattr(agent, "_get_search_tool"))
        st = agent._get_search_tool()
        self.assertTrue(hasattr(st, "search"))

    def test_can_handle(self):
        from orbit.orbit.agents.specialized import FineTuneAgent

        agent = FineTuneAgent()
        self.assertTrue(agent.can_handle("fine-tune my model for training data"))
        self.assertTrue(agent.can_handle("train a dataset for model training"))
        self.assertTrue(agent.can_handle("evaluate model benchmark"))
        self.assertFalse(agent.can_handle("hello world"))

    def test_has_history(self):
        from orbit.orbit.agents.specialized import FineTuneAgent

        agent = FineTuneAgent()
        self.assertIsInstance(agent.history, list)


class TestThumbnailAgentWiring(unittest.TestCase):
    """THB agent now wired to FileTools + WebSearchTool."""

    def test_import(self):
        from orbit.orbit.agents.specialized import ThumbnailAgent

        self.assertTrue(ThumbnailAgent)

    def test_file_tool_init(self):
        from orbit.orbit.agents.specialized import ThumbnailAgent

        agent = ThumbnailAgent()
        ft = agent._get_file_tool()
        self.assertTrue(hasattr(ft, "write"))

    def test_search_tool_init(self):
        from orbit.orbit.agents.specialized import ThumbnailAgent

        agent = ThumbnailAgent()
        st = agent._get_search_tool()
        self.assertTrue(hasattr(st, "search"))

    def test_can_handle(self):
        from orbit.orbit.agents.specialized import ThumbnailAgent

        agent = ThumbnailAgent()
        self.assertTrue(agent.can_handle("design a thumbnail"))
        self.assertTrue(agent.can_handle("yt thumbnail for video"))
        self.assertFalse(agent.can_handle("hello world"))


class TestPlannerAgentWiring(unittest.TestCase):
    """PLN agent now wired to FileTools for saving plans."""

    def test_import(self):
        from orbit.orbit.agents.planner import PlannerAgent

        self.assertTrue(PlannerAgent)

    def test_file_tool_init(self):
        from orbit.orbit.agents.planner import PlannerAgent

        agent = PlannerAgent()
        ft = agent._get_file_tool()
        self.assertTrue(hasattr(ft, "write"))

    def test_can_handle(self):
        from orbit.orbit.agents.planner import PlannerAgent

        agent = PlannerAgent()
        self.assertTrue(agent.can_handle("anything"))


class TestCriticAgentWiring(unittest.TestCase):
    """CRT agent now wired to FileTools for saving reports."""

    def test_import(self):
        from orbit.orbit.agents.critic import CriticAgent

        self.assertTrue(CriticAgent)

    def test_file_tool_init(self):
        from orbit.orbit.agents.critic import CriticAgent

        agent = CriticAgent()
        ft = agent._get_file_tool()
        self.assertTrue(hasattr(ft, "write"))

    def test_review_basic(self):
        from orbit.orbit.agents.critic import CriticAgent

        agent = CriticAgent()
        verdict = agent.review({"type": "test", "description": "test"}, "Hello world")
        self.assertIn("quality", verdict)
        self.assertIn("score", verdict)
        self.assertIn(verdict["quality"], ["pass", "fail", "retry"])

    def test_needs_retry(self):
        from orbit.orbit.agents.critic import CriticAgent

        agent = CriticAgent()
        self.assertFalse(agent.needs_retry({"quality": "pass"}, 0))
        self.assertTrue(agent.needs_retry({"quality": "retry"}, 0))
        self.assertFalse(agent.needs_retry({"quality": "fail"}, 1))


class TestCouncilAgentWiring(unittest.TestCase):
    """CNC agent now wired to FileTools for saving reports."""

    def test_import(self):
        from orbit.orbit.agents.council import CouncilAgent

        self.assertTrue(CouncilAgent)

    def test_file_tool_init(self):
        from orbit.orbit.agents.council import CouncilAgent

        agent = CouncilAgent()
        ft = agent._get_file_tool()
        self.assertTrue(hasattr(ft, "write"))

    def test_can_handle(self):
        from orbit.orbit.agents.council import CouncilAgent

        agent = CouncilAgent()
        self.assertTrue(agent.can_handle("council: should I invest in AI?"))
        self.assertFalse(agent.can_handle("hello world"))


class TestStreamingTTSBlueprint(unittest.TestCase):
    """New streaming_tts blueprint endpoints."""

    def test_import(self):
        from orbit.streaming_tts_bp import streaming_tts_bp

        self.assertTrue(streaming_tts_bp)

    def test_blueprint_name(self):
        from orbit.streaming_tts_bp import streaming_tts_bp

        self.assertEqual(streaming_tts_bp.name, "streaming_tts")


class TestAgentMemoryBlueprint(unittest.TestCase):
    """New agentmemory blueprint endpoints."""

    def test_import(self):
        from orbit.agentmemory_bp import agentmemory_bp

        self.assertTrue(agentmemory_bp)

    def test_blueprint_name(self):
        from orbit.agentmemory_bp import agentmemory_bp

        self.assertEqual(agentmemory_bp.name, "agentmemory")


class TestSkillLibraryBlueprint(unittest.TestCase):
    """New skill_library blueprint endpoints."""

    def test_import(self):
        from orbit.skill_library_bp import skill_library_bp

        self.assertTrue(skill_library_bp)

    def test_blueprint_name(self):
        from orbit.skill_library_bp import skill_library_bp

        self.assertEqual(skill_library_bp.name, "skill_library")


class TestNaturoBlueprint(unittest.TestCase):
    """New naturo blueprint endpoints."""

    def test_import(self):
        from orbit.naturo_bp import naturo_bp

        self.assertTrue(naturo_bp)

    def test_blueprint_name(self):
        from orbit.naturo_bp import naturo_bp

        self.assertEqual(naturo_bp.name, "naturo")


class TestContextWindowManagerFixes(unittest.TestCase):
    """RLock fix + release fix verification."""

    def test_rlock_type(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            self.assertIn("RLock", type(cwm._lock).__name__)
        finally:
            os.unlink(path)

    def test_release_zeroes_tokens(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            cwm.register_agent("TAS")
            cwm.request_tokens("TAS", 5000)
            cwm.release("TAS")
            alloc = cwm.get_allocation("TAS")
            self.assertEqual(alloc["allocated_tokens"], 0)
            self.assertEqual(alloc["used_tokens"], 0)
        finally:
            os.unlink(path)

    def test_no_deadlock_on_request(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            cr = cwm.request_tokens("NEW_AGENT", 1000)
            self.assertEqual(cr.status, "granted")
            self.assertGreater(cr.granted_tokens, 0)
        finally:
            os.unlink(path)

    def test_rebalance_after_register(self):
        from orbit.orbit.core.context_window_manager import ContextWindowManager

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cwm = ContextWindowManager(storage_file=path)
            cwm.register_agent("A", priority=10)
            cwm.register_agent("B", priority=1)
            cwm.request_tokens("A", 5000)
            cwm.request_tokens("B", 5000)
            ov = cwm.get_overview()
            a_tokens = ov["allocations"]["A"]["tokens"]
            b_tokens = ov["allocations"]["B"]["tokens"]
            self.assertGreaterEqual(a_tokens, b_tokens)
        finally:
            os.unlink(path)


class TestServerAllBlueprintsRegistered(unittest.TestCase):
    """Verify ALL blueprints load successfully."""

    def test_all_core_blueprints_load(self):
        from orbit.orbit.server import create_app

        app = create_app()
        names = list(app.blueprints)
        core_bps = [
            "rag_bp",
            "cost_optimizer",
            "agent_debate",
            "tool_analytics",
            "skill_learning",
            "hybrid_memory",
            "smart_browser",
            "task_fanout",
            "moa",
            "streaming_tts",
            "marketplace_v2",
            "battle",
            "pdf",
            "self_improvement",
            "memory_consolidation",
            "request_tracing",
            "semantic_cache",
            "prompt_optimizer_bp",
            "conversation_summarizer",
            "response_evaluator",
            "webhook_system_bp",
            "code_interpreter",
            "memory_graph",
            "anomaly_detector",
            "smart_scheduler",
            "doc_pipeline",
            "plugin_bridge",
            "conv_analytics",
            "model_benchmark",
            "file_watcher",
            "context_mgr",
            "mcp_bp",
            "desktop_bp",
            "github_bp",
        ]
        for bp in core_bps:
            self.assertIn(bp, names, f"Blueprint '{bp}' missing")

    def test_direct_blueprints_load(self):
        from orbit.orbit.server import create_app

        app = create_app()
        names = list(app.blueprints)
        direct_bps = [
            "permissions",
            "settings",
            "chat",
            "agents",
            "tech_scout",
            "pipeline",
            "self_test",
            "briefing",
            "memory_upgrade",
            "watchdog",
            "updater",
            "multimodal",
            "knowledge",
            "conversation",
            "skills",
            "analytics",
            "voice",
            "n8n_integration",
            "security_hardening",
            "mobile",
            "reasoning",
            "goals",
            "decision",
            "time",
            "experimentation_framework_bp",
            "version",
            "notification_center",
            "universal_search",
            "daily_digest",
            "context_menu",
            "boot_report",
            "honest_metrics_bp",
            "email_bp",
            "calendar_bp",
            "cai_security_bp",
            "providers_bp",
            "seo_bp",
        ]
        for bp in direct_bps:
            self.assertIn(bp, names, f"Direct blueprint '{bp}' missing")

    def test_total_blueprint_count(self):
        from orbit.orbit.server import create_app

        app = create_app()
        count = len(app.blueprints)
        self.assertGreaterEqual(count, 60, f"Expected 60+ blueprints, got {count}")


class TestAgentRegistryComplete(unittest.TestCase):
    """Verify all 24 agents in registry."""

    def test_all_agents_present(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        expected = [
            "QUEEN",
            "TAS",
            "COD",
            "RES",
            "WRI",
            "COA",
            "DEC",
            "SEC",
            "MEM",
            "SCR",
            "SOC",
            "MTG",
            "FTN",
            "THB",
            "SEO",
            "QNT",
            "LOG",
            "CNC",
            "PLN",
            "EXE",
            "PMA",
            "CRT",
            "HRM",
            "MMA",
        ]
        for label in expected:
            self.assertIn(
                label, AGENT_REGISTRY, f"Agent '{label}' missing from registry"
            )

    def test_registry_count(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        self.assertEqual(len(AGENT_REGISTRY), 25)

    def test_all_agents_instantiate(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        for label, cls in AGENT_REGISTRY.items():
            try:
                agent = cls()
                self.assertTrue(hasattr(agent, "can_handle"))
                self.assertTrue(hasattr(agent, "_run"))
            except Exception as e:  # noqa: BLE001
                self.fail(f"Agent {label} failed to instantiate: {e}")


if __name__ == "__main__":
    unittest.main()
