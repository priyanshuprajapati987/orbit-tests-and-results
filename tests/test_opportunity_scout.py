"""
Opportunity Scout — Tests

Covers 4 scanning modes, analysis pipeline, dismiss/action, stats, persistence.
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbit.orbit.core.opportunity_scout import (
    Opportunity,
    OpportunityScan,
    get_opportunity_scout,
)


class TestOpportunityScoutCore(unittest.TestCase):
    def setUp(self):
        self.scout = OpportunityScan()
        self.scout.reset()

    def test_01_import(self):
        from orbit.orbit.core.opportunity_scout import OpportunityScan

        self.assertTrue(OpportunityScan)

    def test_02_singleton_getter(self):
        inst = get_opportunity_scout()
        self.assertIsInstance(inst, OpportunityScan)
        self.assertIs(inst, get_opportunity_scout())

    def test_03_scan_tech_trends_returns_list(self):
        sample = [
            {
                "name": "repoA",
                "description": "python llm agents framework",
                "category": "python",
                "stars": 5000,
                "url": "x",
            },
            {
                "name": "repoB",
                "description": "rust game engine",
                "category": "rust",
                "stars": 100,
                "url": "y",
            },
        ]
        with patch.object(self.scout, "_fetch_github_trending", return_value=sample):
            opps = self.scout.scan_tech_trends()
        self.assertIsInstance(opps, list)
        self.assertGreater(len(opps), 0)

    def test_04_scan_tech_trends_relevance_filter(self):
        opps = self.scout.scan_tech_trends(stack_keywords=["banana", "fruit"])
        for opp in opps:
            self.assertGreater(opp.relevance, 0.6)

    def test_05_scan_market_gaps_returns_list(self):
        sample = [
            {
                "name": "repoA",
                "description": "python llm agents framework",
                "category": "python",
                "stars": 5000,
                "url": "x",
            },
            {
                "name": "repoB",
                "description": "rust game engine",
                "category": "rust",
                "stars": 100,
                "url": "y",
            },
        ]
        with patch.object(self.scout, "_fetch_github_trending", return_value=sample):
            opps = self.scout.scan_market_gaps()
        self.assertIsInstance(opps, list)
        self.assertGreater(len(opps), 0)
        for opp in opps:
            self.assertEqual(opp.type, "market_gap")
            self.assertEqual(opp.urgency, "medium")

    def test_06_scan_competitor_moves(self):
        # Hermetic: Google News RSS times out under full-suite load (was flaky,
        # 0 results -> AssertionError). Mock the fetch; matching logic stays real.
        canned = [
            {"title": "OpenAI releases new GPT model", "summary": "chatgpt update", "url": "https://example.com/1"},
            {"title": "Anthropic announces Claude upgrade", "summary": "claude 5", "url": "https://example.com/2"},
        ]
        with patch.object(type(self.scout), "_fetch_competitor_news", return_value=canned):
            opps = self.scout.scan_competitor_moves()
        self.assertIsInstance(opps, list)
        self.assertGreater(len(opps), 0)
        for opp in opps:
            self.assertEqual(opp.type, "competitor_move")
            self.assertGreater(opp.relevance, 0)

    def test_07_scan_network_empty(self):
        opps = self.scout.scan_network_opportunities([])
        self.assertEqual(len(opps), 0)

    def test_08_scan_network_with_events(self):
        events = [
            {
                "type": "opportunity",
                "title": "Partner with Acme Corp",
                "description": "Strategic partnership opportunity",
                "relevance": 0.9,
            },
            {
                "type": "collab",
                "title": "Collab with DevStudio",
                "description": "Joint development opportunity",
                "relevance": 0.8,
            },
            {
                "type": "meeting",
                "title": "Coffee chat",
                "description": "Casual",
                "relevance": 0.1,
            },
        ]
        opps = self.scout.scan_network_opportunities(events)
        self.assertEqual(len(opps), 2)
        for opp in opps:
            self.assertEqual(opp.type, "network")
            self.assertGreater(opp.relevance, 0.7)

    def test_09_analyze_all_returns_sorted(self):
        opps = self.scout.analyze_all_opportunities()
        self.assertGreater(len(opps), 0)
        for i in range(len(opps) - 1):
            self.assertGreaterEqual(opps[i].relevance, opps[i + 1].relevance)

    def test_10_dismiss_opportunity(self):
        self.scout.analyze_all_opportunities()
        before = len(self.scout.get_all_opportunities())
        first_id = self.scout.get_all_opportunities()[0].id
        ok = self.scout.dismiss_opportunity(first_id)
        self.assertTrue(ok)
        after = len(self.scout.get_all_opportunities())
        self.assertEqual(after, before - 1)

    def test_11_dismiss_nonexistent(self):
        ok = self.scout.dismiss_opportunity("nonexistent")
        self.assertFalse(ok)

    def test_12_record_action(self):
        self.scout.analyze_all_opportunities()
        opps = self.scout.get_all_opportunities()
        self.assertGreater(len(opps), 0)
        opp_id = opps[0].id
        ok = self.scout.record_action(opp_id, "analyzed and queued")
        self.assertTrue(ok)

    def test_13_record_action_nonexistent(self):
        ok = self.scout.record_action("nonexistent", "test")
        self.assertFalse(ok)

    def test_14_get_stats_structure(self):
        self.scout.analyze_all_opportunities()
        stats = self.scout.get_stats()
        self.assertIn("total", stats)
        self.assertIn("by_type", stats)
        self.assertIn("by_urgency", stats)
        self.assertIn("avg_relevance", stats)
        self.assertIn("last_scan", stats)
        self.assertGreater(stats["total"], 0)
        self.assertGreater(stats["avg_relevance"], 0)

    def test_15_stats_empty(self):
        stats = self.scout.get_stats()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["avg_relevance"], 0)

    def test_16_get_top_opportunities_limit(self):
        self.scout.analyze_all_opportunities()
        top3 = self.scout.get_top_opportunities(limit=3)
        self.assertLessEqual(len(top3), 3)
        top10 = self.scout.get_top_opportunities(limit=10)
        self.assertLessEqual(len(top10), 10)

    def test_17_opportunity_dataclass_to_dict(self):
        opp = Opportunity(
            id="test_1",
            type="tech_trend",
            title="Test Opportunity",
            description="A test",
            relevance=0.85,
            urgency="high",
            action="Test it",
            discovered_at=datetime.now(timezone.utc),
        )
        d = opp.to_dict()
        self.assertEqual(d["id"], "test_1")
        self.assertEqual(d["type"], "tech_trend")
        self.assertEqual(d["relevance"], 0.85)
        self.assertIn("discovered_at", d)

    def test_18_opportunity_from_dict_roundtrip(self):
        opp = Opportunity(
            id="roundtrip_1",
            type="market_gap",
            title="Roundtrip Test",
            description="Round trip serialization",
            relevance=0.75,
            urgency="medium",
            action="Roundtrip action",
            discovered_at=datetime.now(timezone.utc),
        )
        d = opp.to_dict()
        restored = Opportunity.from_dict(d)
        self.assertEqual(restored.id, opp.id)
        self.assertEqual(restored.type, opp.type)
        self.assertEqual(restored.relevance, opp.relevance)
        self.assertEqual(
            restored.discovered_at.isoformat(), opp.discovered_at.isoformat()
        )

    def test_19_score_relevance(self):
        item = {
            "description": "Python agent orchestration framework",
            "category": "agent_tools",
        }
        score = self.scout._score_relevance(item, ["python", "llm"])
        self.assertGreaterEqual(score, 0.3)
        score2 = self.scout._score_relevance(item, ["javascript", "react"])
        self.assertEqual(score2, 0.0)

    def test_20_score_fit(self):
        event = {"relevance": 0.9}
        self.assertEqual(self.scout._score_fit(event), 0.9)
        self.assertEqual(self.scout._score_fit({}), 0.5)

    def test_21_reset_clears_data(self):
        self.scout.analyze_all_opportunities()
        self.assertGreater(len(self.scout.get_all_opportunities()), 0)
        self.scout.reset()
        self.assertEqual(len(self.scout.get_all_opportunities()), 0)

    def test_22_stats_by_type_accuracy(self):
        self.scout.analyze_all_opportunities()
        stats = self.scout.get_stats()
        total_from_type = sum(stats["by_type"].values())
        self.assertEqual(stats["total"], total_from_type)

    def test_23_analyze_all_persists(self):
        self.scout.analyze_all_opportunities()
        new_scout = OpportunityScan()
        loaded = new_scout.get_all_opportunities()
        self.assertGreater(len(loaded), 0)

    def test_24_tech_trends_id_format(self):
        opps = self.scout.scan_tech_trends()
        for opp in opps:
            self.assertTrue(opp.id.startswith("tech_"))

    def test_25_market_gaps_id_format(self):
        opps = self.scout.scan_market_gaps()
        for opp in opps:
            self.assertTrue(opp.id.startswith("gap_"))


if __name__ == "__main__":
    unittest.main()
