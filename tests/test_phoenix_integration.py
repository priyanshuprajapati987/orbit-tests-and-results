"""
Integration tests: Phoenix checkpoint captures awareness + learning data.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from orbit.orbit.core.agent_awareness import (
    Decision,
    get_awareness_manager,
)
from orbit.orbit.core.agent_learning import (
    SolutionPattern,
    get_learning_bridge,
    get_pattern_indexer,
)
from orbit.orbit.core.phoenix import CHECKPOINT_DIR, PhoenixEngine


class TestPhoenixAwarenessLearningIntegration(unittest.TestCase):
    def setUp(self):
        self.engine = PhoenixEngine()
        self.engine._history.clear()
        # Use singletons so checkpoint internal imports see the same instance
        self.awareness = get_awareness_manager()
        self.awareness.reset()
        self.indexer = get_pattern_indexer()
        self.indexer.reset()
        get_learning_bridge()  # ensure singleton exists

    def _read_latest_checkpoint(self):
        """Read the most recent checkpoint file directly."""
        cps = sorted(CHECKPOINT_DIR.glob("*.json"), reverse=True)
        if not cps:
            return None

        return json.loads(cps[0].read_text(encoding="utf-8"))

    def test_01_checkpoint_includes_agent_awareness(self):
        self.awareness.register_agent("CodeAgent", ["coding", "debugging"])
        self.awareness.log_decision(
            "CodeAgent", Decision("coding", "Fix bug", "fix", "fix", True)
        )
        self.engine.take_checkpoint("test_awareness")
        data = self._read_latest_checkpoint()
        self.assertIsNotNone(data)
        self.assertIn("agent_awareness", data.get("data", {}))

    def test_02_checkpoint_includes_agent_learning(self):
        self.indexer.index_pattern(
            SolutionPattern(
                "CodeAgent",
                "timeout_handling",
                "API timeout",
                "Exponential backoff",
            )
        )
        self.engine.take_checkpoint("test_learning")
        data = self._read_latest_checkpoint()
        self.assertIn("agent_learning", data.get("data", {}))
        self.assertGreater(data["data"]["agent_learning"]["total_patterns"], 0)

    def test_03_checkpoint_data_is_serializable(self):
        self.awareness.register_agent("TestAgent", ["test"])
        self.awareness.log_decision(
            "TestAgent", Decision("test", "Run", "done", "done", True)
        )
        self.indexer.index_pattern(
            SolutionPattern("TestAgent", "general", "test", "fix")
        )
        self.engine.take_checkpoint("test_serialize")
        data = self._read_latest_checkpoint()

        serialized = json.dumps(data, default=str)
        self.assertIn("agent_awareness", serialized)
        self.assertIn("agent_learning", serialized)

    def test_04_checkpoint_awareness_team_summary(self):
        self.awareness.register_agent("AgentA", ["coding"])
        self.awareness.register_agent("AgentB", ["research"])
        self.awareness.log_decision(
            "AgentA", Decision("coding", "Fix", "fix", "fix", True)
        )
        self.awareness.log_decision(
            "AgentB", Decision("research", "Find", "found", "missed", False)
        )
        self.engine.take_checkpoint("test_team")
        data = self._read_latest_checkpoint()
        summary = data["data"]["agent_awareness"]
        self.assertIn("team_size", summary)
        self.assertEqual(summary["team_size"], 2)

    def test_05_checkpoint_preserved_across_engine_instances(self):
        self.awareness.register_agent("PersistAgent", ["coding"])
        self.awareness.log_decision(
            "PersistAgent", Decision("coding", "T", "T", "T", True)
        )
        self.indexer.index_pattern(
            SolutionPattern("PersistAgent", "general", "test", "fix")
        )
        self.engine.take_checkpoint("test_persist")
        data = self._read_latest_checkpoint()
        self.assertIn("agent_awareness", data.get("data", {}))
        self.assertIn("agent_learning", data.get("data", {}))


if __name__ == "__main__":
    unittest.main()
