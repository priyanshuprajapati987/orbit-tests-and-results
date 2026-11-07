"""Unit tests for orbit/orbit/agents/utility_agents.py (7 agents, all mocked)."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.agents.utility_agents import (
    QuarantineAgent,
    LogAnalystAgent,
    CoordinationAgent,
    DecisionAgent,
    SecurityAgent,
    SecurityGuardAgent,
    MemoryAgent,
    HermesAgent,
)


class TestQuarantineAgent(unittest.TestCase):
    def setUp(self):
        self.agent = QuarantineAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "QNT")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("quarantine the suspicious file"))
        self.assertFalse(self.agent.can_handle("hello"))

    def test_quarantine_success(self):
        ft = MagicMock()
        ft.copy.return_value = {"success": True}
        ft.delete.return_value = {"success": True}
        with patch.object(self.agent, "_get_file_tool", return_value=ft):
            r = self.agent.execute("quarantine file foo.txt")
        self.assertIn("File quarantined", r)
        ft.copy.assert_called_once()
        ft.delete.assert_called_once()

    def test_quarantine_delete_blocked(self):
        ft = MagicMock()
        ft.copy.return_value = {"success": True}
        ft.delete.return_value = {"success": False, "error": "permission"}
        with patch.object(self.agent, "_get_file_tool", return_value=ft):
            r = self.agent.execute("quarantine file foo.txt")
        self.assertIn("copied to quarantine", r)
        self.assertIn("original delete blocked", r)

    def test_quarantine_copy_fail(self):
        ft = MagicMock()
        ft.copy.return_value = {"success": False, "error": "disk full"}
        with patch.object(self.agent, "_get_file_tool", return_value=ft):
            r = self.agent.execute("quarantine file foo.txt")
        self.assertIn("Quarantine failed: disk full", r)

    def test_quarantine_copy_non_dict(self):
        ft = MagicMock()
        ft.copy.return_value = "weird"
        with patch.object(self.agent, "_get_file_tool", return_value=ft):
            r = self.agent.execute("quarantine file foo.txt")
        self.assertIn("Quarantine failed: copy returned weird", r)

    def test_quarantine_no_file(self):
        ft = MagicMock()
        with patch.object(self.agent, "_get_file_tool", return_value=ft), \
             patch.object(self.agent, "_get_tool", return_value=None):
            r = self.agent.execute("quarantine something")
        self.assertEqual(r, "Quarantine agent: security tool unavailable.")

    def test_list_quarantine_missing_dir(self):
        with patch.object(self.agent, "_quarantine_dir", return_value=__import__("pathlib").Path("/tmp/does/not/exist/xyz")):
            r = self.agent.execute("list quarantine")
        self.assertIn("doesn't exist yet", r)

    def test_restore_not_found(self):
        with patch.object(self.agent, "_quarantine_dir", return_value=__import__("pathlib").Path("/tmp/does/not/exist/xyz")):
            r = self.agent.execute("restore foo.txt")
        self.assertIn("not found in quarantine", r)

    def test_restore_no_filename(self):
        r = self.agent.execute("restore")
        self.assertIn("Which file should I restore", r)

    def test_security_tool_fallback(self):
        tool = MagicMock()
        tool.handle_natural.return_value = {"result": "tool result"}
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("scan this")
        self.assertEqual(r, "tool result")

    def test_security_tool_non_dict(self):
        tool = MagicMock()
        tool.handle_natural.return_value = "plain result"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("scan this")
        self.assertEqual(r, "plain result")

    def test_security_tool_unavailable(self):
        with patch.object(self.agent, "_get_tool", return_value=None):
            r = self.agent.execute("scan this")
        self.assertEqual(r, "Quarantine agent: security tool unavailable.")


class TestLogAnalystAgent(unittest.TestCase):
    def setUp(self):
        self.agent = LogAnalystAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "LOG")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("analyze error log"))
        self.assertFalse(self.agent.can_handle("hello world"))

    def test_run_with_file(self):
        ft = MagicMock()
        ft.read.return_value = {"content": "line1\nline2\nERROR here"}
        with patch.object(self.agent, "_get_file_tool", return_value=ft), \
             patch("orbit.agents.utility_agents.llm_router.generate", return_value="analysis") as gen:
            r = self.agent.execute("analyze app.log please")
        self.assertEqual(r, "analysis")
        self.assertIn("[Log Content]", gen.call_args.kwargs["system_prompt"])

    def test_run_read_error(self):
        ft = MagicMock()
        ft.read.return_value = {"error": "permission denied"}
        with patch.object(self.agent, "_get_file_tool", return_value=ft):
            r = self.agent.execute("analyze app.log")
        self.assertIn("Could not read app.log", r)

    def test_run_fallback_llm(self):
        with patch.object(self.agent, "_get_file_tool", return_value=MagicMock()), \
             patch("orbit.agents.utility_agents.llm_router.generate", return_value="llm text") as gen:
            r = self.agent.execute("what went wrong")
        self.assertEqual(r, "llm text")
        self.assertIn("LOG ANALYST", gen.call_args.kwargs["system_prompt"])


class TestCoordinationAgent(unittest.TestCase):
    def setUp(self):
        self.agent = CoordinationAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "COA")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("run n8n workflow now"))
        self.assertFalse(self.agent.can_handle("hello"))

    def test_run_tool_result(self):
        tool = MagicMock()
        tool.handle_natural.return_value = "workflow triggered"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("trigger workflow")
        self.assertEqual(r, "workflow triggered")

    def test_run_tool_empty(self):
        tool = MagicMock()
        tool.handle_natural.return_value = ""
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("trigger workflow")
        self.assertEqual(r, "Coordination task completed (no detailed response).")

    def test_run_tool_unavailable(self):
        with patch.object(self.agent, "_get_tool", return_value=None):
            r = self.agent.execute("trigger workflow")
        self.assertEqual(r, "Coordination agent: n8n tool unavailable.")


class TestDecisionAgent(unittest.TestCase):
    def setUp(self):
        self.agent = DecisionAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "DEC")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("compare pros and cons"))
        self.assertFalse(self.agent.can_handle("hello"))

    def test_analyze_quoted_options(self):
        engine = MagicMock()
        engine.analyze.return_value = {
            "winner": "A", "winner_score": 80.0, "confidence": 70.0,
            "recommendation": "Pick A", "options": [{"name": "A", "weighted_total": 80.0, "risk": "low"}],
        }
        with patch.object(self.agent, "_get_engine", return_value=engine):
            r = self.agent.execute('analyze "Option A" "Option B"')
        self.assertIn("Winner: A", r)
        self.assertIn("Pick A", r)
        self.assertIn("80.0/100", r)

    def test_analyze_default_options(self):
        engine = MagicMock()
        engine.analyze.return_value = {
            "winner": "Option A", "winner_score": 50.0, "confidence": 60.0,
            "recommendation": "go A", "options": [{"name": "Option A", "weighted_total": 50.0, "risk": "med"}],
        }
        with patch.object(self.agent, "_get_engine", return_value=engine):
            r = self.agent.execute("analyze between two things")
        self.assertIn("Winner: Option A", r)

    def test_fallback_llm(self):
        with patch("orbit.agents.utility_agents.llm_router.generate", return_value="llm decision") as gen:
            r = self.agent.execute("tell me something")
        self.assertEqual(r, "llm decision")
        self.assertIn("DECISION specialist", gen.call_args.kwargs["system_prompt"])


class TestSecurityAgent(unittest.TestCase):
    def setUp(self):
        self.agent = SecurityAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "SEC")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("scan for virus threats"))
        self.assertFalse(self.agent.can_handle("hello world"))

    def test_run_dict_result(self):
        tool = MagicMock()
        tool.handle_natural.return_value = {"result": "no threats"}
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("scan system")
        self.assertEqual(r, "no threats")

    def test_run_non_dict_result(self):
        tool = MagicMock()
        tool.handle_natural.return_value = "plain"
        with patch.object(self.agent, "_get_tool", return_value=tool):
            r = self.agent.execute("scan system")
        self.assertEqual(r, "plain")

    def test_run_unavailable(self):
        with patch.object(self.agent, "_get_tool", return_value=None):
            r = self.agent.execute("scan system")
        self.assertEqual(r, "Security agent unavailable.")


class TestSecurityGuardAgent(unittest.TestCase):
    def setUp(self):
        self.agent = SecurityGuardAgent()
        self.guard = MagicMock()
        self.guard.scan_codebase.return_value = {"findings": [], "files_scanned": 5, "scanned_at": "2026-01-01T00:00:00", "count": 0}
        self.guard.check_defenses.return_value = {"passed": 3, "total": 3, "checks": [{"ok": True, "name": "Auth", "detail": "enabled"}]}
        self.guard.incidents.return_value = []
        self.guard.auto_fix.return_value = {"count": 0, "fixes": []}
        self.guard.start_monitor.return_value = True
        self.guard.run_full_check.return_value = {"verdict": "secure", "codebase": {"count": 0, "files_scanned": 5, "critical": 0, "high": 0}, "defenses": {"passed": 3, "total": 3}}
        patcher = patch.object(self.agent, "_get_guard", return_value=self.guard)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "SECG")

    def test_can_handle_strong(self):
        self.assertTrue(self.agent.can_handle("security scan codebase"))
        self.assertTrue(self.agent.can_handle("protect orbit now"))

    def test_can_handle_weak_intent(self):
        self.assertTrue(self.agent.can_handle("scan", intent="security"))

    def test_can_handle_weak_none(self):
        self.assertFalse(self.agent.can_handle("hello"))

    def test_scan_clean(self):
        r = self.agent.execute("run security scan")
        self.assertIn("scan clean", r)

    def test_scan_with_findings(self):
        self.guard.scan_codebase.return_value = {
            "findings": [{"severity": "high", "file": "a.py", "line": 10, "name": "secret"}],
            "count": 1, "files_scanned": 1, "scanned_at": "2026-01-01T00:00:00",
        }
        r = self.agent.execute("scan codebase")
        self.assertIn("found 1 issue", r)
        self.assertIn("a.py:10", r)

    def test_defense_status(self):
        r = self.agent.execute("defense status check")
        self.assertIn("Defense status", r)
        self.assertIn("Auth", r)

    def test_incidents_empty(self):
        r = self.agent.execute("show security incidents")
        self.assertIn("No security incidents", r)

    def test_incidents_list(self):
        self.guard.incidents.return_value = [{"severity": "high", "message": "bad thing happened"}]
        r = self.agent.execute("show incidents")
        self.assertIn("bad thing happened", r)

    def test_autofix(self):
        self.guard.auto_fix.return_value = {"count": 1, "fixes": [{"applied": True, "item": "x", "detail": "fixed"}]}
        r = self.agent.execute("autofix security")
        self.assertIn("Auto-fix ran 1", r)
        self.assertIn("fixed", r)

    def test_monitor(self):
        r = self.agent.execute("start monitor watch")
        self.assertIn("Background security monitoring started", r)

    def test_stop(self):
        r = self.agent.execute("stop guard")
        self.assertIn("stopped", r)

    def test_full_report_default(self):
        r = self.agent.execute("give me security report")
        self.assertIn("full report", r)
        self.assertIn("secure", r)


class TestMemoryAgent(unittest.TestCase):
    def setUp(self):
        self.pool = MagicMock()
        self.pool.stats.return_value = {
            "total_memories": 5, "avg_strength": 0.8,
            "by_namespace": {"global": 3}, "by_agent": {"MEM": 2},
        }
        patches = [
            patch("orbit.agents.utility_agents.get_shared_memory", return_value=self.pool),
            patch("orbit.agents.utility_agents.cleanup_stale_memories", return_value={"pruned": 1, "remaining": 4}),
            patch("orbit.agents.utility_agents.recall_shared", return_value=[]),
            patch("orbit.agents.utility_agents.share_memory"),
            patch("orbit.agents.utility_agents.memory_module"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        import orbit.agents.utility_agents as ua
        ua.memory_module.get_recent.return_value = []
        ua.memory_module.get_context_str.return_value = ""
        ua.memory_module.clear.return_value = None
        self.agent = MemoryAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "MEM")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("remember this memory"))
        self.assertFalse(self.agent.can_handle("hello world"))

    def test_cleanup(self):
        r = self.agent.execute("cleanup stale memories")
        self.assertIn("Pruned: 1 entries", r)

    def test_clear(self):
        r = self.agent.execute("clear everything")
        self.assertIn("cleared", r)

    def test_search_no_results(self):
        r = self.agent.execute("recall history of python")
        self.assertIn("No memories found", r)

    def test_search_with_results(self):
        from orbit.agents import utility_agents as ua
        ua.recall_shared.return_value = [
            {"relevance_score": 0.9, "source_agent": "TAS", "value": {"summary": "did a thing"}},
        ]
        ua.memory_module.get_recent.return_value = [{"user": "hi", "assistant": "hello", "timestamp": "t"}]
        r = self.agent.execute("recall history of python")
        self.assertIn("Relevant memories", r)
        self.assertIn("did a thing", r)

    def test_stats(self):
        r = self.agent.execute("memory stats")
        self.assertIn("Total: 5 entries", r)

    def test_share(self):
        from orbit.agents import utility_agents as ua
        entry = MagicMock()
        entry.key = "note_0"
        entry.id = 42
        ua.share_memory.return_value = entry
        r = self.agent.execute("share: hello world")
        self.assertIn("Memory saved", r)

    def test_fallback_llm(self):
        import orbit.agents.utility_agents as ua
        ua.memory_module.get_context_str.return_value = ""
        ua.recall_shared.return_value = []
        with patch("orbit.agents.utility_agents.llm_router.generate", return_value="llm memory") as gen:
            r = self.agent.execute("what do you know")
        self.assertEqual(r, "llm memory")
        self.assertIn("MEMORY specialist", gen.call_args.kwargs["system_prompt"])


class TestHermesAgent(unittest.TestCase):
    def setUp(self):
        self.agent = HermesAgent()

    def test_instantiation(self):
        self.assertEqual(self.agent.label, "HRM")

    def test_can_handle(self):
        self.assertTrue(self.agent.can_handle("hermes reason deeply"))
        self.assertTrue(self.agent.can_handle("anything", intent="reasoning"))
        self.assertFalse(self.agent.can_handle("hello"))

    def test_no_api_key_fallback(self):
        with patch("orbit.config.decrypt_env", return_value=""), \
             patch("orbit.agents.utility_agents.llm_router.generate", return_value="llm hermes") as gen:
            r = self.agent.execute("think step by step")
        self.assertEqual(r, "llm hermes")
        self.assertIn("HERMES", gen.call_args.kwargs["system_prompt"])

    def test_api_success(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "hermes answer"}}]}
        with patch("orbit.config.decrypt_env", return_value="sk-test"), \
             patch("requests.post", return_value=resp) as post:
            r = self.agent.execute("think deeply")
        self.assertEqual(r, "hermes answer")
        post.assert_called_once()

    def test_api_all_fail_fallback(self):
        resp = MagicMock()
        resp.status_code = 500
        with patch("orbit.config.decrypt_env", return_value="sk-test"), \
             patch("requests.post", return_value=resp), \
             patch("orbit.agents.utility_agents.llm_router.generate", return_value="llm fallback") as gen:
            r = self.agent.execute("deep analysis")
        self.assertEqual(r, "llm fallback")

    def test_api_exception_fallback(self):
        with patch("orbit.config.decrypt_env", return_value="sk-test"), \
             patch("requests.post", side_effect=RuntimeError("net down")), \
             patch("orbit.agents.utility_agents.llm_router.generate", return_value="llm fallback"):
            r = self.agent.execute("reason out loud")
        self.assertEqual(r, "llm fallback")

    def test_context_appended(self):
        with patch("orbit.config.decrypt_env", return_value=""), \
             patch("orbit.agents.utility_agents.llm_router.generate", return_value="x") as gen:
            self.agent.execute("hermes think", context="ctx")
        self.assertIn("[Context]", gen.call_args.kwargs["system_prompt"])


if __name__ == "__main__":
    unittest.main()
