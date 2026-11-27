"""Deep tests for orbit/orbit/core/tech_scout.py (Loop 17/5)."""

import json
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from orbit.orbit.core import tech_scout as ts


class InitTests(unittest.TestCase):
    def test_init_creates_data_dir(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            s = ts.TechScout()
        mk.assert_called_once_with(parents=True, exist_ok=True)
        self.assertIsNotNone(s.session)


class ScoreRelevanceTests(unittest.TestCase):
    def test_no_hits(self):
        self.assertEqual(ts.TechScout()._score_relevance("nothing here"), 0)

    def test_one_hit(self):
        # 1*8 + 0 = 8
        self.assertEqual(ts.TechScout()._score_relevance("agent"), 8)

    def test_three_hits_bonus(self):
        # 3*8 + 2 = 26
        self.assertEqual(ts.TechScout()._score_relevance("agent memory llm"), 26)

    def test_five_hits_bonus(self):
        # 5*8 + 2 + 5 = 47
        self.assertEqual(ts.TechScout()._score_relevance(
            "agent memory llm voice automation"), 47)

    def test_cap_100(self):
        text = " ".join(ts.ORBIT_KEYWORDS)
        score = ts.TechScout()._score_relevance(text)
        self.assertLessEqual(score, 100)

    def test_case_insensitive(self):
        self.assertEqual(ts.TechScout()._score_relevance("AGENT"), 8)


class ExtractXmlTests(unittest.TestCase):
    def test_found(self):
        xml = "<title>hello</title>"
        self.assertEqual(ts.TechScout()._extract_xml(xml, "title"), "hello")

    def test_not_found(self):
        self.assertEqual(ts.TechScout()._extract_xml("<x/>", "title"), "")

    def test_multiline(self):
        xml = "<summary>\nline1\nline2\n</summary>"
        self.assertEqual(ts.TechScout()._extract_xml(xml, "summary"), "line1\nline2")

    def test_attrs_on_tag(self):
        xml = '<entry><id attr="x">val</id></entry>'
        self.assertEqual(ts.TechScout()._extract_xml(xml, "id"), "val")


class ScanGithubTests(unittest.TestCase):
    def _scout(self):
        return ts.TechScout()

    def test_success_filters_score(self):
        scout = self._scout()
        resp = mock.MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"items": [
            {"full_name": "org/agent-tool", "description": "agent memory llm rag",
             "html_url": "u", "stargazers_count": 100, "language": "py",
             "topics": ["agent", "llm"], "created_at": "2026-01-01"},
            {"full_name": "org/low", "description": "nothing relevant",
             "html_url": "u2", "stargazers_count": 10, "language": "py",
             "topics": [], "created_at": "2026-01-01"},
        ]}
        scout.session.get = mock.MagicMock(return_value=resp)
        results = scout._scan_github_trending()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "github")
        self.assertEqual(results[0]["title"], "org/agent-tool")
        self.assertEqual(results[0]["stars"], 100)
        self.assertEqual(results[0]["language"], "py")
        self.assertGreaterEqual(results[0]["relevance_score"], 15)

    def test_non_200_returns_empty(self):
        scout = self._scout()
        resp = mock.MagicMock(status_code=404)
        scout.session.get = mock.MagicMock(return_value=resp)
        self.assertEqual(scout._scan_github_trending(), [])

    def test_exception_returns_empty(self):
        scout = self._scout()
        scout.session.get = mock.MagicMock(side_effect=Exception("net"))
        with mock.patch.object(ts, "logger") as lg:
            self.assertEqual(scout._scan_github_trending(), [])
        lg.error.assert_called_once()

    def test_caps_at_15(self):
        scout = self._scout()
        items = [{"full_name": f"org/a{i}", "description": "agent memory llm rag tool",
                  "html_url": "u", "stargazers_count": 1, "language": "py",
                  "topics": [], "created_at": ""} for i in range(20)]
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = {"items": items}
        scout.session.get = mock.MagicMock(return_value=resp)
        results = scout._scan_github_trending()
        self.assertEqual(len(results), 15)

    def test_none_description_handled(self):
        scout = self._scout()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = {"items": [
            {"full_name": "org/x", "description": None,
             "html_url": "u", "stargazers_count": 1, "language": None,
             "topics": None, "created_at": None}]}
        scout.session.get = mock.MagicMock(return_value=resp)
        results = scout._scan_github_trending()
        # score from "org/x" + "" + "" -> likely < 15 -> empty
        self.assertIsInstance(results, list)


class ScanHuggingfaceTests(unittest.TestCase):
    def test_success(self):
        scout = ts.TechScout()
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = [
            {"modelId": "org/agent-llm", "tags": ["agent", "llm", "rag"],
             "downloads": 1000, "likes": 50, "lastModified": "2026-01-01"},
        ]
        scout.session.get = mock.MagicMock(return_value=resp)
        results = scout._scan_huggingface()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "huggingface")
        self.assertEqual(results[0]["title"], "org/agent-llm")
        self.assertEqual(results[0]["downloads"], 1000)

    def test_non_200(self):
        scout = ts.TechScout()
        resp = mock.MagicMock(status_code=500)
        scout.session.get = mock.MagicMock(return_value=resp)
        self.assertEqual(scout._scan_huggingface(), [])

    def test_exception(self):
        scout = ts.TechScout()
        scout.session.get = mock.MagicMock(side_effect=Exception("net"))
        with mock.patch.object(ts, "logger") as lg:
            self.assertEqual(scout._scan_huggingface(), [])
        lg.error.assert_called_once()

    def test_caps_at_15(self):
        scout = ts.TechScout()
        models = [{"modelId": f"org/m{i}", "tags": ["agent", "llm", "rag", "tool"],
                   "downloads": 1, "likes": 1, "lastModified": ""} for i in range(20)]
        resp = mock.MagicMock(status_code=200)
        resp.json.return_value = models
        scout.session.get = mock.MagicMock(return_value=resp)
        self.assertEqual(len(scout._scan_huggingface()), 15)


class ScanArxivTests(unittest.TestCase):
    def test_success(self):
        scout = ts.TechScout()
        xml = (
            "<entry><title>Agent Memory Paper</title><summary>llm agent rag</summary>"
            "<id>http://arxiv.org/abs/1</id><author><name>A</name></author></entry>"
        )
        resp = mock.MagicMock(status_code=200)
        resp.text = xml
        scout.session.get = mock.MagicMock(return_value=resp)
        results = scout._scan_arxiv()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "arxiv")
        self.assertEqual(results[0]["title"], "Agent Memory Paper")
        self.assertEqual(results[0]["url"], "http://arxiv.org/abs/1")

    def test_non_200(self):
        scout = ts.TechScout()
        resp = mock.MagicMock(status_code=404)
        scout.session.get = mock.MagicMock(return_value=resp)
        self.assertEqual(scout._scan_arxiv(), [])

    def test_exception(self):
        scout = ts.TechScout()
        scout.session.get = mock.MagicMock(side_effect=Exception("net"))
        with mock.patch.object(ts, "logger") as lg:
            self.assertEqual(scout._scan_arxiv(), [])
        lg.error.assert_called_once()

    def test_caps_at_15(self):
        scout = ts.TechScout()
        entries = "".join(
            f"<entry><title>Agent Memory {i}</title><summary>llm agent rag</summary>"
            f"<id>u{i}</id><author><name>A</name></author></entry>"
            for i in range(20))
        resp = mock.MagicMock(status_code=200)
        resp.text = entries
        scout.session.get = mock.MagicMock(return_value=resp)
        self.assertEqual(len(scout._scan_arxiv()), 15)

    def test_empty_response(self):
        scout = ts.TechScout()
        resp = mock.MagicMock(status_code=200)
        resp.text = "no entries here"
        scout.session.get = mock.MagicMock(return_value=resp)
        self.assertEqual(scout._scan_arxiv(), [])


class ScanAllTests(unittest.TestCase):
    def test_scan_all(self):
        scout = ts.TechScout()
        gh = [{"source": "github", "title": "g", "relevance_score": 20}]
        hf = [{"source": "huggingface", "title": "h", "relevance_score": 10}]
        ax = [{"source": "arxiv", "title": "a", "relevance_score": 30}]
        with mock.patch.object(scout, "_scan_github_trending", return_value=gh), \
                mock.patch.object(scout, "_scan_huggingface", return_value=hf), \
                mock.patch.object(scout, "_scan_arxiv", return_value=ax), \
                mock.patch.object(scout, "_save_report"):
            report = scout.scan_all()
        self.assertIn("timestamp", report)
        self.assertEqual(report["github_trending"], gh)
        self.assertEqual(report["huggingface_models"], hf)
        self.assertEqual(report["arxiv_papers"], ax)
        self.assertEqual(report["summary"]["total_items"], 3)
        self.assertEqual(report["summary"]["github_count"], 1)
        self.assertEqual(report["summary"]["huggingface_count"], 1)
        self.assertEqual(report["summary"]["arxiv_count"], 1)
        self.assertEqual(report["summary"]["avg_relevance"], 20.0)
        self.assertEqual(len(report["summary"]["top_relevant"]), 3)

    def test_scan_all_empty(self):
        scout = ts.TechScout()
        with mock.patch.object(scout, "_scan_github_trending", return_value=[]), \
                mock.patch.object(scout, "_scan_huggingface", return_value=[]), \
                mock.patch.object(scout, "_scan_arxiv", return_value=[]), \
                mock.patch.object(scout, "_save_report"):
            report = scout.scan_all()
        self.assertEqual(report["summary"]["total_items"], 0)
        self.assertEqual(report["summary"]["avg_relevance"], 0)
        self.assertEqual(report["summary"]["top_relevant"], [])


class SaveReportTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)
        self.addCleanup(mock.patch.stopall)

    def test_save_new_file(self):
        scout = ts.TechScout()
        report = {"summary": {"total_items": 5}}
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d), \
                mock.patch("orbit.orbit.core.tech_scout.datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-01-01"
            scout._save_report(report)
        p = self._d / "2026-01-01.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text("utf-8"))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["summary"]["total_items"], 5)

    def test_save_appends_to_existing_list(self):
        scout = ts.TechScout()
        p = self._d / "2026-01-01.json"
        p.write_text('[{"summary":{"total_items":1}}]', encoding="utf-8")
        report = {"summary": {"total_items": 2}}
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d), \
                mock.patch("orbit.orbit.core.tech_scout.datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-01-01"
            scout._save_report(report)
        data = json.loads(p.read_text("utf-8"))
        self.assertEqual(len(data), 2)

    def test_save_existing_dict_wrapped(self):
        scout = ts.TechScout()
        p = self._d / "2026-01-01.json"
        p.write_text('{"summary":{"total_items":1}}', encoding="utf-8")
        report = {"summary": {"total_items": 2}}
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d), \
                mock.patch("orbit.orbit.core.tech_scout.datetime") as dt:
            dt.now.return_value.strftime.return_value = "2026-01-01"
            scout._save_report(report)
        data = json.loads(p.read_text("utf-8"))
        self.assertEqual(len(data), 2)

    def test_save_failure_logged(self):
        scout = ts.TechScout()
        report = {"summary": {"total_items": 1}}
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d), \
                mock.patch("orbit.orbit.core.tech_scout.datetime") as dt, \
                mock.patch.object(Path, "write_text", side_effect=OSError("boom")), \
                mock.patch.object(ts, "logger") as lg:
            dt.now.return_value.strftime.return_value = "2026-01-01"
            scout._save_report(report)
        lg.error.assert_called_once()


class GetLatestTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)

    def test_today_exists_list(self):
        scout = ts.TechScout()
        p = self._d / f"{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.json"
        p.write_text('[{"a":1},{"b":2}]', encoding="utf-8")
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_latest()
        self.assertEqual(r, {"b": 2})

    def test_today_exists_dict(self):
        scout = ts.TechScout()
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        p = self._d / f"{today}.json"
        p.write_text('{"a":1}', encoding="utf-8")
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_latest()
        self.assertEqual(r, {"a": 1})

    def test_falls_back_to_history(self):
        scout = ts.TechScout()
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d), \
                mock.patch.object(scout, "get_history", return_value=[{"x": 1}]):
            r = scout.get_latest()
        self.assertEqual(r, {"x": 1})

    def test_no_reports_returns_none(self):
        scout = ts.TechScout()
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d), \
                mock.patch.object(scout, "get_history", return_value=[]):
            r = scout.get_latest()
        self.assertIsNone(r)

    def test_today_corrupt_falls_back(self):
        scout = ts.TechScout()
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        p = self._d / f"{today}.json"
        p.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d), \
                mock.patch.object(scout, "get_history", return_value=[]):
            r = scout.get_latest()
        self.assertIsNone(r)


class GetHistoryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = Path(tempfile.mkdtemp())
        self._d.mkdir(parents=True, exist_ok=True)

    def test_days_invalid_string(self):
        scout = ts.TechScout()
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_history("abc")
        self.assertEqual(r, [])

    def test_days_none(self):
        scout = ts.TechScout()
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_history(None)
        self.assertEqual(r, [])

    def test_days_clamped_low(self):
        scout = ts.TechScout()
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            # 0 -> max(1, min(0,90)) = 1
            r = scout.get_history(0)
        self.assertIsInstance(r, list)

    def test_days_clamped_high(self):
        scout = ts.TechScout()
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_history(1000)
        self.assertIsInstance(r, list)

    def test_reads_existing(self):
        scout = ts.TechScout()
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        p = self._d / f"{today}.json"
        p.write_text('[{"x":1}]', encoding="utf-8")
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_history(1)
        self.assertEqual(r, [{"x": 1}])

    def test_reads_dict_as_single(self):
        scout = ts.TechScout()
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        p = self._d / f"{today}.json"
        p.write_text('{"x":1}', encoding="utf-8")
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_history(1)
        self.assertEqual(r, [{"x": 1}])

    def test_corrupt_file_skipped(self):
        scout = ts.TechScout()
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        p = self._d / f"{today}.json"
        p.write_text("{bad", encoding="utf-8")
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_history(1)
        self.assertEqual(r, [])

    def test_multiple_days(self):
        scout = ts.TechScout()
        import datetime as dt
        for i in range(3):
            day = (dt.datetime.now() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
            p = self._d / f"{day}.json"
            p.write_text(f'[{{"day":{i}}}]', encoding="utf-8")
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", self._d):
            r = scout.get_history(3)
        self.assertEqual(len(r), 3)


class GetScoutTests(unittest.TestCase):
    def setUp(self):
        self._saved = ts._scout
        ts._scout = None
        self.addCleanup(setattr, ts, "_scout", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", d):
            a = ts.get_scout()
        self.assertIsInstance(a, ts.TechScout)
        self.assertIs(ts._scout, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.tech_scout.DATA_DIR", d):
            a = ts.get_scout()
            b = ts.get_scout()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
