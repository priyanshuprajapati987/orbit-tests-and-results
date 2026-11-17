"""Unit tests for orbit/orbit/core/calculator.py."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.core.calculator import Calculator, get_calculator, SAFE_OPS


class TestCalculate(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_addition(self):
        r = self.calc.calculate("2 + 3")
        self.assertEqual(r["result"], 5)
        self.assertEqual(r["expression"], "2 + 3")

    def test_subtraction(self):
        self.assertEqual(self.calc.calculate("10 - 4")["result"], 6)

    def test_multiplication(self):
        self.assertEqual(self.calc.calculate("6 * 7")["result"], 42)

    def test_division(self):
        self.assertEqual(self.calc.calculate("10 / 4")["result"], 2.5)

    def test_floor_division(self):
        self.assertEqual(self.calc.calculate("10 // 3")["result"], 3)

    def test_modulo(self):
        self.assertEqual(self.calc.calculate("10 % 3")["result"], 1)

    def test_power(self):
        self.assertEqual(self.calc.calculate("2 ** 10")["result"], 1024)

    def test_negative_unary(self):
        self.assertEqual(self.calc.calculate("-5")["result"], -5)

    def test_positive_unary(self):
        self.assertEqual(self.calc.calculate("+5")["result"], 5)

    def test_nested_expression(self):
        self.assertEqual(self.calc.calculate("(2 + 3) * 4")["result"], 20)

    def test_float(self):
        self.assertAlmostEqual(self.calc.calculate("3.14 * 2")["result"], 6.28)

    def test_leading_trailing_spaces(self):
        self.assertEqual(self.calc.calculate("  1 + 1  ")["result"], 2)

    def test_empty_expression(self):
        r = self.calc.calculate("")
        self.assertEqual(r["error"], "empty expression")

    def test_whitespace_only(self):
        r = self.calc.calculate("   ")
        self.assertEqual(r["error"], "empty expression")

    def test_division_by_zero(self):
        r = self.calc.calculate("1 / 0")
        self.assertEqual(r["error"], "division by zero")

    def test_modulo_zero(self):
        r = self.calc.calculate("1 % 0")
        self.assertEqual(r["error"], "division by zero")

    def test_syntax_error(self):
        r = self.calc.calculate("2 +")
        self.assertIn("error", r)

    def test_name_rejected(self):
        # name is not a supported node -> error
        r = self.calc.calculate("foo")
        self.assertIn("error", r)

    def test_call_rejected(self):
        r = self.calc.calculate("__import__('os')")
        self.assertIn("error", r)

    def test_string_constant_rejected(self):
        r = self.calc.calculate('"hello"')
        self.assertIn("error", r)

    def test_bool_constant_treated_as_int(self):
        # bool is a subclass of int in Python -> passes isinstance(int) check
        r = self.calc.calculate("True")
        self.assertEqual(r["result"], True)

    def test_list_rejected(self):
        r = self.calc.calculate("[1, 2]")
        self.assertIn("error", r)

    def test_bitwise_and_rejected(self):
        # ast.BitAnd not in SAFE_OPS
        r = self.calc.calculate("5 & 3")
        self.assertIn("error", r)

    def test_bitwise_or_rejected(self):
        r = self.calc.calculate("5 | 3")
        self.assertIn("error", r)

    def test_left_shift_rejected(self):
        r = self.calc.calculate("1 << 3")
        self.assertIn("error", r)

    def test_matmul_rejected(self):
        r = self.calc.calculate("1 @ 2")
        self.assertIn("error", r)

    def test_bitwise_not_rejected(self):
        # ast.Invert not in SAFE_OPS
        r = self.calc.calculate("~5")
        self.assertIn("error", r)

    def test_none_input(self):
        r = self.calc.calculate(None)
        self.assertIn("error", r)

    def test_number_input(self):
        r = self.calc.calculate(42)
        self.assertIn("error", r)


class TestPercentage(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_basic(self):
        r = self.calc.percentage(200, 50)
        self.assertEqual(r["result"], 100)
        self.assertEqual(r["value"], 200)
        self.assertEqual(r["percent"], 50)

    def test_zero_percent(self):
        self.assertEqual(self.calc.percentage(100, 0)["result"], 0)

    def test_float(self):
        self.assertAlmostEqual(self.calc.percentage(33.3, 15)["result"], 4.995)

    def test_over_100(self):
        self.assertEqual(self.calc.percentage(10, 200)["result"], 20)


class TestUnitConvert(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def test_km_to_mile(self):
        r = self.calc.unit_convert(1, "km", "mile")
        self.assertAlmostEqual(r["result"], 0.6214, places=4)
        self.assertEqual(r["from"], "1 km")
        self.assertEqual(r["to"], "0.6214 mile")

    def test_mile_to_km(self):
        r = self.calc.unit_convert(1, "mile", "km")
        self.assertAlmostEqual(r["result"], 1.6093, places=4)

    def test_kg_to_lb(self):
        r = self.calc.unit_convert(1, "kg", "lb")
        self.assertAlmostEqual(r["result"], 2.2046, places=4)

    def test_lb_to_kg(self):
        r = self.calc.unit_convert(1, "lb", "kg")
        self.assertAlmostEqual(r["result"], 0.4536, places=4)

    def test_c_to_f(self):
        r = self.calc.unit_convert(100, "c", "f")
        self.assertEqual(r["result"], 212.0)

    def test_f_to_c(self):
        r = self.calc.unit_convert(32, "f", "c")
        self.assertAlmostEqual(r["result"], 0.0, places=4)

    def test_case_insensitive(self):
        r = self.calc.unit_convert(1, "KM", "MILE")
        self.assertNotIn("error", r)

    def test_unknown_conversion(self):
        r = self.calc.unit_convert(1, "kg", "stone")
        self.assertIn("error", r)
        self.assertIn("Unknown conversion", r["error"])

    def test_same_unit_unknown(self):
        r = self.calc.unit_convert(1, "km", "km")
        self.assertIn("error", r)


class TestGetCalculator(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_calculator(), get_calculator())

    def test_type(self):
        self.assertIsInstance(get_calculator(), Calculator)

    def test_safe_ops_complete(self):
        import ast
        for op in [ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
                   ast.Mod, ast.Pow, ast.USub, ast.UAdd]:
            self.assertIn(op, SAFE_OPS)


if __name__ == "__main__":
    unittest.main()
