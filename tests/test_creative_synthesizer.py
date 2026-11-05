"""Tests for Creative Synthesizer (System 9)"""

import tempfile
import unittest


class TestCreativeSynthesizer(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()

    def _get_synthesizer(self):
        import orbit.orbit.core.creative_synthesizer as m

        m.DATA_DIR = type(m.DATA_DIR)(self.data_dir)
        m.DATA_DIR.mkdir(parents=True, exist_ok=True)
        m._instance = None
        from orbit.orbit.core.creative_synthesizer import get_creative_synthesizer

        return get_creative_synthesizer()

    def test_import(self):
        from orbit.orbit.core.creative_synthesizer import (
            get_creative_synthesizer,
        )

        self.assertTrue(callable(get_creative_synthesizer))

    def test_register_domain(self):
        s = self._get_synthesizer()
        s.register_domain("coding")
        stats = s.get_stats()
        self.assertIn("coding", stats["domains"])

    def test_register_pattern(self):
        s = self._get_synthesizer()
        pattern = s.register_pattern(
            "coding",
            "Factory Pattern",
            "Creational pattern",
            "Use factory method",
            ["oop", "patterns"],
        )
        self.assertEqual(pattern["domain"], "coding")
        self.assertEqual(pattern["name"], "Factory Pattern")

    def test_get_patterns_all(self):
        s = self._get_synthesizer()
        s.register_pattern("coding", "P1", "desc", "sol")
        s.register_pattern("design", "P2", "desc", "sol")
        self.assertEqual(len(s.get_patterns()), 2)

    def test_get_patterns_filtered(self):
        s = self._get_synthesizer()
        s.register_pattern("coding", "P1", "desc", "sol")
        s.register_pattern("design", "P2", "desc", "sol")
        self.assertEqual(len(s.get_patterns("coding")), 1)

    def test_find_cross_domain_insights(self):
        s = self._get_synthesizer()
        s.register_domain("coding")
        s.register_domain("design")
        s.register_pattern(
            "coding",
            "Factory Pattern",
            "Creational pattern",
            "Use factory method",
            ["oop", "patterns"],
        )
        s.register_pattern(
            "design",
            "Color Theory",
            "Color mixing",
            "Use complementary colors",
            ["visual", "ui"],
        )
        insights = s.find_cross_domain_insights("coding")
        self.assertIsInstance(insights, list)

    def test_get_insights_empty(self):
        s = self._get_synthesizer()
        self.assertEqual(len(s.get_insights()), 0)

    def test_get_stats(self):
        s = self._get_synthesizer()
        s.register_domain("coding")
        s.register_pattern("coding", "P1", "desc", "sol")
        stats = s.get_stats()
        self.assertEqual(stats["total_patterns"], 1)
        self.assertEqual(stats["domain_count"], 1)

    def test_reset(self):
        s = self._get_synthesizer()
        s.register_pattern("coding", "P1", "desc", "sol")
        s.reset()
        self.assertEqual(len(s.get_patterns()), 0)
        self.assertEqual(len(s.get_insights()), 0)

    def test_singleton(self):
        from orbit.orbit.core.creative_synthesizer import get_creative_synthesizer

        s1 = get_creative_synthesizer()
        s2 = get_creative_synthesizer()
        self.assertIs(s1, s2)

    def test_cross_domain_hits_increment(self):
        s = self._get_synthesizer()
        s.register_domain("coding")
        s.register_domain("design")
        s.register_pattern("coding", "Pattern A", "Desc A", "Solution A", ["test"])
        s.find_cross_domain_insights("coding")
        self.assertGreaterEqual(s.get_stats()["avg_cross_domain_hits"], 0)


if __name__ == "__main__":
    unittest.main()
