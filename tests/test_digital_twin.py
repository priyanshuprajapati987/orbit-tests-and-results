"""Unit tests for orbit/orbit/core/digital_twin.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.digital_twin import build_twin, twin_summary


class TestDigitalTwin(unittest.TestCase):
    def test_defaults_no_modules(self):
        with patch("orbit.core.personalization", side_effect=ImportError("no module"), create=True):
            with patch("orbit.core.relationship_tracker", side_effect=ImportError("no module"), create=True):
                t = build_twin()
        self.assertEqual(t["preferences"], [])
        self.assertEqual(t["agents"], [])
        self.assertEqual(t["relationships"], [])
        self.assertEqual(t["notes"], "")

    def test_personalization_str(self):
        pers = MagicMock()
        pers.build_personalization_context.return_value = "some context notes"
        with patch("orbit.core.personalization", pers, create=True):
            with patch("orbit.core.relationship_tracker", side_effect=ImportError("x"), create=True):
                t = build_twin()
        self.assertEqual(t["notes"], "some context notes")

    def test_personalization_dict(self):
        pers = MagicMock()
        pers.build_personalization_context.return_value = {
            "preferences": ["dark mode", "vim"],
            "agents": ["TAS", "COD"],
            "notes": "user notes",
        }
        with patch("orbit.core.personalization", pers, create=True):
            with patch("orbit.core.relationship_tracker", side_effect=ImportError("x"), create=True):
                t = build_twin()
        self.assertEqual(t["preferences"], ["dark mode", "vim"])
        self.assertEqual(t["agents"], ["TAS", "COD"])
        self.assertEqual(t["notes"], "user notes")

    def test_preferences_truncated_to_10(self):
        pers = MagicMock()
        pers.build_personalization_context.return_value = {"preferences": list(range(20)), "agents": [], "notes": ""}
        with patch("orbit.core.personalization", pers, create=True):
            with patch("orbit.core.relationship_tracker", side_effect=ImportError("x"), create=True):
                t = build_twin()
        self.assertEqual(len(t["preferences"]), 10)

    def test_relationships(self):
        pers = MagicMock()
        pers.build_personalization_context.return_value = "ctx"
        rt = MagicMock()
        rt.list_people.return_value = [{"name": "Alice"}, {"name": "Bob"}]
        with patch("orbit.core.personalization", pers, create=True):
            with patch("orbit.core.relationship_tracker", rt, create=True):
                t = build_twin()
        self.assertEqual(t["relationships"], ["Alice", "Bob"])

    def test_relationships_truncated_to_20(self):
        pers = MagicMock()
        pers.build_personalization_context.return_value = "ctx"
        rt = MagicMock()
        rt.list_people.return_value = [{"name": f"p{i}"} for i in range(30)]
        with patch("orbit.core.personalization", pers, create=True):
            with patch("orbit.core.relationship_tracker", rt, create=True):
                t = build_twin()
        self.assertEqual(len(t["relationships"]), 20)

    def test_relationships_failure(self):
        pers = MagicMock()
        pers.build_personalization_context.return_value = "ctx"
        rt = MagicMock()
        rt.list_people.side_effect = RuntimeError("boom")
        with patch("orbit.core.personalization", pers, create=True):
            with patch("orbit.core.relationship_tracker", rt, create=True):
                t = build_twin()
        self.assertEqual(t["relationships"], [])

    def test_twin_summary_empty(self):
        with patch("orbit.core.digital_twin.build_twin", return_value={"preferences": [], "agents": [], "relationships": [], "notes": ""}):
            s = twin_summary()
        self.assertEqual(s, "You (digital twin):")

    def test_twin_summary_full(self):
        twin = {
            "preferences": ["dark mode", "vim"],
            "agents": ["TAS", "COD"],
            "relationships": ["Alice", "Bob"],
            "notes": "some notes here",
        }
        with patch("orbit.core.digital_twin.build_twin", return_value=twin):
            s = twin_summary()
        self.assertIn("Prefers: dark mode; vim", s)
        self.assertIn("Often uses: TAS, COD", s)
        self.assertIn("Knows: Alice, Bob", s)
        self.assertIn("some notes here", s)

    def test_twin_summary_notes_truncated(self):
        twin = {"preferences": [], "agents": [], "relationships": [], "notes": "x" * 500}
        with patch("orbit.core.digital_twin.build_twin", return_value=twin):
            s = twin_summary()
        # notes truncated to 300
        self.assertNotIn("x" * 500, s)
        self.assertIn("x" * 300, s)


if __name__ == "__main__":
    unittest.main()
