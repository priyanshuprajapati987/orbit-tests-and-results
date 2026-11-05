"""Regression tests: semantic context retrieval in TFIDFRetriever.

- With NO embedder (offline default), retrieval is pure TF-IDF and still works.
- With a semantic embedder injected, a PARAPHRASE query with zero keyword overlap
  ("how do I quit orbit") recalls the related chunk ("exit the assistant application"),
  proving meaning-based recall works.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _fake_embedder(text: str):
    """Tiny deterministic embedder: dim0=exit/quit words, dim1=weather words, dim2=bias."""
    t = text.lower()
    v0 = sum(1 for w in ("quit", "exit", "close", "stop", "shut") if w in t)
    v1 = sum(1 for w in ("weather", "rain", "temperature", "forecast") if w in t)
    return [float(v0), float(v1), 1.0]


def test_tfidf_only_when_no_embedder():
    from orbit.orbit.core.context_manager import TFIDFRetriever

    r = TFIDFRetriever()
    r.add("The weather in London is rainy today.")
    r.add("To exit the assistant application click the close button.")
    hits = r.search("London rain forecast", top_k=2)
    assert hits and "weather" in hits[0]["text"].lower()


def test_semantic_recalls_paraphrase():
    from orbit.orbit.core.context_manager import TFIDFRetriever

    r = TFIDFRetriever(semantic_weight=0.7)
    r.set_embedder(_fake_embedder)
    r.add("The weather in London is rainy today.")
    r.add("To exit the assistant application click the close button.")
    r.add("Photosynthesis happens in green plant leaves.")

    # Zero keyword overlap with the exit doc ("quit" not in stored text).
    hits = r.search("how do I quit orbit", top_k=3)
    texts = [h["text"].lower() for h in hits]
    assert any("exit the assistant" in t for t in texts)
    # The exit doc should outrank the unrelated photosynthesis doc.
    exit_rank = next(i for i, t in enumerate(texts) if "exit the assistant" in t)
    photo_rank = next((i for i, t in enumerate(texts) if "photosynthesis" in t), 99)
    assert exit_rank < photo_rank
