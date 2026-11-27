"""Deep tests for orbit/orbit/core/universal_search.py (Loop 13/5).

Covers every statement:
  * ``UniversalSearch.__init__`` — creates DATA_DIR, lock.
  * Each ``_search_*`` — success path with mocked subsystem, exception
    path (subsystem raises → [] + debug log).
  * ``search`` — single category, all categories, sorting by score desc,
    unknown category falls through to all.
  * ``get_universal_search`` — singleton creation + reuse; ``_instance``
    reset.
"""

import unittest
from unittest import mock

from orbit.orbit.core import universal_search as us


def _conv_mgr(convs):
    m = mock.MagicMock()
    m.list_all.return_value = convs
    return m


def _kb(cards):
    m = mock.MagicMock()
    m.search.return_value = cards
    return m


def _pool(entries):
    m = mock.MagicMock()
    m.search.return_value = entries
    return m


def _goals(goals):
    m = mock.MagicMock()
    m.get_all.return_value = goals
    return m


def _decisions(decisions):
    m = mock.MagicMock()
    m.get_history.return_value = decisions
    return m


def _lab(exps):
    m = mock.MagicMock()
    m.get_all.return_value = exps
    return m


class InitTests(unittest.TestCase):
    def test_init_creates_data_dir_and_lock(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            s = us.UniversalSearch()
        mk.assert_called_once_with(parents=True, exist_ok=True)
        self.assertTrue(hasattr(s, "_lock"))


class SearchConversationsTests(unittest.TestCase):
    def test_success_with_messages(self):
        convs = [{"id": 1, "title": "Hello", "messages": [
            {"content": "world foo"}, {"content": "bar"}]}]
        mgr = _conv_mgr(convs)
        with mock.patch("orbit.orbit.core.conversation_manager.get_conversation_manager",
                        return_value=mgr):
            r = us.UniversalSearch()._search_conversations("foo")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["category"], "conversations")
        self.assertEqual(r[0]["id"], 1)
        self.assertEqual(r[0]["title"], "Hello")
        self.assertEqual(r[0]["snippet"], "world foo")
        self.assertEqual(r[0]["score"], 1.0)

    def test_no_match(self):
        convs = [{"id": 1, "title": "Hello", "messages": [{"content": "world"}]}]
        mgr = _conv_mgr(convs)
        with mock.patch("orbit.orbit.core.conversation_manager.get_conversation_manager",
                        return_value=mgr):
            self.assertEqual(us.UniversalSearch()._search_conversations("zzz"), [])

    def test_empty_messages_snippet(self):
        convs = [{"id": 2, "title": "T", "messages": []}]
        # text_blob = "T " + "" = "T " ; query "t" matches
        mgr = _conv_mgr(convs)
        with mock.patch("orbit.orbit.core.conversation_manager.get_conversation_manager",
                        return_value=mgr):
            r = us.UniversalSearch()._search_conversations("t")
        self.assertEqual(r[0]["snippet"], "")

    def test_exception_returns_empty(self):
        with mock.patch("orbit.orbit.core.conversation_manager.get_conversation_manager",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(us, "logger") as lg:
            self.assertEqual(us.UniversalSearch()._search_conversations("q"), [])
        lg.debug.assert_called_once()


class SearchKnowledgeTests(unittest.TestCase):
    def test_success(self):
        cards = [{"id": "k1", "title": "Title", "content": "content here",
                  "relevance": 0.9}]
        kb = _kb(cards)
        with mock.patch("orbit.orbit.core.knowledge_base.get_knowledge_base",
                        return_value=kb):
            r = us.UniversalSearch()._search_knowledge("q")
        self.assertEqual(r[0]["category"], "knowledge")
        self.assertEqual(r[0]["id"], "k1")
        self.assertEqual(r[0]["title"], "Title")
        self.assertEqual(r[0]["snippet"], "content here")
        self.assertEqual(r[0]["score"], 0.9)

    def test_relevance_default(self):
        cards = [{"id": "k2", "title": "T", "content": "c"}]
        kb = _kb(cards)
        with mock.patch("orbit.orbit.core.knowledge_base.get_knowledge_base",
                        return_value=kb):
            r = us.UniversalSearch()._search_knowledge("q")
        self.assertEqual(r[0]["score"], 0.5)

    def test_exception(self):
        with mock.patch("orbit.orbit.core.knowledge_base.get_knowledge_base",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(us, "logger") as lg:
            self.assertEqual(us.UniversalSearch()._search_knowledge("q"), [])
        lg.debug.assert_called_once()


class SearchMemoryTests(unittest.TestCase):
    def test_success(self):
        entries = [{"id": "m1", "key": "k", "value": "v", "relevance": 0.7}]
        pool = _pool(entries)
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        return_value=pool):
            r = us.UniversalSearch()._search_memory("q")
        self.assertEqual(r[0]["category"], "memory")
        self.assertEqual(r[0]["id"], "m1")
        self.assertEqual(r[0]["title"], "k")
        self.assertEqual(r[0]["snippet"], "v")
        self.assertEqual(r[0]["score"], 0.7)

    def test_relevance_default(self):
        entries = [{"id": "m2", "key": "k", "value": 42}]
        pool = _pool(entries)
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        return_value=pool):
            r = us.UniversalSearch()._search_memory("q")
        self.assertEqual(r[0]["score"], 0.5)
        self.assertEqual(r[0]["snippet"], "42")

    def test_pool_search_limit_20(self):
        pool = _pool([])
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        return_value=pool):
            us.UniversalSearch()._search_memory("q")
        pool.search.assert_called_once_with("q", limit=20)

    def test_exception(self):
        with mock.patch("orbit.orbit.core.memory_store.get_shared_memory",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(us, "logger") as lg:
            self.assertEqual(us.UniversalSearch()._search_memory("q"), [])
        lg.debug.assert_called_once()


class SearchGoalsTests(unittest.TestCase):
    def test_match(self):
        goals = [{"id": "g1", "title": "Learn Python", "description": "study"}]
        tracker = _goals(goals)
        with mock.patch("orbit.orbit.core.goal_tracker.get_goal_tracker",
                        return_value=tracker):
            r = us.UniversalSearch()._search_goals("python")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["category"], "goals")
        self.assertEqual(r[0]["title"], "Learn Python")
        self.assertEqual(r[0]["score"], 0.8)

    def test_no_match(self):
        goals = [{"id": "g1", "title": "Sleep", "description": "rest"}]
        tracker = _goals(goals)
        with mock.patch("orbit.orbit.core.goal_tracker.get_goal_tracker",
                        return_value=tracker):
            self.assertEqual(us.UniversalSearch()._search_goals("python"), [])

    def test_exception(self):
        with mock.patch("orbit.orbit.core.goal_tracker.get_goal_tracker",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(us, "logger") as lg:
            self.assertEqual(us.UniversalSearch()._search_goals("q"), [])
        lg.debug.assert_called_once()


class SearchDecisionsTests(unittest.TestCase):
    def test_match(self):
        decisions = [{"id": "d1", "question": "Which DB?", "recommendation": "Postgres",
                      "winner": "Postgres"}]
        engine = _decisions(decisions)
        with mock.patch("orbit.orbit.core.decision_engine.get_decision_engine",
                        return_value=engine):
            r = us.UniversalSearch()._search_decisions("postgres")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["category"], "decisions")
        self.assertEqual(r[0]["title"], "Which DB?")
        self.assertEqual(r[0]["score"], 0.7)
        self.assertIn("Postgres", r[0]["snippet"])

    def test_no_match(self):
        decisions = [{"id": "d1", "question": "X", "recommendation": "Y",
                      "winner": "Z"}]
        engine = _decisions(decisions)
        with mock.patch("orbit.orbit.core.decision_engine.get_decision_engine",
                        return_value=engine):
            self.assertEqual(us.UniversalSearch()._search_decisions("python"), [])

    def test_exception(self):
        with mock.patch("orbit.orbit.core.decision_engine.get_decision_engine",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(us, "logger") as lg:
            self.assertEqual(us.UniversalSearch()._search_decisions("q"), [])
        lg.debug.assert_called_once()


class SearchExperimentsTests(unittest.TestCase):
    def test_match(self):
        exps = [{"id": "e1", "name": "Exp1", "hypothesis": "improves speed"}]
        lab = _lab(exps)
        with mock.patch("orbit.orbit.core.experiment_lab.get_experiment_lab",
                        return_value=lab):
            r = us.UniversalSearch()._search_experiments("speed")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["category"], "experiments")
        self.assertEqual(r[0]["title"], "Exp1")
        self.assertEqual(r[0]["snippet"], "improves speed")
        self.assertEqual(r[0]["score"], 0.6)

    def test_no_match(self):
        exps = [{"id": "e1", "name": "Exp1", "hypothesis": "x"}]
        lab = _lab(exps)
        with mock.patch("orbit.orbit.core.experiment_lab.get_experiment_lab",
                        return_value=lab):
            self.assertEqual(us.UniversalSearch()._search_experiments("zzz"), [])

    def test_exception(self):
        with mock.patch("orbit.orbit.core.experiment_lab.get_experiment_lab",
                        side_effect=RuntimeError("boom")), \
                mock.patch.object(us, "logger") as lg:
            self.assertEqual(us.UniversalSearch()._search_experiments("q"), [])
        lg.debug.assert_called_once()


class SearchMethodTests(unittest.TestCase):
    def test_all_categories_sorted_by_score(self):
        s = us.UniversalSearch()
        with mock.patch.object(s, "_search_conversations",
                               return_value=[{"category": "conversations",
                                              "score": 0.5}]), \
                mock.patch.object(s, "_search_knowledge",
                                  return_value=[{"category": "knowledge",
                                                 "score": 0.9}]), \
                mock.patch.object(s, "_search_memory", return_value=[]), \
                mock.patch.object(s, "_search_goals", return_value=[]), \
                mock.patch.object(s, "_search_decisions", return_value=[]), \
                mock.patch.object(s, "_search_experiments", return_value=[]):
            r = s.search("q")
        self.assertEqual(r[0]["category"], "knowledge")
        self.assertEqual(r[1]["category"], "conversations")

    def test_single_category(self):
        s = us.UniversalSearch()
        with mock.patch.object(s, "_search_knowledge",
                               return_value=[{"category": "knowledge",
                                              "score": 1.0}]) as sk, \
                mock.patch.object(s, "_search_conversations") as sc:
            r = s.search("q", category="knowledge")
        self.assertEqual(len(r), 1)
        sc.assert_not_called()
        sk.assert_called_once_with("q")

    def test_unknown_category_runs_all(self):
        s = us.UniversalSearch()
        mocks = {}
        for name in ("_search_conversations", "_search_knowledge", "_search_memory",
                     "_search_goals", "_search_decisions", "_search_experiments"):
            mocks[name] = mock.patch.object(s, name, return_value=[])
        with mock.MagicMock():
            pass
        # apply all patches
        patchers = [mock.patch.object(s, n, return_value=[]) for n in
                    ("_search_conversations", "_search_knowledge", "_search_memory",
                     "_search_goals", "_search_decisions", "_search_experiments")]
        for p in patchers:
            p.start()
        try:
            r = s.search("q", category="nope")
        finally:
            for p in patchers:
                p.stop()
        self.assertEqual(r, [])

    def test_empty_results(self):
        s = us.UniversalSearch()
        patchers = [mock.patch.object(s, n, return_value=[]) for n in
                    ("_search_conversations", "_search_knowledge", "_search_memory",
                     "_search_goals", "_search_decisions", "_search_experiments")]
        for p in patchers:
            p.start()
        try:
            r = s.search("q")
        finally:
            for p in patchers:
                p.stop()
        self.assertEqual(r, [])


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = us._instance
        us._instance = None
        self.addCleanup(setattr, us, "_instance", self._saved)

    def test_creates_instance(self):
        a = us.get_universal_search()
        self.assertIsInstance(a, us.UniversalSearch)
        self.assertIs(us._instance, a)

    def test_reuses_instance(self):
        a = us.get_universal_search()
        b = us.get_universal_search()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
