"""Deep tests for orbit/orbit/tools/cai_security.py (Loop 14/1).

Covers both the CAI-unavailable path (default env) and the CAI-available
path (via sys.modules mocking + module reload).
"""

import asyncio
import json
import os
import sys
import types
import unittest
from unittest import mock

import importlib


def _make_fake_cai():
    """Build fake cai.sdk.agents + openai modules."""
    cai_agents = types.ModuleType("cai.sdk.agents")
    # function_tool decorator that returns the function unchanged
    def function_tool(fn=None, **kw):
        if fn is None:
            def wrap(f):
                return f
            return wrap
        return fn
    cai_agents.Agent = mock.MagicMock()
    cai_agents.Runner = mock.MagicMock()
    cai_agents.OpenAIChatCompletionsModel = mock.MagicMock()
    cai_agents.RunConfig = mock.MagicMock()
    cai_agents.function_tool = function_tool
    cai_sdk = types.ModuleType("cai.sdk")
    cai_sdk.agents = cai_agents
    cai = types.ModuleType("cai")
    cai.sdk = cai_sdk
    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncOpenAI = mock.MagicMock()
    return {
        "cai": cai,
        "cai.sdk": cai_sdk,
        "cai.sdk.agents": cai_agents,
        "openai": openai_mod,
    }


class CaiUnavailableTests(unittest.TestCase):
    """Default environment: CAI SDK not installed."""

    def setUp(self):
        # ensure cai not importable
        for k in ("cai", "cai.sdk", "cai.sdk.agents", "openai"):
            sys.modules.pop(k, None)
        # reload module fresh (will hit except branch)
        import orbit.orbit.tools.cai_security as m
        importlib.reload(m)
        self.m = m

    def test_cai_available_false(self):
        self.assertFalse(self.m._CAI_AVAILABLE)
        self.assertIsNone(self.m.Agent)
        self.assertIsNone(self.m.Runner)

    def test_cai_tools_empty(self):
        self.assertEqual(self.m.CAI_TOOLS, [])

    def test_get_agent_returns_none_and_logs(self):
        with mock.patch.object(self.m, "logger") as lg:
            self.assertIsNone(self.m.get_agent())
        lg.warning.assert_called_once()

    def test_get_agent_cached_none(self):
        # _cai_agent stays None; second call still None
        self.m.get_agent()
        self.assertIsNone(self.m.get_agent())

    def test_analyze_unavailable(self):
        r = asyncio.run(self.m.analyze("q"))
        self.assertIn("CAI module unavailable", r)

    def test_security_audit_unavailable(self):
        r = asyncio.run(self.m.security_audit())
        self.assertIn("CAI module unavailable", r)

    def test_threat_analysis_unavailable(self):
        r = asyncio.run(self.m.threat_analysis())
        self.assertIn("CAI module unavailable", r)

    def test_run_analysis(self):
        r = self.m.run_analysis("q")
        self.assertIn("CAI module unavailable", r)

    def test_run_audit(self):
        r = self.m.run_audit()
        self.assertIn("CAI module unavailable", r)

    def test_run_threat_analysis(self):
        r = self.m.run_threat_analysis()
        self.assertIn("CAI module unavailable", r)

    def test_security_tool_instance_exists(self):
        self.assertIsNotNone(self.m._security_tool)


class CaiAvailableTests(unittest.TestCase):
    """CAI SDK available via sys.modules mocking."""

    def setUp(self):
        self.fake = _make_fake_cai()
        # save originals
        self._saved_modules = {}
        for k, v in self.fake.items():
            self._saved_modules[k] = sys.modules.get(k, _MISSING)
            sys.modules[k] = v
        # make cai importable as top-level
        import orbit.orbit.tools.cai_security as m
        importlib.reload(m)
        self.m = m
        self.assertTrue(self.m._CAI_AVAILABLE)
        self.addCleanup(self._teardown)

    def _teardown(self):
        for k in self.fake:
            if self._saved_modules[k] is _MISSING:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = self._saved_modules[k]
        # reload back to unavailable state for other tests
        import orbit.orbit.tools.cai_security as m
        importlib.reload(m)

    def test_cai_tools_populated(self):
        self.assertEqual(len(self.m.CAI_TOOLS), 8)

    def test_get_agent_creates_agent(self):
        self.m._cai_agent = None
        self.m._client = None
        with mock.patch.dict(os.environ, {"OLLAMA_URL": "http://x/v1",
                                          "CAI_MODEL": "ollama/m"}):
            agent = self.m.get_agent()
        self.assertIsNotNone(agent)
        self.m._client = None
        self.m._cai_agent = None

    def test_get_agent_cached(self):
        self.m._cai_agent = "CACHED"
        self.assertEqual(self.m.get_agent(), "CACHED")
        self.m._cai_agent = None

    def test_get_agent_default_env(self):
        self.m._cai_agent = None
        self.m._client = None
        with mock.patch.dict(os.environ, {}, clear=True):
            agent = self.m.get_agent()
        self.assertIsNotNone(agent)
        self.m._cai_agent = None
        self.m._client = None

    def test_analyze_success(self):
        self.m._cai_agent = "AGENT"
        # mock Runner.run as async returning final_output
        async def fake_run(agent, input):
            r = mock.MagicMock()
            r.final_output = "RESULT TEXT"
            return r
        self.m.Runner.run = fake_run
        r = asyncio.run(self.m.analyze("query"))
        self.assertEqual(r, "RESULT TEXT")
        self.m._cai_agent = None

    def test_analyze_connection_error(self):
        self.m._cai_agent = "AGENT"
        async def fake_run(agent, input):
            raise Exception("Cannot connect to host refused")
        self.m.Runner.run = fake_run
        r = asyncio.run(self.m.analyze("q"))
        self.assertIn("Cannot connect to Ollama", r)
        self.m._cai_agent = None

    def test_analyze_auth_error(self):
        self.m._cai_agent = "AGENT"
        async def fake_run(agent, input):
            raise Exception("AuthenticationError api_key invalid")
        self.m.Runner.run = fake_run
        r = asyncio.run(self.m.analyze("q"))
        self.assertIn("Authentication issue", r)
        self.m._cai_agent = None

    def test_analyze_generic_error(self):
        self.m._cai_agent = "AGENT"
        with mock.patch.object(self.m, "logger") as lg:
            async def fake_run(agent, input):
                raise ValueError("something else")
            self.m.Runner.run = fake_run
            r = asyncio.run(self.m.analyze("q"))
        self.assertIn("CAI Analysis Error: something else", r)
        lg.error.assert_called_once()
        self.m._cai_agent = None

    def test_analyze_no_agent(self):
        self.m._cai_agent = None
        # get_agent returns None because _CAI_AVAILABLE? it's True but _cai_agent None -> creates agent.
        # To make get_agent return None, set _CAI_AVAILABLE False temporarily
        self.m._CAI_AVAILABLE = False
        r = asyncio.run(self.m.analyze("q"))
        self.assertIn("CAI module unavailable", r)
        self.m._CAI_AVAILABLE = True

    def test_security_audit(self):
        self.m._cai_agent = "AGENT"
        async def fake_run(agent, input):
            r = mock.MagicMock()
            r.final_output = "AUDIT"
            return r
        self.m.Runner.run = fake_run
        r = asyncio.run(self.m.security_audit())
        self.assertEqual(r, "AUDIT")
        self.m._cai_agent = None

    def test_threat_analysis(self):
        self.m._cai_agent = "AGENT"
        async def fake_run(agent, input):
            r = mock.MagicMock()
            r.final_output = "THREAT"
            return r
        self.m.Runner.run = fake_run
        r = asyncio.run(self.m.threat_analysis())
        self.assertEqual(r, "THREAT")
        self.m._cai_agent = None

    def test_run_analysis_success(self):
        self.m._cai_agent = "AGENT"
        async def fake_run(agent, input):
            r = mock.MagicMock()
            r.final_output = "OK"
            return r
        self.m.Runner.run = fake_run
        self.assertEqual(self.m.run_analysis("q"), "OK")
        self.m._cai_agent = None

    def test_run_analysis_exception(self):
        # asyncio.run itself raises (e.g. event loop issue) -> caught
        with mock.patch("asyncio.run", side_effect=RuntimeError("loop fail")), \
                mock.patch.object(self.m, "logger") as lg:
            r = self.m.run_analysis("q")
        self.assertIn("CAI Analysis Error: loop fail", r)
        lg.error.assert_called_once()

    def test_run_audit_exception(self):
        with mock.patch("asyncio.run", side_effect=RuntimeError("loop fail")), \
                mock.patch.object(self.m, "logger") as lg:
            r = self.m.run_audit()
        self.assertIn("CAI Audit Error: loop fail", r)
        lg.error.assert_called_once()

    def test_run_threat_analysis_exception(self):
        with mock.patch("asyncio.run", side_effect=RuntimeError("loop fail")), \
                mock.patch.object(self.m, "logger") as lg:
            r = self.m.run_threat_analysis()
        self.assertIn("CAI Threat Analysis Error: loop fail", r)
        lg.error.assert_called_once()

    def test_function_tools_callable(self):
        # CAI_TOOLS wrappers call _security_tool methods
        st = mock.MagicMock()
        st.scan_processes.return_value = {"p": 1}
        st.scan_ports.return_value = ["p1", "p2"]
        st.scan_network.return_value = "net"
        st.firewall_status.return_value = "fw"
        st.disk_usage.return_value = [{"d": 1}]
        st.active_connections.return_value = "conn"
        st.defender_scan.return_value = "def"
        st.full_report.return_value = "report"
        with mock.patch.object(self.m, "_security_tool", st):
            tools = self.m.CAI_TOOLS
            # call each
            self.assertEqual(json.loads(tools[0]()), {"p": 1})
            self.assertEqual(tools[1](), "p1\np2")
            self.assertEqual(tools[2](), "net")
            self.assertEqual(tools[3](), "fw")
            self.assertEqual(json.loads(tools[4]()), [{"d": 1}])
            self.assertEqual(tools[5](), "conn")
            self.assertEqual(tools[6](), "def")
            self.assertEqual(tools[7](), "report")


    def test_main_guard(self):
        import runpy
        # make get_logger return a mock so logger.info is tracked
        with mock.patch("logging.getLogger", return_value=mock.MagicMock()):
            # remove from sys.modules so runpy re-executes cleanly
            import sys
            sys.modules.pop("orbit.orbit.tools.cai_security", None)
            with mock.patch("orbit.orbit.tools.cai_security.run_audit",
                            return_value="AUDIT_RESULT"):
                runpy.run_module("orbit.orbit.tools.cai_security",
                                 run_name="__main__")


if __name__ == "__main__":
    unittest.main()
_MISSING = object()
