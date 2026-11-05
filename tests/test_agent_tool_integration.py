"""
ORBIT Agent-Tool Integration Tests
====================================
Verifies that each agent ACTUALLY calls its claimed tool when execute() is run,
not just returns a generic LLM response.

Run: py -m pytest tests/test_agent_tool_integration.py -v
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL-WIRED AGENTS — verify tool is actually invoked
# ═══════════════════════════════════════════════════════════════════════════════


class TestTaskAgentIntegration(unittest.TestCase):
    """TAS: TaskAgent should call FileTools for file ops, ComputerTool for system ops."""

    def test_list_files_calls_filetools(self):
        from orbit.orbit.agents.specialized import TaskAgent

        agent = TaskAgent()
        mock_ft = MagicMock()
        mock_ft.list_dir.return_value = {
            "success": True,
            "items": [{"name": "test.txt"}],
        }
        with patch.object(agent, "_get_file_tool", return_value=mock_ft):
            agent.execute("list files in current directory")
            mock_ft.list_dir.assert_called_once()
            self.assertTrue(True)  # execute succeeded without error

    def test_read_file_calls_filetools(self):
        from orbit.orbit.agents.specialized import TaskAgent

        agent = TaskAgent()
        mock_ft = MagicMock()
        mock_ft.read.return_value = {"success": True, "content": "file contents here"}
        with patch.object(agent, "_get_file_tool", return_value=mock_ft):
            agent.execute("read file test.txt")
            mock_ft.read.assert_called_once()
            self.assertTrue(True)  # execute succeeded without error

    def test_system_info_calls_computer_tool(self):
        from orbit.orbit.agents.specialized import TaskAgent

        agent = TaskAgent()
        with patch.object(agent, "_get_tool") as mock_get:
            mock_tool = MagicMock()
            mock_tool.handle_natural.return_value = {
                "success": True,
                "data": "OS: Windows 11",
            }
            mock_get.return_value = mock_tool
            agent.execute("show system info")
            mock_tool.handle_natural.assert_called_once()


class TestCodeAgentIntegration(unittest.TestCase):
    """COD: CodeAgent should call CodeCompletionEngine for completion requests."""

    def test_complete_calls_engine(self):
        from orbit.orbit.agents.specialized import CodeAgent

        agent = CodeAgent()
        mock_engine = MagicMock()
        mock_engine.suggest_completions.return_value = [
            {"text": "suggestion1", "type": "code", "score": 0.9}
        ]
        with (
            patch.object(agent, "_get_completion_engine", return_value=mock_engine),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", unittest.mock.mock_open(read_data="line1\nline2\n")),
        ):
            agent.execute("complete main.py")
            mock_engine.suggest_completions.assert_called_once()

    def test_general_code_query_uses_llm(self):
        from orbit.orbit.agents.specialized import CodeAgent

        agent = CodeAgent()
        with patch("orbit.orbit.agents.task_agents.llm_router") as mock_router:
            mock_router.generate.return_value = "Here is the code..."
            agent.execute("write a python function to sort a list")
            mock_router.generate.assert_called_once()


class TestResearchAgentIntegration(unittest.TestCase):
    """RES: ResearchAgent should call NewsTool for news, WebSearchTool for search."""

    def test_news_query_calls_newstool(self):
        from orbit.orbit.agents.specialized import ResearchAgent

        agent = ResearchAgent()
        with patch.object(agent, "_get_tool") as mock_get:
            mock_tool = MagicMock()
            mock_tool.handle_natural.return_value = (
                "Latest tech news: AI is advancing..."
            )
            mock_get.return_value = mock_tool
            agent.execute("show me the latest news")
            mock_tool.handle_natural.assert_called_once()

    def test_search_query_calls_websearch(self):
        from orbit.orbit.agents.specialized import ResearchAgent

        agent = ResearchAgent()
        with patch.object(agent, "_get_search_tool") as mock_get:
            mock_search = MagicMock()
            mock_search.search.return_value = {
                "results": [
                    {"title": "Result 1", "snippet": "Test", "url": "http://test.com"}
                ]
            }
            mock_get.return_value = mock_search
            agent.execute("search for python tutorials")
            mock_search.search.assert_called_once()


class TestCoordinationAgentIntegration(unittest.TestCase):
    """COA: CoordinationAgent should call N8nTool for workflow commands."""

    def test_workflow_query_calls_n8n(self):
        from orbit.orbit.agents.specialized import CoordinationAgent

        agent = CoordinationAgent()
        with patch.object(agent, "_get_tool") as mock_get:
            mock_tool = MagicMock()
            mock_tool.handle_natural.return_value = (
                "n8n is online. 3 workflows available."
            )
            mock_get.return_value = mock_tool
            agent.execute("list n8n workflows")
            mock_tool.handle_natural.assert_called_once()


class TestDecisionAgentIntegration(unittest.TestCase):
    """DEC: DecisionAgent should call DecisionEngine for analyze/decide queries."""

    def test_analyze_calls_engine(self):
        from orbit.orbit.agents.specialized import DecisionAgent

        agent = DecisionAgent()
        with patch.object(agent, "_get_engine") as mock_get:
            mock_engine = MagicMock()
            mock_engine.analyze.return_value = {
                "winner": "Option A",
                "winner_score": 85.0,
                "confidence": 78.0,
                "recommendation": "Go with Option A",
                "options": [
                    {"name": "Option A", "weighted_total": 85.0, "risk": "low"},
                    {"name": "Option B", "weighted_total": 60.0, "risk": "medium"},
                ],
            }
            mock_get.return_value = mock_engine
            agent.execute("analyze which is better option 'Option A' or 'Option B'")
            mock_engine.analyze.assert_called_once()


class TestSecurityAgentIntegration(unittest.TestCase):
    """SEC: SecurityAgent should call SecurityTool for security commands."""

    def test_security_scan_calls_tool(self):
        from orbit.orbit.agents.specialized import SecurityAgent

        agent = SecurityAgent()
        with patch.object(agent, "_get_tool") as mock_get:
            mock_tool = MagicMock()
            mock_tool.handle_natural.return_value = "SECURITY REPORT: All clear."
            mock_get.return_value = mock_tool
            agent.execute("run security check")
            mock_tool.handle_natural.assert_called_once()


class TestMemoryAgentIntegration(unittest.TestCase):
    """MEM: MemoryAgent should call memory_store functions for memory operations."""

    def test_cleanup_calls_stale_cleanup(self):
        from orbit.orbit.agents.specialized import MemoryAgent

        agent = MemoryAgent()
        with patch(
            "orbit.orbit.agents.utility_agents.cleanup_stale_memories"
        ) as mock_cleanup:
            mock_cleanup.return_value = {"pruned": 5, "remaining": 10}
            agent.execute("cleanup stale memories")
            mock_cleanup.assert_called_once()

    def test_clear_calls_memory_clear(self):
        from orbit.orbit.agents.specialized import MemoryAgent

        agent = MemoryAgent()
        with patch("orbit.orbit.agents.utility_agents.memory_module") as mock_mem:
            agent.execute("clear memory")
            mock_mem.clear.assert_called_once()

    def test_recall_calls_recall_shared(self):
        from orbit.orbit.agents.specialized import MemoryAgent

        agent = MemoryAgent()
        with patch("orbit.orbit.agents.utility_agents.recall_shared") as mock_recall:
            mock_recall.return_value = [
                {
                    "source_agent": "TAS",
                    "value": {"summary": "test memory"},
                    "relevance_score": 0.95,
                }
            ]
            with patch("orbit.orbit.agents.utility_agents.memory_module") as mock_mem:
                mock_mem.get_recent.return_value = []
                agent.execute("recall something")
                mock_recall.assert_called_once()


class TestScreenAgentIntegration(unittest.TestCase):
    """SCR: ScreenAgent should call screen_module for capture/analyze."""

    def test_screen_capture_calls_module(self):
        from orbit.orbit.agents.specialized import ScreenAgent

        agent = ScreenAgent()
        with patch("orbit.orbit.agents.media_agents.screen_module") as mock_screen:
            mock_screen.capture_screen.return_value = "/tmp/screenshot.png"
            mock_screen.analyze_screenshot.return_value = (
                "Screenshot shows a desktop with taskbar"
            )
            agent.execute("take a screenshot")
            mock_screen.capture_screen.assert_called_once()
            mock_screen.analyze_screenshot.assert_called_once()
            mock_screen.cleanup.assert_called_once()

    def test_capture_failure_returns_error(self):
        from orbit.orbit.agents.specialized import ScreenAgent

        agent = ScreenAgent()
        with patch("orbit.orbit.agents.media_agents.screen_module") as mock_screen:
            mock_screen.capture_screen.return_value = None
            agent.execute("take a screenshot")
            self.assertTrue(True)  # execute completed without error


class TestSocialAgentIntegration(unittest.TestCase):
    """SOC: SocialAgent should call N8nTool for social media workflows."""

    def test_workflow_list_calls_n8n(self):
        from orbit.orbit.agents.specialized import SocialAgent

        agent = SocialAgent()
        with patch.object(agent, "_get_tool") as mock_get:
            mock_tool = MagicMock()
            mock_tool.handle_natural.return_value = (
                "📋 2 workflows: social-post, schedule-tweet"
            )
            mock_get.return_value = mock_tool
            agent.execute("list social workflows")
            mock_tool.handle_natural.assert_called()

    def test_post_triggers_n8n_workflow(self):
        from orbit.orbit.agents.specialized import SocialAgent

        agent = SocialAgent()
        with patch.object(agent, "_get_tool") as mock_get:
            mock_tool = MagicMock()
            mock_tool.trigger_workflow_by_name.return_value = (
                "Workflow 'post' triggered via webhook: ✅"
            )
            mock_tool.list_workflows.return_value = [{"name": "post", "id": "1"}]
            mock_get.return_value = mock_tool
            agent.execute("post to social media")
            mock_tool.trigger_workflow_by_name.assert_called()

    def test_n8n_status_check(self):
        from orbit.orbit.agents.specialized import SocialAgent

        agent = SocialAgent()
        with patch.object(agent, "_get_tool") as mock_get:
            mock_tool = MagicMock()
            mock_tool.check_status.return_value = {
                "online": True,
                "url": "http://localhost:5678",
            }
            mock_get.return_value = mock_tool
            agent.execute("check n8n online status")
            mock_tool.check_status.assert_called_once()


class TestMeetingAgentIntegration(unittest.TestCase):
    """MTG: MeetingAgent should call meeting module functions."""

    def test_list_meetings_calls_module(self):
        from orbit.orbit.agents.specialized import MeetingAgent

        agent = MeetingAgent()
        mock_meet = MagicMock()
        mock_meet.list_meetings.return_value = []
        mock_meet.format_meetings.return_value = "No meetings found."
        import sys

        import orbit.orbit

        old_mod = sys.modules.get("orbit.orbit.meeting")
        old_pkg = orbit.orbit.__dict__.get("meeting")
        sys.modules["orbit.orbit.meeting"] = mock_meet
        orbit.orbit.meeting = mock_meet
        try:
            agent.execute("show meetings list")
            mock_meet.list_meetings.assert_called_once()
        finally:
            if old_mod is not None:
                sys.modules["orbit.orbit.meeting"] = old_mod
            else:
                sys.modules.pop("orbit.orbit.meeting", None)
            if old_pkg is not None:
                orbit.orbit.meeting = old_pkg
            else:
                orbit.orbit.__dict__.pop("meeting", None)

    def test_start_meeting_calls_module(self):
        from orbit.orbit.agents.specialized import MeetingAgent

        agent = MeetingAgent()
        mock_meet = MagicMock()
        mock_meet.start_meeting.return_value = {"success": True, "title": "Standup"}
        import sys

        import orbit.orbit

        old_mod = sys.modules.get("orbit.orbit.meeting")
        old_pkg = orbit.orbit.__dict__.get("meeting")
        sys.modules["orbit.orbit.meeting"] = mock_meet
        orbit.orbit.meeting = mock_meet
        try:
            agent.execute("start meeting standup")
            mock_meet.start_meeting.assert_called_once()
        finally:
            if old_mod is not None:
                sys.modules["orbit.orbit.meeting"] = old_mod
            else:
                sys.modules.pop("orbit.orbit.meeting", None)
            if old_pkg is not None:
                orbit.orbit.meeting = old_pkg
            else:
                orbit.orbit.__dict__.pop("meeting", None)


class TestQuarantineAgentIntegration(unittest.TestCase):
    """QNT: QuarantineAgent should call FileTools for quarantine operations."""

    def test_list_quarantine_calls_filetools(self):
        from orbit.orbit.agents.specialized import QuarantineAgent

        agent = QuarantineAgent()
        with patch.object(agent, "_get_file_tool") as mock_get:
            mock_ft = MagicMock()
            mock_ft.list_dir.return_value = {
                "success": True,
                "items": [{"name": "suspect.exe", "size": 1024}],
            }
            mock_get.return_value = mock_ft
            with patch("pathlib.Path.home") as mock_home:
                mock_home.return_value = Path("/tmp/test_home")
                with patch("pathlib.Path.exists", return_value=True):
                    agent.execute("list quarantine")
                    mock_ft.list_dir.assert_called_once()


class TestExecutorAgentIntegration(unittest.TestCase):
    """EXE: ExecutorAgent should call ComputerTool and NewsTool for subtasks."""

    def test_file_subtask_uses_file_tool(self):
        from orbit.orbit.agents.executor_agent import ExecutorAgent

        agent = ExecutorAgent()
        with patch.object(agent, "file_tool") as mock_ft:
            mock_ft.read.return_value = {"success": True, "data": "file contents"}
            agent.execute_subtask(
                {
                    "type": "file",
                    "description": "read test.txt",
                    "params": {"action": "read", "path": "test.txt"},
                }
            )
            mock_ft.read.assert_called_once()

    def test_research_subtask_calls_news_tool(self):
        from orbit.orbit.agents.executor_agent import ExecutorAgent

        agent = ExecutorAgent()
        with (
            patch.object(agent, "news_tool") as mock_nt,
            patch.object(agent, "search_tool") as mock_st,
        ):
            mock_nt.handle_natural.return_value = "Latest news: ..."
            mock_st.search.return_value = {"results": []}
            agent.execute_subtask({"type": "research", "description": "get tech news"})
            mock_nt.handle_natural.assert_called_once()

    def test_code_subtask_uses_llm(self):
        from orbit.orbit.agents.executor_agent import ExecutorAgent

        agent = ExecutorAgent()
        with patch("orbit.orbit.agents.executor_agent.llm_router") as mock_router:
            mock_router.generate.return_value = "def sort(arr): return sorted(arr)"
            agent.execute_subtask(
                {"type": "code", "description": "write a sort function"}
            )
            mock_router.generate.assert_called_once()


class TestPipelineMemoryAgentIntegration(unittest.TestCase):
    """PMA: PipelineMemoryAgent should call memory_store functions."""

    def test_save_result_calls_memory_functions(self):
        from orbit.orbit.agents.memory_agent import PipelineMemoryAgent

        agent = PipelineMemoryAgent()
        with (
            patch("orbit.orbit.agents.memory_agent.memory_module") as mock_mem,
            patch("orbit.orbit.agents.memory_agent.share_memory") as mock_share,
        ):
            entry = agent.save_result(
                task_id=1, subtask_id=1, result="completed", context="test task"
            )
            mock_mem.save_conversation.assert_called_once()
            mock_share.assert_called_once()
            self.assertIn("task_id", str(entry))

    def test_recall_calls_recall_shared(self):
        from orbit.orbit.agents.memory_agent import PipelineMemoryAgent

        agent = PipelineMemoryAgent()
        with patch("orbit.orbit.agents.memory_agent.recall_shared") as mock_recall:
            mock_recall.return_value = [
                {
                    "value": {"timestamp": "2026-01-01", "result": "test"},
                    "source_agent": "PMA",
                }
            ]
            agent.recall(task_id=1)
            mock_recall.assert_called_once()

    def test_run_calls_recall(self):
        from orbit.orbit.agents.memory_agent import PipelineMemoryAgent

        agent = PipelineMemoryAgent()
        with patch.object(agent, "recall") as mock_recall:
            mock_recall.return_value = "No relevant pipeline memories found."
            agent.execute("recall pipeline results")
            mock_recall.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# LLM-ONLY AGENTS — verify they intentionally use LLM, not tools
# ═══════════════════════════════════════════════════════════════════════════════


class TestWritingAgentIntegration(unittest.TestCase):
    """WRI: WritingAgent is intentionally LLM-only — should call llm_router.generate."""

    def test_uses_llm_for_writing(self):
        from orbit.orbit.agents.specialized import WritingAgent

        agent = WritingAgent()
        with patch("orbit.orbit.agents.research_agents.llm_router") as mock_router:
            mock_router.generate.return_value = "Here is your blog post..."
            agent.execute("write a blog post about AI")
            mock_router.generate.assert_called_once()
            self.assertTrue(True)  # execute completed without error


class TestFineTuneAgentIntegration(unittest.TestCase):
    """FTN: FineTuneAgent is intentionally LLM-only."""

    def test_uses_llm_for_finetune(self):
        from orbit.orbit.agents.specialized import FineTuneAgent

        agent = FineTuneAgent()
        with patch("orbit.orbit.agents.research_agents.llm_router") as mock_router:
            mock_router.generate.return_value = (
                "To fine-tune a model, you need training data..."
            )
            agent.execute("fine-tune a model")
            mock_router.generate.assert_called_once()


class TestThumbnailAgentIntegration(unittest.TestCase):
    """THB: ThumbnailAgent is intentionally LLM-only."""

    def test_uses_llm_for_thumbnail(self):
        from orbit.orbit.agents.specialized import ThumbnailAgent

        agent = ThumbnailAgent()
        with patch("orbit.orbit.agents.research_agents.llm_router") as mock_router:
            mock_router.generate.return_value = (
                "Thumbnail design: Bold text, vibrant colors..."
            )
            agent.execute("design a thumbnail for my video")
            mock_router.generate.assert_called_once()


class TestLogAnalystAgentIntegration(unittest.TestCase):
    """LOG: LogAnalystAgent is intentionally LLM-only."""

    def test_uses_llm_for_log_analysis(self):
        from orbit.orbit.agents.specialized import LogAnalystAgent

        agent = LogAnalystAgent()
        with patch("orbit.orbit.agents.utility_agents.llm_router") as mock_router:
            mock_router.generate.return_value = (
                "The error pattern indicates a memory leak..."
            )
            agent.execute("analyze this error log traceback")
            mock_router.generate.assert_called_once()


class TestCouncilAgentIntegration(unittest.TestCase):
    """CNC: CouncilAgent is intentionally LLM-only (5 parallel LLM calls + synthesis)."""

    def test_calls_llm_for_advisors(self):
        from orbit.orbit.agents.council import CouncilAgent

        agent = CouncilAgent()
        with patch("orbit.orbit.agents.council.llm_router") as mock_router:
            mock_router.generate.return_value = "Advisor analysis..."
            agent.execute("council: should I invest in AI startups?")
            self.assertTrue(mock_router.generate.call_count >= 1)


class TestPlannerAgentIntegration(unittest.TestCase):
    """PLN: PlannerAgent is intentionally LLM-only (generates JSON plan)."""

    def test_uses_llm_for_planning(self):
        from orbit.orbit.agents.planner import PlannerAgent

        agent = PlannerAgent()
        with patch("orbit.orbit.agents.planner.llm_router") as mock_router:
            mock_router.generate.return_value = '{"subtasks": [{"id": 1, "type": "research", "description": "search"}], "parallel": false}'
            agent.execute("plan a research task")
            mock_router.generate.assert_called_once()


class TestCriticAgentIntegration(unittest.TestCase):
    """CRT: CriticAgent is intentionally LLM-only (reviews results)."""

    def test_uses_llm_for_review(self):
        from orbit.orbit.agents.critic import CriticAgent

        agent = CriticAgent()
        with patch("orbit.orbit.agents.critic.llm_router") as mock_router:
            mock_router.generate.return_value = (
                '{"quality": "pass", "score": 0.85, "feedback": "Looks good"}'
            )
            agent.execute("review this output")
            mock_router.generate.assert_called_once()


class TestQueenAgentIntegration(unittest.TestCase):
    """QNN: QueenAgent orchestrates via LLM + delegates to other agents."""

    def test_creates_plan_via_llm(self):
        from orbit.orbit.agents.queen import QueenAgent

        agent = QueenAgent()
        with patch.object(
            agent, "_call_qwen", return_value='{"plan": ["TAS"], "parallel": false}'
        ) as mock_qwen:
            plan = agent._generate_plan("list files")
            self.assertIn("plan", plan)
            self.assertEqual(plan["plan"], ["TAS"])
            mock_qwen.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# CAN_HANDLE COVERAGE — verify every agent has can_handle
# ═══════════════════════════════════════════════════════════════════════════════


class TestAllAgentsCanHandle(unittest.TestCase):
    """Every agent should implement can_handle() and respond to its domain keywords."""

    def _check_agent(self, cls, positive_text, negative_text=None):
        agent = cls()
        self.assertTrue(
            agent.can_handle(positive_text),
            f"{cls.__name__} should handle: {positive_text}",
        )
        if negative_text:
            # Not all agents have negative cases (some return True for everything)
            # This is just a sanity check
            result = agent.can_handle(negative_text)
            self.assertIsInstance(result, bool)

    def test_task_agent(self):
        from orbit.orbit.agents.specialized import TaskAgent

        self._check_agent(TaskAgent, "read file and list directory")

    def test_code_agent(self):
        from orbit.orbit.agents.specialized import CodeAgent

        self._check_agent(CodeAgent, "write python code")

    def test_research_agent(self):
        from orbit.orbit.agents.specialized import ResearchAgent

        self._check_agent(ResearchAgent, "search for latest news")

    def test_writing_agent(self):
        from orbit.orbit.agents.specialized import WritingAgent

        self._check_agent(WritingAgent, "write a blog article")

    def test_coordination_agent(self):
        from orbit.orbit.agents.specialized import CoordinationAgent

        self._check_agent(CoordinationAgent, "automate workflow with n8n")

    def test_decision_agent(self):
        from orbit.orbit.agents.specialized import DecisionAgent

        self._check_agent(DecisionAgent, "analyze which option is better")

    def test_security_agent(self):
        from orbit.orbit.agents.specialized import SecurityAgent

        self._check_agent(SecurityAgent, "run security scan")

    def test_memory_agent(self):
        from orbit.orbit.agents.specialized import MemoryAgent

        self._check_agent(MemoryAgent, "recall previous memory")

    def test_screen_agent(self):
        from orbit.orbit.agents.specialized import ScreenAgent

        self._check_agent(ScreenAgent, "take a screenshot of screen")

    def test_social_agent(self):
        from orbit.orbit.agents.specialized import SocialAgent

        self._check_agent(SocialAgent, "post to social media")

    def test_meeting_agent(self):
        from orbit.orbit.agents.specialized import MeetingAgent

        self._check_agent(MeetingAgent, "show meetings list")

    def test_finetune_agent(self):
        from orbit.orbit.agents.specialized import FineTuneAgent

        self._check_agent(FineTuneAgent, "fine-tune training data")

    def test_thumbnail_agent(self):
        from orbit.orbit.agents.specialized import ThumbnailAgent

        self._check_agent(ThumbnailAgent, "design a thumbnail")

    def test_seo_agent(self):
        from orbit.orbit.agents.specialized import SEOAgent

        self._check_agent(SEOAgent, "research seo keywords")

    def test_quarantine_agent(self):
        from orbit.orbit.agents.specialized import QuarantineAgent

        self._check_agent(QuarantineAgent, "quarantine suspicious file")

    def test_log_agent(self):
        from orbit.orbit.agents.specialized import LogAnalystAgent

        self._check_agent(LogAnalystAgent, "analyze error logs")

    def test_council_agent(self):
        from orbit.orbit.agents.council import CouncilAgent

        self._check_agent(CouncilAgent, "council: what do you think")

    def test_planner_agent(self):
        from orbit.orbit.agents.planner import PlannerAgent

        self._check_agent(PlannerAgent, "plan a task")

    def test_executor_agent(self):
        from orbit.orbit.agents.executor_agent import ExecutorAgent

        self._check_agent(ExecutorAgent, "execute this task")

    def test_critic_agent(self):
        from orbit.orbit.agents.critic import CriticAgent

        self._check_agent(CriticAgent, "review this result")

    def test_pma_agent(self):
        from orbit.orbit.agents.memory_agent import PipelineMemoryAgent

        self._check_agent(PipelineMemoryAgent, "recall pipeline results")


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT REGISTRY COMPLETENESS
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentRegistry(unittest.TestCase):
    """Verify AGENT_REGISTRY has all 25 agents and each can be instantiated."""

    def test_registry_has_25_entries(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        self.assertEqual(len(AGENT_REGISTRY), 25)

    def test_all_registry_agents_instantiate(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        for label, cls in AGENT_REGISTRY.items():
            agent = cls()
            self.assertTrue(
                hasattr(agent, "execute"), f"{label} ({cls.__name__}) missing execute()"
            )
            self.assertTrue(
                hasattr(agent, "can_handle"),
                f"{label} ({cls.__name__}) missing can_handle()",
            )
            self.assertTrue(
                hasattr(agent, "_run"), f"{label} ({cls.__name__}) missing _run()"
            )

    def test_all_labels_match(self):
        from orbit.orbit.agents import AGENT_REGISTRY

        expected_labels = {
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
            "SECG",
        }
        self.assertEqual(set(AGENT_REGISTRY.keys()), expected_labels)


if __name__ == "__main__":
    unittest.main(verbosity=2)
