"""Unit tests for orbit/orbit/widgets.py (PyQt5 widgets)."""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from PyQt5.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from orbit.widgets import (
    RadarChart, AnimatedArc, AnimatedOverlay, AgentNodeWidget,
    AgentNetworkWidget, StatBarWidget, GlassPanel,
    SKILL_CATEGORIES, AGENT_MODES,
)


class TestWidgetsConstants(unittest.TestCase):
    def test_skill_categories(self):
        self.assertGreater(len(SKILL_CATEGORIES), 0)

    def test_agent_modes(self):
        self.assertGreater(len(AGENT_MODES), 0)


class TestRadarChart(unittest.TestCase):
    def setUp(self):
        self.w = RadarChart()

    def test_instantiation(self):
        self.assertIsNotNone(self.w)

    def test_set_skill(self):
        self.w.set_skill("Computer", 0.9)
        self.assertAlmostEqual(self.w.target_values["Computer"], 0.9, places=2)

    def test_increment_skill(self):
        before = self.w.target_values["Computer"]
        self.w.increment_skill("Computer", 0.1)
        self.assertGreater(self.w.target_values["Computer"], before)

    def test_animate_step(self):
        self.w._animate_step()
        self.assertTrue(True)

    def test_paint(self):
        self.w.resize(300, 300)
        self.w.repaint()
        QApplication.processEvents()


class TestAnimatedArc(unittest.TestCase):
    def setUp(self):
        self.w = AnimatedArc()

    def test_instantiation(self):
        self.assertIsNotNone(self.w)

    def test_paint(self):
        self.w.resize(100, 100)
        self.w.repaint()
        QApplication.processEvents()


class TestAnimatedOverlay(unittest.TestCase):
    def setUp(self):
        self.w = AnimatedOverlay()

    def test_instantiation(self):
        self.assertIsNotNone(self.w)

    def test_paint(self):
        self.w.resize(100, 100)
        self.w.repaint()
        QApplication.processEvents()


class TestAgentNodeWidget(unittest.TestCase):
    def setUp(self):
        self.w = AgentNodeWidget("QNN", "Queen", "#ffd700")

    def test_instantiation(self):
        self.assertIsNotNone(self.w)

    def test_paint(self):
        self.w.resize(80, 80)
        self.w.repaint()
        QApplication.processEvents()


class TestAgentNetworkWidget(unittest.TestCase):
    def setUp(self):
        self.w = AgentNetworkWidget()

    def test_instantiation(self):
        self.assertIsNotNone(self.w)

    def test_paint(self):
        self.w.resize(200, 200)
        self.w.repaint()
        QApplication.processEvents()


class TestStatBarWidget(unittest.TestCase):
    def setUp(self):
        self.w = StatBarWidget()

    def test_instantiation(self):
        self.assertIsNotNone(self.w)

    def test_paint(self):
        self.w.resize(200, 40)
        self.w.repaint()
        QApplication.processEvents()


class TestGlassPanel(unittest.TestCase):
    def setUp(self):
        self.w = GlassPanel()

    def test_instantiation(self):
        self.assertIsNotNone(self.w)

    def test_paint(self):
        self.w.resize(200, 100)
        self.w.repaint()
        QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
