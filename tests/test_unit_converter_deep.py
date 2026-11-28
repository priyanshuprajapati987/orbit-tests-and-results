"""Deep tests for orbit/orbit/core/unit_converter.py (Loop 24/2)."""
import unittest
from orbit.orbit.core import unit_converter as uc

class ConvertTests(unittest.TestCase):
    def setUp(self): self.c = uc.UnitConverter()
    def test_length(self):
        r = self.c.convert(1000,"m","km")
        self.assertEqual(r["value"],1.0)
        self.assertEqual(r["category"],"length")
    def test_mass(self):
        r = self.c.convert(1,"kg","g")
        self.assertEqual(r["value"],1000.0)
    def test_temp_c_to_f(self):
        r = self.c.convert(0,"C","F")
        self.assertEqual(r["value"],32.0)
    def test_temp_f_to_c(self):
        r = self.c.convert(32,"F","C")
        self.assertEqual(r["value"],0.0)
    def test_temp_k(self):
        r = self.c.convert(0,"C","K")
        self.assertEqual(r["value"],273.15)
    def test_speed(self):
        r = self.c.convert(1,"m/s","km/h")
        self.assertAlmostEqual(r["value"],3.6,places=5)
    def test_data(self):
        r = self.c.convert(1,"GB","MB")
        self.assertEqual(r["value"],1024.0)
    def test_time(self):
        r = self.c.convert(1,"hour","sec")
        self.assertEqual(r["value"],3600.0)
    def test_category_explicit(self):
        r = self.c.convert(5,"m","km",category="length")
        self.assertEqual(r["value"],0.005)
    def test_unknown_units(self):
        r = self.c.convert(1,"foo","bar")
        self.assertIn("error", r)
    def test_units_not_in_category(self):
        r = self.c.convert(1,"m","g",category="length")
        self.assertIn("error", r)
    def test_input_output_strings(self):
        r = self.c.convert(1,"m","km")
        self.assertEqual(r["input"],"1 m")
        self.assertIn("km", r["output"])

class ListCategoriesTests(unittest.TestCase):
    def test(self):
        c = uc.UnitConverter()
        cats = c.list_categories()
        self.assertIn("length", cats)
        self.assertIn("m", cats["length"])

class SingletonTests(unittest.TestCase):
    def test(self):
        uc._converter = None
        a = uc.get_converter(); b = uc.get_converter()
        self.assertIs(a,b)
        uc._converter = None

if __name__ == "__main__":
    unittest.main()
