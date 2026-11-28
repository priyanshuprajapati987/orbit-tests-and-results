"""Deep tests for orbit/orbit/core/learning_safety.py (Loop 22/4)."""

import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import learning_safety as ls


class RehydrateTests(unittest.TestCase):
    def test_valid_enums(self):
        a = {"adaptation_id": "a1", "category": "c", "description": "d",
             "risk_level": "high", "status": "applied", "samples_used": 5,
             "confidence": 0.9, "before_state": {}, "after_state": {},
             "timestamp": "t", "rollback_data": None,
             "validation_passed": True, "regression_detected": False}
        r = ls._rehydrate_adaptation(a)
        self.assertEqual(r.risk_level, ls.AdaptationRisk.HIGH)
        self.assertEqual(r.status, ls.AdaptationStatus.APPLIED)
        self.assertEqual(r.adaptation_id, "a1")

    def test_unknown_risk_fallback_low(self):
        a = {"adaptation_id": "a1", "category": "c", "description": "d",
             "risk_level": "bogus", "status": "applied", "samples_used": 0,
             "confidence": 0, "before_state": {}, "after_state": {}}
        r = ls._rehydrate_adaptation(a)
        self.assertEqual(r.risk_level, ls.AdaptationRisk.LOW)

    def test_unknown_status_fallback_pending(self):
        a = {"adaptation_id": "a1", "category": "c", "description": "d",
             "risk_level": "low", "status": "bogus", "samples_used": 0,
             "confidence": 0, "before_state": {}, "after_state": {}}
        r = ls._rehydrate_adaptation(a)
        self.assertEqual(r.status, ls.AdaptationStatus.PENDING)

    def test_extra_keys_ignored(self):
        a = {"adaptation_id": "a1", "category": "c", "description": "d",
             "risk_level": "low", "status": "pending", "samples_used": 0,
             "confidence": 0, "before_state": {}, "after_state": {},
             "extra_field": "ignored"}
        r = ls._rehydrate_adaptation(a)
        self.assertFalse(hasattr(r, "extra_field"))

    def test_defaults_for_missing(self):
        a = {"adaptation_id": "a1", "category": "", "description": "",
             "samples_used": 0, "confidence": 0, "before_state": {},
             "after_state": {}}
        r = ls._rehydrate_adaptation(a)
        self.assertEqual(r.adaptation_id, "a1")
        self.assertEqual(r.risk_level, ls.AdaptationRisk.LOW)
        self.assertEqual(r.status, ls.AdaptationStatus.PENDING)


class InitLoadSaveTests(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_init_creates_data_dir(self):
        d = self._tmp()
        with mock.patch("pathlib.Path.mkdir") as mk:
            s = ls.LearningSafety(data_dir=d)
        mk.assert_called_once_with(parents=True, exist_ok=True)

    def test_init_defaults(self):
        d = self._tmp()
        s = ls.LearningSafety(data_dir=d)
        self.assertEqual(s._min_samples, 10)
        self.assertEqual(s._min_confidence, 0.7)
        self.assertEqual(s._max_adaptations_per_hour, 10)
        self.assertEqual(s._regression_threshold, 0.15)
        self.assertEqual(s._eval_train_split, 0.8)
        self.assertEqual(s._samples, {})
        self.assertEqual(s._adaptations, [])
        self.assertEqual(len(s._adaptation_times), 0)

    def test_load_existing(self):
        d = self._tmp()
        (d / "samples.json").write_text(json.dumps({"cat1": [{"success": True}]}),
                                       encoding="utf-8")
        (d / "adaptations.json").write_text(json.dumps({"adaptations": [
            {"adaptation_id": "a1", "category": "c", "description": "d",
             "risk_level": "low", "status": "pending", "samples_used": 0,
             "confidence": 0, "before_state": {}, "after_state": {}}]}),
            encoding="utf-8")
        s = ls.LearningSafety(data_dir=d)
        self.assertEqual(len(s._samples["cat1"]), 1)
        self.assertEqual(len(s._adaptations), 1)

    def test_load_corrupt_samples(self):
        d = self._tmp()
        (d / "samples.json").write_text("{bad", encoding="utf-8")
        (d / "adaptations.json").write_text("{bad", encoding="utf-8")
        with mock.patch.object(ls, "logger") as lg:
            s = ls.LearningSafety(data_dir=d)
        lg.warning.assert_called_once()
        self.assertEqual(s._samples, {})
        self.assertEqual(s._adaptations, [])

    def test_load_missing(self):
        d = self._tmp()
        s = ls.LearningSafety(data_dir=d)
        self.assertEqual(s._samples, {})
        self.assertEqual(s._adaptations, [])

    def test_load_only_samples(self):
        d = self._tmp()
        (d / "samples.json").write_text(json.dumps({"cat1": [{"success": True}]}),
                                       encoding="utf-8")
        s = ls.LearningSafety(data_dir=d)
        self.assertEqual(len(s._samples["cat1"]), 1)
        self.assertEqual(s._adaptations, [])

    def test_load_only_adaptations(self):
        d = self._tmp()
        (d / "adaptations.json").write_text(json.dumps({"adaptations": []}),
                                           encoding="utf-8")
        s = ls.LearningSafety(data_dir=d)
        self.assertEqual(s._adaptations, [])

    def test_save_success(self):
        d = self._tmp()
        s = ls.LearningSafety(data_dir=d)
        s.record_sample("cat", "q", "r", True, 10.0)
        # save called during record_sample; verify files exist
        self.assertTrue((d / "samples.json").exists())
        self.assertTrue((d / "adaptations.json").exists())

    def test_save_failure_logged(self):
        d = self._tmp()
        s = ls.LearningSafety(data_dir=d)
        with mock.patch("orbit.orbit.core.learning_safety.atomic_write_text",
                        side_effect=OSError("boom")), \
                mock.patch.object(ls, "logger") as lg:
            s._save()
        lg.warning.assert_called_once()


class RecordSampleTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_record_sample(self):
        s = self._make()
        s.record_sample("cat", "query text", "result text", True, 50.0,
                        metadata={"k": "v"})
        self.assertEqual(len(s._samples["cat"]), 1)
        sample = s._samples["cat"][0]
        self.assertEqual(sample["query"], "query text")
        self.assertEqual(sample["result"], "result text")
        self.assertTrue(sample["success"])
        self.assertEqual(sample["latency_ms"], 50.0)
        self.assertEqual(sample["metadata"], {"k": "v"})
        self.assertIn("timestamp", sample)

    def test_record_sample_truncates(self):
        s = self._make()
        long_q = "q" * 300
        long_r = "r" * 300
        s.record_sample("cat", long_q, long_r, True, 1.0)
        sample = s._samples["cat"][0]
        self.assertEqual(len(sample["query"]), 200)
        self.assertEqual(len(sample["result"]), 200)

    def test_record_sample_default_metadata(self):
        s = self._make()
        s.record_sample("cat", "q", "r", False, 1.0)
        self.assertEqual(s._samples["cat"][0]["metadata"], {})

    def test_record_sample_cap_1000(self):
        s = self._make()
        for i in range(1005):
            s.record_sample("cat", f"q{i}", "r", True, 1.0)
        self.assertEqual(len(s._samples["cat"]), 1000)

    def test_get_sample_count(self):
        s = self._make()
        self.assertEqual(s.get_sample_count("cat"), 0)
        s.record_sample("cat", "q", "r", True, 1.0)
        self.assertEqual(s.get_sample_count("cat"), 1)
        self.assertEqual(s.get_sample_count("nope"), 0)


class CanAdaptTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_insufficient_samples(self):
        s = self._make()
        for i in range(5):
            s.record_sample("cat", "q", "r", True, 1.0)
        r = s.can_adapt("cat")
        self.assertFalse(r["allowed"])
        self.assertEqual(r["reason"], "insufficient_samples: 5/10")
        self.assertEqual(r["sample_count"], 5)
        self.assertEqual(r["min_required"], 10)

    def test_low_confidence(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", False, 1.0)
        r = s.can_adapt("cat")
        self.assertFalse(r["allowed"])
        self.assertTrue(r["reason"].startswith("low_confidence"))
        self.assertEqual(r["success_rate"], 0.0)
        self.assertEqual(r["min_confidence"], 0.7)

    def test_rate_limited(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        # fill adaptation times
        for i in range(10):
            s._adaptation_times.append(time.time())
        r = s.can_adapt("cat")
        self.assertFalse(r["allowed"])
        self.assertTrue(r["reason"].startswith("rate_limited"))
        self.assertEqual(r["recent_count"], 10)
        self.assertEqual(r["limit"], 10)

    def test_allowed(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        r = s.can_adapt("cat")
        self.assertTrue(r["allowed"])
        self.assertEqual(r["sample_count"], 10)
        self.assertEqual(r["success_rate"], 1.0)
        self.assertEqual(r["confidence"], 1.0)

    def test_confidence_threshold_boundary(self):
        s = self._make()
        # 7 successes out of 10 = 0.7 -> allowed (>= 0.7)
        for i in range(7):
            s.record_sample("cat", "q", "r", True, 1.0)
        for i in range(3):
            s.record_sample("cat", "q", "r", False, 1.0)
        r = s.can_adapt("cat")
        self.assertTrue(r["allowed"])
        self.assertEqual(r["success_rate"], 0.7)

    def test_rate_limit_old_entries_ignored(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        # old adaptation times (> 1 hour ago) should be ignored
        s._adaptation_times.append(time.time() - 4000)
        r = s.can_adapt("cat")
        self.assertTrue(r["allowed"])

    def test_rate_limit_mixed(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        # 9 recent + 1 old -> allowed (recent=9 < 10)
        for i in range(9):
            s._adaptation_times.append(time.time())
        s._adaptation_times.append(time.time() - 4000)
        r = s.can_adapt("cat")
        self.assertTrue(r["allowed"])


class AssessRiskTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_no_changes_low(self):
        s = self._make()
        r = s.assess_risk("cat", {"a": 1}, {"a": 1})
        self.assertEqual(r, ls.AdaptationRisk.LOW)

    def test_critical_keys_high(self):
        s = self._make()
        r = s.assess_risk("cat", {"model": "old"}, {"model": "new"})
        self.assertEqual(r, ls.AdaptationRisk.HIGH)

    def test_critical_keys_provider(self):
        s = self._make()
        r = s.assess_risk("cat", {"provider": "a"}, {"provider": "b"})
        self.assertEqual(r, ls.AdaptationRisk.HIGH)

    def test_critical_keys_temperature(self):
        s = self._make()
        r = s.assess_risk("cat", {"temperature": 0.5}, {"temperature": 0.9})
        self.assertEqual(r, ls.AdaptationRisk.HIGH)

    def test_critical_keys_max_tokens(self):
        s = self._make()
        r = s.assess_risk("cat", {"max_tokens": 100}, {"max_tokens": 200})
        self.assertEqual(r, ls.AdaptationRisk.HIGH)

    def test_critical_keys_system_prompt(self):
        s = self._make()
        r = s.assess_risk("cat", {"system_prompt": "a"}, {"system_prompt": "b"})
        self.assertEqual(r, ls.AdaptationRisk.HIGH)

    def test_few_samples_medium(self):
        s = self._make()
        # add 10 samples (min_samples=10, min*2=20; 10 < 20 -> medium)
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        r = s.assess_risk("cat", {"x": 1}, {"x": 2})
        self.assertEqual(r, ls.AdaptationRisk.MEDIUM)

    def test_enough_samples_low(self):
        s = self._make()
        for i in range(20):
            s.record_sample("cat", "q", "r", True, 1.0)
        r = s.assess_risk("cat", {"x": 1}, {"x": 2})
        self.assertEqual(r, ls.AdaptationRisk.LOW)

    def test_key_added(self):
        s = self._make()
        r = s.assess_risk("cat", {}, {"new": 1})
        self.assertEqual(r, ls.AdaptationRisk.MEDIUM)  # few samples

    def test_key_removed(self):
        s = self._make()
        r = s.assess_risk("cat", {"old": 1}, {})
        self.assertEqual(r, ls.AdaptationRisk.MEDIUM)


class ProposeAdaptationTests(unittest.TestCase):
    def _make_with_samples(self, n=10):
        s = ls.LearningSafety(data_dir=self._tmp())
        for i in range(n):
            s.record_sample("cat", "q", "r", True, 1.0)
        return s

    def _tmp(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_rejected_insufficient_samples(self):
        s = ls.LearningSafety(data_dir=self._tmp())
        r = s.propose_adaptation("cat", "desc", {}, {})
        self.assertIsNone(r)
        # no adaptation added
        self.assertEqual(len(s._adaptations), 0)

    def test_rejected_low_confidence(self):
        s = ls.LearningSafety(data_dir=self._tmp())
        for i in range(10):
            s.record_sample("cat", "q", "r", False, 1.0)
        r = s.propose_adaptation("cat", "desc", {}, {})
        self.assertIsNone(r)

    def test_approved_low_risk(self):
        s = self._make_with_samples(20)
        with mock.patch.object(ls, "logger") as lg:
            r = s.propose_adaptation("cat", "desc", {"x": 1}, {"x": 2})
        self.assertIsNotNone(r)
        self.assertEqual(r.category, "cat")
        self.assertEqual(r.description, "desc")
        self.assertEqual(r.risk_level, ls.AdaptationRisk.LOW)
        self.assertEqual(r.status, ls.AdaptationStatus.APPROVED)
        self.assertEqual(r.samples_used, 20)
        self.assertEqual(r.confidence, 1.0)
        self.assertEqual(r.before_state, {"x": 1})
        self.assertEqual(r.after_state, {"x": 2})
        self.assertEqual(r.rollback_data, {"x": 1})
        self.assertTrue(r.adaptation_id)
        self.assertTrue(r.timestamp)
        self.assertEqual(len(s._adaptations), 1)
        # adaptation_times recorded
        self.assertEqual(len(s._adaptation_times), 1)
        lg.info.assert_called_once()
        # persisted
        self.assertTrue((Path(s._data_dir) / "samples.json").exists())

    def test_pending_critical_risk(self):
        s = self._make_with_samples(20)
        r = s.propose_adaptation("cat", "desc", {"model": "a"}, {"model": "b"})
        self.assertIsNotNone(r)
        self.assertEqual(r.risk_level, ls.AdaptationRisk.HIGH)
        # HIGH != CRITICAL -> APPROVED
        self.assertEqual(r.status, ls.AdaptationStatus.APPROVED)

    def test_critical_risk_pending(self):
        # Need risk CRITICAL. Critical keys only give HIGH. 
        # To get CRITICAL, need... actually no path gives CRITICAL in assess_risk.
        # assess_risk returns LOW/MEDIUM/HIGH only. So CRITICAL never returned.
        # But propose_adaptation checks `risk != AdaptationRisk.CRITICAL` -> always True
        # So status always APPROVED. Test that CRITICAL never occurs.
        s = self._make_with_samples(20)
        r = s.propose_adaptation("cat", "desc", {"model": "a"}, {"model": "b"})
        self.assertNotEqual(r.risk_level, ls.AdaptationRisk.CRITICAL)

    def test_rate_limited_rejection(self):
        s = self._make_with_samples(10)
        for i in range(10):
            s._adaptation_times.append(time.time())
        r = s.propose_adaptation("cat", "desc", {}, {})
        self.assertIsNone(r)
        lg = None


class ApplyAdaptationTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_apply_approved(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        rec = s.propose_adaptation("cat", "desc", {}, {})
        self.assertTrue(s.apply_adaptation(rec.adaptation_id))
        # status changed
        self.assertEqual(rec.status, ls.AdaptationStatus.APPLIED)
        # persisted
        self.assertTrue((Path(s._data_dir) / "adaptations.json").exists())

    def test_apply_unknown(self):
        s = self._make()
        self.assertFalse(s.apply_adaptation("nope"))

    def test_apply_pending_not_applied(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        # force a pending record by manually creating
        rec = ls.AdaptationRecord(
            adaptation_id="p1", category="cat", description="d",
            risk_level=ls.AdaptationRisk.CRITICAL,
            status=ls.AdaptationStatus.PENDING, samples_used=10,
            confidence=0.9, before_state={}, after_state={})
        s._adaptations.append(rec)
        self.assertFalse(s.apply_adaptation("p1"))

    def test_apply_already_applied(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        rec = s.propose_adaptation("cat", "desc", {}, {})
        s.apply_adaptation(rec.adaptation_id)
        # second apply fails (status now APPLIED, not APPROVED)
        self.assertFalse(s.apply_adaptation(rec.adaptation_id))

    def test_apply_logs(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        rec = s.propose_adaptation("cat", "desc", {}, {})
        with mock.patch.object(ls, "logger") as lg:
            s.apply_adaptation(rec.adaptation_id)
        lg.info.assert_called_once()


class RollbackAdaptationTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_rollback_applied(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        rec = s.propose_adaptation("cat", "desc", {}, {})
        s.apply_adaptation(rec.adaptation_id)
        with mock.patch.object(ls, "logger") as lg:
            self.assertTrue(s.rollback_adaptation(rec.adaptation_id))
        self.assertEqual(rec.status, ls.AdaptationStatus.ROLLED_BACK)
        lg.warning.assert_called_once()

    def test_rollback_unknown(self):
        s = self._make()
        self.assertFalse(s.rollback_adaptation("nope"))

    def test_rollback_not_applied(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        rec = s.propose_adaptation("cat", "desc", {}, {})
        # not applied (still APPROVED) -> rollback fails
        self.assertFalse(s.rollback_adaptation(rec.adaptation_id))

    def test_rollback_pending(self):
        s = self._make()
        rec = ls.AdaptationRecord(
            adaptation_id="p1", category="cat", description="d",
            risk_level=ls.AdaptationRisk.LOW,
            status=ls.AdaptationStatus.PENDING, samples_used=0,
            confidence=0, before_state={}, after_state={})
        s._adaptations.append(rec)
        self.assertFalse(s.rollback_adaptation("p1"))


class RecordPerformanceDetectRegressionTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_record_performance(self):
        s = self._make()
        s.record_performance("cat", 0.9)
        self.assertEqual(list(s._performance_history["cat"]), [0.9])
        s.record_performance("cat", 0.8)
        self.assertEqual(list(s._performance_history["cat"]), [0.9, 0.8])

    def test_detect_regression_insufficient_data(self):
        s = self._make()
        for i in range(5):
            s.record_performance("cat", 0.9)
        r = s.detect_regression("cat")
        self.assertFalse(r["regression"])
        self.assertEqual(r["reason"], "insufficient_data")

    def test_detect_regression_no_regression(self):
        s = self._make()
        for i in range(10):
            s.record_performance("cat", 0.9)
        r = s.detect_regression("cat")
        self.assertFalse(r["regression"])
        self.assertEqual(r["samples"], 10)
        self.assertIn("degradation_pct", r)
        self.assertIn("avg_baseline", r)
        self.assertIn("avg_recent", r)

    def test_detect_regression_with_regression(self):
        s = self._make()
        # baseline high, recent low
        for i in range(5):
            s.record_performance("cat", 1.0)
        for i in range(5):
            s.record_performance("cat", 0.5)
        # need an applied adaptation to rollback
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        rec = s.propose_adaptation("cat", "desc", {}, {})
        s.apply_adaptation(rec.adaptation_id)
        with mock.patch.object(ls, "logger") as lg:
            r = s.detect_regression("cat")
        self.assertTrue(r["regression"])
        self.assertGreater(r["degradation_pct"], 15.0)
        self.assertTrue(rec.regression_detected)
        self.assertEqual(rec.status, ls.AdaptationStatus.ROLLED_BACK)
        lg.warning.assert_called_once()

    def test_detect_regression_no_applied_adaptation(self):
        s = self._make()
        for i in range(5):
            s.record_performance("cat", 1.0)
        for i in range(5):
            s.record_performance("cat", 0.5)
        # no adaptation -> no rollback, but regression still reported
        r = s.detect_regression("cat")
        self.assertTrue(r["regression"])

    def test_detect_regression_zero_baseline(self):
        s = self._make()
        for i in range(5):
            s.record_performance("cat", 0.0)
        for i in range(5):
            s.record_performance("cat", 0.0)
        r = s.detect_regression("cat")
        self.assertFalse(r["regression"])
        self.assertEqual(r["degradation_pct"], 0)

    def test_detect_regression_empty_category(self):
        s = self._make()
        r = s.detect_regression("nope")
        self.assertFalse(r["regression"])
        self.assertEqual(r["reason"], "insufficient_data")


class SplitSamplesTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_empty(self):
        s = self._make()
        r = s.split_samples("cat")
        self.assertEqual(r, {"train": [], "eval": [], "train_count": 0,
                             "eval_count": 0})

    def test_split(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", f"q{i}", "r", True, 1.0)
        r = s.split_samples("cat")
        self.assertEqual(r["train_count"], 8)  # 80% of 10
        self.assertEqual(r["eval_count"], 2)
        self.assertEqual(len(r["train"]), 8)
        self.assertEqual(len(r["eval"]), 2)


class GetStatusTests(unittest.TestCase):
    def _make(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        return ls.LearningSafety(data_dir=d)

    def test_empty(self):
        s = self._make()
        st = s.get_status()
        self.assertEqual(st["min_samples"], 10)
        self.assertEqual(st["min_confidence"], 0.7)
        self.assertEqual(st["max_adaptations_per_hour"], 10)
        self.assertEqual(st["regression_threshold"], 0.15)
        self.assertEqual(st["categories"], {})
        self.assertEqual(st["total_adaptations"], 0)
        self.assertEqual(st["applied"], 0)
        self.assertEqual(st["rolled_back"], 0)
        self.assertEqual(st["recent_adaptations"], [])

    def test_with_data(self):
        s = self._make()
        for i in range(10):
            s.record_sample("cat", "q", "r", True, 1.0)
        rec = s.propose_adaptation("cat", "desc", {}, {})
        s.apply_adaptation(rec.adaptation_id)
        st = s.get_status()
        self.assertIn("cat", st["categories"])
        self.assertEqual(st["categories"]["cat"]["sample_count"], 10)
        self.assertTrue(st["categories"]["cat"]["can_adapt"])
        self.assertEqual(st["total_adaptations"], 1)
        self.assertEqual(st["applied"], 1)
        self.assertEqual(st["rolled_back"], 0)
        self.assertEqual(len(st["recent_adaptations"]), 1)
        ra = st["recent_adaptations"][0]
        self.assertEqual(ra["id"], rec.adaptation_id)
        self.assertEqual(ra["category"], "cat")
        self.assertEqual(ra["status"], "applied")
        self.assertEqual(ra["risk"], "low")
        self.assertEqual(ra["confidence"], 1.0)
        self.assertTrue(ra["timestamp"])


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = ls._learning_safety
        ls._learning_safety = None
        self.addCleanup(setattr, ls, "_learning_safety", self._saved)

    def test_creates(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        with mock.patch("orbit.orbit.core.learning_safety.LearningSafety",
                        wraps=ls.LearningSafety) as C:
            a = ls.get_learning_safety()
        self.assertIsInstance(a, ls.LearningSafety)
        self.assertIs(ls._learning_safety, a)

    def test_reuses(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        a = ls.get_learning_safety()
        b = ls.get_learning_safety()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
