"""Unit tests for orbit/orbit/core/conversation_summarizer_bp.py."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from flask import Flask
from orbit.core.conversation_summarizer_bp import conversation_summarizer_bp


class TestConversationSummarizerBp(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(conversation_summarizer_bp)
        self.client = self.app.test_client()
        self.fake_cs = MagicMock()
        sys.modules["orbit.orbit.core.conversation_summarizer"] = self.fake_cs

    def tearDown(self):
        sys.modules.pop("orbit.orbit.core.conversation_summarizer", None)

    def test_blueprint_name(self):
        self.assertEqual(conversation_summarizer_bp.name, "conversation_summarizer")

    def test_routes_registered(self):
        rules = [r.rule for r in self.app.url_map.iter_rules()]
        for p in ["/api/summarizer/compress", "/api/summarizer/context/<conversation_id>",
                  "/api/summarizer/topics/<conversation_id>", "/api/summarizer/stats"]:
            self.assertIn(p, rules)

    def test_compress_missing_fields_400(self):
        r = self.client.post("/api/summarizer/compress", json={"conversation_id": "c1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.get_json())

    def test_compress_success(self):
        cs_result = MagicMock()
        cs_result.conversation_id = "c1"
        cs_result.total_turns = 10
        cs_result.compressed_turns = 4
        cs_result.chunks = [1, 2]
        self.fake_cs.get_conversation_summarizer.return_value.summarize_conversation.return_value = cs_result
        self.fake_cs.get_conversation_summarizer.return_value.get_topics.return_value = ["t1"]
        r = self.client.post("/api/summarizer/compress", json={"conversation_id": "c1", "turns": [{"u": "hi"}], "title": "T"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["conversation_id"], "c1")
        self.assertEqual(body["total_turns"], 10)
        self.assertEqual(body["compressed_turns"], 4)
        self.assertEqual(body["chunks"], 2)
        self.assertEqual(body["topics"], ["t1"])
        self.fake_cs.get_conversation_summarizer.return_value.summarize_conversation.assert_called_once_with("c1", [{"u": "hi"}], title="T")

    def test_compress_no_body(self):
        r = self.client.post("/api/summarizer/compress")
        self.assertEqual(r.status_code, 400)

    def test_context(self):
        self.fake_cs.get_conversation_summarizer.return_value.get_compressed_context.return_value = "ctx"
        r = self.client.get("/api/summarizer/context/c1?token_budget=100")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["conversation_id"], "c1")
        self.assertEqual(r.get_json()["compressed_context"], "ctx")
        self.fake_cs.get_conversation_summarizer.return_value.get_compressed_context.assert_called_once_with("c1", 100)

    def test_context_default_budget(self):
        self.fake_cs.get_conversation_summarizer.return_value.get_compressed_context.return_value = "ctx"
        r = self.client.get("/api/summarizer/context/c1")
        self.fake_cs.get_conversation_summarizer.return_value.get_compressed_context.assert_called_once_with("c1", 4000)

    def test_topics(self):
        self.fake_cs.get_conversation_summarizer.return_value.get_topics.return_value = ["a", "b"]
        r = self.client.get("/api/summarizer/topics/c1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["conversation_id"], "c1")
        self.assertEqual(r.get_json()["topics"], ["a", "b"])

    def test_stats(self):
        self.fake_cs.get_conversation_summarizer.return_value.get_stats.return_value = {"count": 3}
        r = self.client.get("/api/summarizer/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["count"], 3)


if __name__ == "__main__":
    unittest.main()
