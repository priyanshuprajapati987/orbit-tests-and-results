"""Unit tests for orbit/orbit/core/agent_society.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.agent_society import debate, DEFAULT_PERSONAS


class TestAgentSociety(unittest.TestCase):
    def _make_router(self, answers):
        # answers: list of (content, success) for each generate call
        router = MagicMock()
        resps = []
        for content, success in answers:
            m = MagicMock()
            m.content = content
            m.success = success
            resps.append(m)
        router.generate.side_effect = resps
        return router

    def test_empty_question(self):
        r = debate("")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "empty question")
        self.assertEqual(r["votes"], [])

    def test_none_question(self):
        r = debate(None)
        self.assertFalse(r["ok"])

    def test_all_fail(self):
        router = self._make_router([("", False)] * 4)
        with patch("orbit.core.llm.router.get_router", return_value=router):
            r = debate("question", use_cache=False)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "all agents failed")

    def test_success(self):
        answers = [("optimist answer", True), ("critic answer", True),
                   ("pragmatist answer", True), ("expert answer", True),
                   ("synthesis final", True)]
        router = self._make_router(answers)
        with patch("orbit.core.llm.router.get_router", return_value=router):
            r = debate("what to do?", use_cache=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["question"], "what to do?")
        self.assertEqual(len(r["votes"]), 4)
        self.assertEqual(r["synthesis"], "synthesis final")
        self.assertTrue(r["agreement"])

    def test_partial_failure(self):
        answers = [("optimist answer", True), ("", False),
                   ("pragmatist answer", True), ("expert answer", True),
                   ("synth", True)]
        router = self._make_router(answers)
        with patch("orbit.core.llm.router.get_router", return_value=router):
            r = debate("q", use_cache=False)
        self.assertTrue(r["ok"])
        self.assertFalse(r["agreement"])
        # 3 confident
        confident = [v for v in r["votes"] if v["confident"]]
        self.assertEqual(len(confident), 3)

    def test_synthesis_failure_fallback(self):
        answers = [("opt", True), ("crit", True), ("prag", True), ("exp", True),
                   (None, False)]  # synthesis returns None success
        # make sresp.success False
        resps = []
        for content, success in answers:
            m = MagicMock()
            m.content = content
            m.success = success
            resps.append(m)
        # last one: success False → synthesis = confident[0]["answer"] = "opt"
        router = MagicMock()
        router.generate.side_effect = resps
        with patch("orbit.core.llm.router.get_router", return_value=router):
            r = debate("q", use_cache=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["synthesis"], "")

    def test_synthesis_exception_fallback(self):
        router = MagicMock()
        resps = []
        for i in range(4):
            m = MagicMock(); m.content = f"ans{i}"; m.success = True; resps.append(m)
        # 5th call raises
        resps.append(RuntimeError("synth down"))
        router.generate.side_effect = resps
        with patch("orbit.core.llm.router.get_router", return_value=router):
            r = debate("q", use_cache=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["synthesis"], "ans0")

    def test_custom_personas(self):
        personas = [("p1", "persona1"), ("p2", "persona2")]
        answers = [("a1", True), ("a2", True), ("synth", True)]
        router = self._make_router(answers)
        with patch("orbit.core.llm.router.get_router", return_value=router):
            r = debate("q", personas=personas, use_cache=False)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["votes"]), 2)
        self.assertEqual(r["votes"][0]["persona"], "p1")

    def test_default_personas(self):
        self.assertEqual(len(DEFAULT_PERSONAS), 4)

    def test_votes_structure(self):
        answers = [("ans", True)] * 4 + [("synth", True)]
        router = self._make_router(answers)
        with patch("orbit.core.llm.router.get_router", return_value=router):
            r = debate("q", use_cache=False)
        for v in r["votes"]:
            self.assertIn("persona", v)
            self.assertIn("answer", v)
            self.assertIn("confident", v)

    def test_cache_param_passed(self):
        answers = [("a", True)] * 4 + [("s", True)]
        router = self._make_router(answers)
        with patch("orbit.core.llm.router.get_router", return_value=router):
            debate("q", use_cache=False)
        # LLMRequest should have use_cache=False
        req = router.generate.call_args_list[0][0][0]
        self.assertFalse(req.use_cache)


if __name__ == "__main__":
    unittest.main()
