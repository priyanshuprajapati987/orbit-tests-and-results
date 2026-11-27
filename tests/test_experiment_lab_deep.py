"""Deep tests for orbit/orbit/core/experiment_lab.py (Loop 15/2)."""

import json
import threading
import unittest
from pathlib import Path
from unittest import mock

from orbit.orbit.core import experiment_lab as el


class InitLoadTests(unittest.TestCase):
    def setUp(self):
        self._orig_instance = el._instance
        el._instance = None
        self.addCleanup(setattr, el, "_instance", self._orig_instance)

    def test_init_creates_data_dir(self):
        with mock.patch("pathlib.Path.mkdir") as mk:
            lab = el.ExperimentLab()
        mk.assert_called_once_with(parents=True, exist_ok=True)
        self.assertTrue(hasattr(lab, "_lock"))

    def test_load_existing_file(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "experiments.json"
        p.write_text('[{"id":"e1","status":"active","results":[]}]', encoding="utf-8")
        with mock.patch.object(el.ExperimentLab, "_path", lambda self: p):
            with mock.patch("pathlib.Path.mkdir"):
                lab = el.ExperimentLab()
        self.assertEqual(len(lab._experiments), 1)
        self.assertEqual(lab._experiments[0]["id"], "e1")

    def test_load_corrupt_falls_back_to_defaults(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "experiments.json"
        p.write_text("{bad", encoding="utf-8")
        with mock.patch.object(el.ExperimentLab, "_path", lambda self: p):
            with mock.patch("pathlib.Path.mkdir"):
                lab = el.ExperimentLab()
        # falls back to DEFAULT_EXPERIMENTS and saves
        self.assertTrue(len(lab._experiments) >= 3)
        self.assertTrue(p.exists())

    def test_load_missing_uses_defaults(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = Path(d) / "experiments.json"
        with mock.patch.object(el.ExperimentLab, "_path", lambda self: p):
            with mock.patch("pathlib.Path.mkdir"):
                lab = el.ExperimentLab()
        self.assertEqual(len(lab._experiments), len(el.DEFAULT_EXPERIMENTS))
        self.assertTrue(p.exists())

    def test_save_failure(self):
        lab = el.ExperimentLab.__new__(el.ExperimentLab)
        lab._lock = threading.Lock()
        lab._experiments = []
        with mock.patch.object(lab, "_path") as pp:
            pp.return_value = Path("/tmp/x.json")
            with mock.patch.object(Path, "with_name", side_effect=OSError("nope")):
                ok = lab._save()
        self.assertFalse(ok)


class CreateExperimentTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._p = Path(self._d) / "experiments.json"
        with mock.patch.object(el.ExperimentLab, "_path", lambda self, _p=self._p: _p):
            with mock.patch("pathlib.Path.mkdir"):
                self.lab = el.ExperimentLab()

    def test_create(self):
        exp = self.lab.create_experiment("My Exp", "hyp", [
            {"name": "A", "description": "dA"}, {"description": "dB"}])
        self.assertTrue(exp["id"].startswith("exp_"))
        self.assertEqual(exp["name"], "My Exp")
        self.assertEqual(exp["hypothesis"], "hyp")
        self.assertEqual(exp["status"], "active")
        self.assertEqual(exp["variants"][0]["name"], "A")
        self.assertEqual(exp["variants"][1]["name"], "Variant 2")
        self.assertEqual(exp["variants"][1]["description"], "dB")
        self.assertEqual(exp["results"], [])
        self.assertIsNone(exp["winner"])
        self.assertIn("created_at", exp)
        # persisted
        self.assertEqual(len(self.lab.get_all()), 4)


class RecordResultTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._p = Path(self._d) / "experiments.json"
        with mock.patch.object(el.ExperimentLab, "_path", lambda self, _p=self._p: _p):
            with mock.patch("pathlib.Path.mkdir"):
                self.lab = el.ExperimentLab()
        self.exp = self.lab.create_experiment("E", "h", [
            {"name": "A"}, {"name": "B"}])

    def test_record_success(self):
        ok = self.lab.record_result(self.exp["id"], "A", 0.9, "details")
        self.assertTrue(ok)
        exp = self.lab.get_experiment(self.exp["id"])
        self.assertEqual(len(exp["results"]), 1)
        self.assertEqual(exp["results"][0]["variant"], "A")
        self.assertEqual(exp["results"][0]["metric"], 0.9)
        self.assertEqual(exp["results"][0]["details"], "details")
        self.assertIn("timestamp", exp["results"][0])

    def test_record_unknown_returns_false(self):
        self.assertFalse(self.lab.record_result("nope", "A", 1.0))

    def test_record_triggers_winner_after_min_samples(self):
        eid = self.exp["id"]
        # record 10 results for A with high metric and 10 for B with low
        for i in range(10):
            self.lab.record_result(eid, "A", 1.0)
        for i in range(10):
            self.lab.record_result(eid, "B", 0.1)
        exp = self.lab.get_experiment(eid)
        self.assertEqual(exp["winner"], "A")
        self.assertEqual(exp["status"], "completed")

    def test_no_winner_fewer_than_min_samples(self):
        eid = self.exp["id"]
        self.lab.record_result(eid, "A", 1.0)
        self.lab.record_result(eid, "B", 0.1)
        exp = self.lab.get_experiment(eid)
        self.assertIsNone(exp["winner"])
        self.assertEqual(exp["status"], "active")

    def test_no_winner_single_variant(self):
        eid = self.exp["id"]
        for i in range(12):
            self.lab.record_result(eid, "A", 1.0)
        exp = self.lab.get_experiment(eid)
        # only one variant -> no winner
        self.assertIsNone(exp["winner"])

    def test_no_winner_zero_metric(self):
        eid = self.exp["id"]
        for i in range(12):
            self.lab.record_result(eid, "A", 0.0)
            self.lab.record_result(eid, "B", 0.0)
        exp = self.lab.get_experiment(eid)
        # winner avg 0 -> not > 0 -> no winner
        self.assertIsNone(exp["winner"])


class CheckWinnerTests(unittest.TestCase):
    def test_min_samples_guard(self):
        lab = el.ExperimentLab.__new__(el.ExperimentLab)
        exp = {"results": [{"variant": "A", "metric": 1}], "winner": None,
               "status": "active"}
        lab._check_winner(exp)
        self.assertIsNone(exp["winner"])

    def test_less_than_two_variants(self):
        lab = el.ExperimentLab.__new__(el.ExperimentLab)
        results = [{"variant": "A", "metric": 1.0} for _ in range(12)]
        exp = {"results": results, "winner": None, "status": "active"}
        lab._check_winner(exp)
        self.assertIsNone(exp["winner"])


class GetTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        self._p = Path(self._d) / "experiments.json"
        with mock.patch.object(el.ExperimentLab, "_path", lambda self, _p=self._p: _p):
            with mock.patch("pathlib.Path.mkdir"):
                self.lab = el.ExperimentLab()

    def test_get_all_deepcopy(self):
        a = self.lab.get_all()
        a[0]["name"] = "MUTATED"
        self.assertNotEqual(self.lab.get_all()[0]["name"], "MUTATED")

    def test_get_experiment_found(self):
        eid = self.lab._experiments[0]["id"]
        r = self.lab.get_experiment(eid)
        self.assertEqual(r["id"], eid)
        # deepcopy
        r["name"] = "MUTATED"
        self.assertNotEqual(self.lab.get_experiment(eid)["name"], "MUTATED")

    def test_get_experiment_not_found(self):
        self.assertIsNone(self.lab.get_experiment("nope"))

    def test_get_results_found(self):
        eid = self.lab._experiments[0]["id"]
        # record some results
        self.lab.record_result(eid, "A", 1.0)
        self.lab.record_result(eid, "B", 2.0)
        r = self.lab.get_results(eid)
        self.assertEqual(r["total_results"], 2)
        self.assertIn("A", r["summary"])
        self.assertIn("B", r["summary"])
        self.assertEqual(r["summary"]["A"]["count"], 1)
        self.assertEqual(r["summary"]["A"]["avg"], 1.0)
        self.assertEqual(r["summary"]["A"]["min"], 1.0)
        self.assertEqual(r["summary"]["A"]["max"], 1.0)

    def test_get_results_empty_variants(self):
        eid = self.lab._experiments[0]["id"]
        r = self.lab.get_results(eid)
        self.assertEqual(r["total_results"], 0)
        self.assertEqual(r["summary"], {})
        self.assertFalse(r["has_winner"])

    def test_get_results_not_found(self):
        r = self.lab.get_results("nope")
        self.assertEqual(r, {"error": "experiment not found"})

    def test_get_stats(self):
        s = self.lab.get_stats()
        self.assertEqual(s["total"], len(self.lab._experiments))
        self.assertEqual(s["total"], s["active"] + s["completed"])
        self.assertGreaterEqual(s["total"], 3)


class SingletonTests(unittest.TestCase):
    def setUp(self):
        self._saved = el._instance
        el._instance = None
        self.addCleanup(setattr, el, "_instance", self._saved)

    def test_creates(self):
        import tempfile
        with mock.patch("orbit.orbit.core.experiment_lab.DATA_DIR") as dd:
            dd.mkdir = mock.MagicMock()
            # point _path to temp
            d = tempfile.mkdtemp()
            p = Path(d) / "experiments.json"
            with mock.patch.object(el.ExperimentLab, "_path", lambda self: p):
                a = el.get_experiment_lab()
        self.assertIsInstance(a, el.ExperimentLab)
        self.assertIs(el._instance, a)

    def test_reuses(self):
        import tempfile
        with mock.patch("orbit.orbit.core.experiment_lab.DATA_DIR") as dd:
            dd.mkdir = mock.MagicMock()
            d = tempfile.mkdtemp()
            p = Path(d) / "experiments.json"
            with mock.patch.object(el.ExperimentLab, "_path", lambda self: p):
                a = el.get_experiment_lab()
                b = el.get_experiment_lab()
        self.assertIs(a, b)


if __name__ == "__main__":
    unittest.main()
