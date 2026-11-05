"""Enum-coercion regression — knowledge_base + loop_detector (LOOP-ITER-5)."""
import tempfile
from pathlib import Path

import pytest


def _kb():
    import orbit.orbit.core.knowledge_base as kbm

    # redirect storage if DATA_DIR-like exists
    from orbit.orbit.core.knowledge_base import get_knowledge_base

    return get_knowledge_base()


class TestKnowledgeBaseCategoryCoercion:
    def test_bogus_string_category_no_crash(self):
        """REGRESSION: string category must not AttributeError on .value."""
        kb = _kb()
        cid = kb.add("title1", "content1", category="bogus")
        assert isinstance(cid, str)

    def test_valid_string_category(self):
        kb = _kb()
        cid = kb.add("title2", "content2", category="coding")
        assert isinstance(cid, str)

    def test_enum_category_still_works(self):
        from orbit.orbit.core.knowledge_base import KnowledgeCategory

        kb = _kb()
        cid = kb.add("title3", "content3", category=KnowledgeCategory.AI)
        assert isinstance(cid, str)

    def test_confidence_string_coerced(self):
        kb = _kb()
        cid = kb.add("title4", "content4", confidence="0.8")
        assert isinstance(cid, str)

    def test_confidence_nan_fallback(self):
        kb = _kb()
        cid = kb.add("title5", "content5", confidence=float("nan"))
        assert isinstance(cid, str)

    def test_knowledge_category_values(self):
        from orbit.orbit.core.knowledge_base import KnowledgeCategory

        assert KnowledgeCategory.GENERAL.value == "general"
        assert KnowledgeCategory.CODING.value == "coding"


class TestLoopDetectorSeverityCoercion:
    def _ld(self):
        from orbit.orbit.core.loop_detector import LoopDetector

        # storage_dir redirected to tmp to avoid touching real data
        ld = LoopDetector(storage_dir=str(Path(tempfile.mkdtemp())))
        return ld

    def test_bogus_string_severity_no_crash(self):
        """REGRESSION: string severity must not AttributeError on .value."""
        ld = self._ld()
        incident = ld._emit_incident("timing", "comp", "tid", "details", "bogus")
        assert incident["severity"] == "low"  # fallback

    def test_valid_string_severity(self):
        ld = self._ld()
        incident = ld._emit_incident("timing", "comp", "tid", "details", "critical")
        assert incident["severity"] == "critical"

    def test_enum_severity_still_works(self):
        from orbit.orbit.core.loop_detector import Severity

        ld = self._ld()
        incident = ld._emit_incident("timing", "comp", "tid", "details", Severity.HIGH)
        assert incident["severity"] == "high"

    def test_severity_enum_values(self):
        from orbit.orbit.core.loop_detector import Severity

        assert Severity.LOW.value == "low"
        assert Severity.CRITICAL.value == "critical"
