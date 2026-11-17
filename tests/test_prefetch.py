"""Unit tests for orbit/orbit/core/prefetch.py."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.prefetch import Prefetch, get_prefetch, _PREFETCH_PROMPT


def _make_pf(tmpdir, content=None):
    path = os.path.join(tmpdir, "prefetch.json")
    if content is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return Prefetch(store_path=path), path


class TestInitLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_init_no_file(self):
        pf, path = _make_pf(self.tmp)
        self.assertEqual(pf._cache, {})

    def test_init_loads_valid(self):
        pf, path = _make_pf(self.tmp, '{"a": "brief-a", "b": "brief-b"}')
        self.assertEqual(pf._cache, {"a": "brief-a", "b": "brief-b"})

    def test_init_corrupt_json(self):
        pf, path = _make_pf(self.tmp, "not-json{{{")
        self.assertEqual(pf._cache, {})

    def test_init_null_json(self):
        pf, path = _make_pf(self.tmp, "null")
        self.assertEqual(pf._cache, {})

    def test_init_list_json(self):
        pf, path = _make_pf(self.tmp, "[1, 2]")
        self.assertEqual(pf._cache, {})

    def test_init_empty_file(self):
        pf, path = _make_pf(self.tmp, "")
        self.assertEqual(pf._cache, {})


class TestSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_save_creates_file(self):
        pf, path = _make_pf(self.tmp)
        pf._cache["x"] = "brief-x"
        pf._save()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, {"x": "brief-x"})

    def test_save_creates_dirs(self):
        nested = os.path.join(self.tmp, "a", "b")
        path = os.path.join(nested, "prefetch.json")
        pf = Prefetch(store_path=path)
        pf._cache["y"] = "y"
        pf._save()
        self.assertTrue(os.path.exists(path))

    def test_save_atomic_no_tmp_left(self):
        pf, path = _make_pf(self.tmp)
        pf._cache["z"] = "z"
        pf._save()
        self.assertFalse(os.path.exists(path + ".tmp"))


class TestGet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_get_hit(self):
        pf, _ = _make_pf(self.tmp, '{"a": "brief"}')
        self.assertEqual(pf.get("a"), "brief")

    def test_get_miss(self):
        pf, _ = _make_pf(self.tmp)
        self.assertIsNone(pf.get("missing"))


class TestReset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_reset_clears(self):
        pf, path = _make_pf(self.tmp, '{"a": "b"}')
        pf.reset()
        self.assertEqual(pf._cache, {})
        # persisted empty
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {})


class TestRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _run_with_mock(self, pf, topics, brief="generated brief"):
        with patch("orbit.core.llm.router.get_router") as gr, \
             patch("orbit.core.llm.router.LLMRequest") as lreq, \
             patch("orbit.core.prefetch.run_llm_sync") as rl:
            resp = MagicMock()
            resp.content = brief
            resp.success = True
            rl.return_value = resp
            out = pf.run(topics)
            return out, rl, lreq, gr

    def test_run_generates_brief(self):
        pf, path = _make_pf(self.tmp)
        out, rl, lreq, gr = self._run_with_mock(pf, ["python"])
        self.assertEqual(out, {"python": "generated brief"})
        self.assertEqual(pf.get("python"), "generated brief")

    def test_run_cached_topic_skips_llm(self):
        pf, _ = _make_pf(self.tmp, '{"python": "cached-brief"}')
        out, rl, lreq, gr = self._run_with_mock(pf, ["python"])
        self.assertEqual(out, {"python": "cached-brief"})
        rl.assert_not_called()

    def test_run_skips_empty_topics(self):
        pf, _ = _make_pf(self.tmp)
        out, rl, lreq, gr = self._run_with_mock(pf, ["", "  ", None])
        self.assertEqual(out, {})
        rl.assert_not_called()

    def test_run_none_topics(self):
        pf, _ = _make_pf(self.tmp)
        out, rl, lreq, gr = self._run_with_mock(pf, None)
        self.assertEqual(out, {})

    def test_run_multiple_topics(self):
        pf, _ = _make_pf(self.tmp)
        out, rl, lreq, gr = self._run_with_mock(pf, ["a", "b"])
        self.assertEqual(set(out.keys()), {"a", "b"})
        self.assertEqual(rl.call_count, 2)

    def test_run_failed_llm_not_cached(self):
        pf, _ = _make_pf(self.tmp)
        with patch("orbit.core.llm.router.get_router"), \
             patch("orbit.core.llm.router.LLMRequest"), \
             patch("orbit.core.prefetch.run_llm_sync") as rl:
            resp = MagicMock()
            resp.success = False
            resp.content = ""
            rl.return_value = resp
            out = pf.run(["topic"])
        self.assertEqual(out, {})
        self.assertIsNone(pf.get("topic"))

    def test_run_llm_exception_not_cached(self):
        pf, _ = _make_pf(self.tmp)
        with patch("orbit.core.llm.router.get_router"), \
             patch("orbit.core.llm.router.LLMRequest"), \
             patch("orbit.core.prefetch.run_llm_sync", side_effect=RuntimeError("down")):
            out = pf.run(["topic"])
        self.assertEqual(out, {})

    def test_run_prompt_contains_topic(self):
        pf, _ = _make_pf(self.tmp)
        with patch("orbit.core.llm.router.get_router"), \
             patch("orbit.core.llm.router.LLMRequest") as lreq, \
             patch("orbit.core.prefetch.run_llm_sync") as rl:
            resp = MagicMock()
            resp.content = "x"
            resp.success = True
            rl.return_value = resp
            pf.run(["quantum"])
        kwargs = lreq.call_args.kwargs
        self.assertIn("quantum", kwargs["prompt"])
        self.assertTrue(kwargs["force_offline"])
        self.assertTrue(kwargs["use_cache"])
        self.assertEqual(kwargs["max_tokens"], 160)

    def test_prompt_template(self):
        self.assertIn("{topic}", _PREFETCH_PROMPT)
        self.assertIn("60 words", _PREFETCH_PROMPT)

    def test_run_persists_to_disk(self):
        pf, path = _make_pf(self.tmp)
        self._run_with_mock(pf, ["persisted"])
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, {"persisted": "generated brief"})


class TestGetPrefetch(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_prefetch(), get_prefetch())

    def test_type(self):
        self.assertIsInstance(get_prefetch(), Prefetch)


if __name__ == "__main__":
    unittest.main()
