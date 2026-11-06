"""Unit tests batch 2 for utility modules: password_gen, text_utils, json_tools, random_utils, timer, sysinfo."""

import os
import sys
import unittest

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.password_gen import generate, generate_pin, strength, format_password, format_strength, parse_text, format_result
from orbit.text_utils import word_count, count_format, base64_encode, base64_decode, hash_text, case_convert, extract_urls, extract_emails, remove_extra_spaces, slugify, parse_and_handle
from orbit.json_tools import format_json, minify_json, validate_json, extract_keys, format_validation, parse_and_handle as json_parse
from orbit.random_utils import coin_flip, dice_roll, random_number, pick_option, yes_no, lucky_number, parse_text as ru_parse, format_result as ru_format
from orbit.timer import start, stop, status, format_status, parse_text as timer_parse
from orbit.sysinfo import get_info, get_battery, format_info, format_battery, format_cpu, parse_text as sys_parse


class TestPasswordGen(unittest.TestCase):
    def test_generate_default(self):
        r = generate()
        self.assertIsInstance(r, list)
        self.assertGreater(len(r), 0)
        self.assertIn("password", r[0])

    def test_generate_pin(self):
        r = generate_pin(4)
        self.assertEqual(len(r), 4)
        self.assertTrue(r.isdigit())

    def test_strength(self):
        r = strength("abc123XYZ!")
        self.assertIsInstance(r, dict)

    def test_format_password(self):
        r = format_password({"password": "abc123", "length": 6, "entropy": 30.0})
        self.assertIsInstance(r, str)

    def test_format_strength(self):
        r = format_strength(strength("abc123XYZ!"))
        self.assertIsInstance(r, str)

    def test_parse_text(self):
        r = parse_text("generate password length 12")
        self.assertIsNotNone(r)

    def test_format_result(self):
        r = format_result({"result": "abc"})
        self.assertIsInstance(r, str)


class TestTextUtils(unittest.TestCase):
    def test_word_count(self):
        r = word_count("hello world")
        self.assertIsInstance(r, dict)

    def test_count_format(self):
        r = count_format(word_count("hello world"))
        self.assertIsInstance(r, str)

    def test_base64_encode(self):
        r = base64_encode("hello")
        self.assertIsInstance(r, str)

    def test_base64_decode(self):
        enc = base64_encode("hello")
        r = base64_decode(enc)
        self.assertIn("hello", str(r))

    def test_hash_text(self):
        r = hash_text("hello")
        self.assertIsInstance(r, dict)

    def test_case_convert_upper(self):
        r = case_convert("hello", "upper")
        self.assertIn("HELLO", str(r))

    def test_extract_urls(self):
        r = extract_urls("visit https://example.com now")
        self.assertTrue(len(r) >= 1)

    def test_extract_emails(self):
        r = extract_emails("mail me at a@b.com")
        self.assertTrue(len(r) >= 1)

    def test_remove_extra_spaces(self):
        self.assertEqual(remove_extra_spaces("a   b"), "a b")

    def test_slugify(self):
        r = slugify("Hello World!")
        self.assertIsNotNone(r)

    def test_parse_and_handle(self):
        r = parse_and_handle("count words in hello world")
        self.assertIsNotNone(r)


class TestJsonTools(unittest.TestCase):
    def test_format_json(self):
        r = format_json('{"a":1}')
        self.assertIsInstance(r, dict)

    def test_minify_json(self):
        r = minify_json('{"a": 1}')
        self.assertIsInstance(r, dict)

    def test_validate_json_valid(self):
        r = validate_json('{"a":1}')
        self.assertIsInstance(r, dict)

    def test_validate_json_invalid(self):
        r = validate_json('{bad')
        self.assertIsInstance(r, dict)

    def test_extract_keys(self):
        r = extract_keys('{"a":1,"b":2}')
        self.assertIsInstance(r, list)

    def test_format_validation(self):
        r = format_validation(validate_json('{"a":1}'))
        self.assertIsInstance(r, str)

    def test_parse_and_handle(self):
        r = json_parse('{"a":1}')
        self.assertIsNotNone(r)


class TestRandomUtils(unittest.TestCase):
    def test_coin_flip(self):
        r = coin_flip()
        self.assertIsInstance(r, str)

    def test_dice_roll(self):
        r = dice_roll(6)
        self.assertIsInstance(r, str)

    def test_random_number(self):
        r = random_number(1, 10)
        self.assertIsInstance(r, str)

    def test_pick_option(self):
        r = pick_option(["a", "b", "c"])
        self.assertTrue(any(opt in r for opt in ["a", "b", "c"]))

    def test_yes_no(self):
        r = yes_no()
        self.assertIsInstance(r, str)

    def test_lucky_number(self):
        r = lucky_number()
        self.assertIsNotNone(r)

    def test_parse_text(self):
        r = ru_parse("flip a coin")
        self.assertIsNotNone(r)

    def test_format_result(self):
        r = ru_format({"type": "coin", "result": "heads"})
        self.assertIsInstance(r, str)


class TestTimer(unittest.TestCase):
    def test_start(self):
        r = start(60, "test_timer_xyz")
        self.assertIsNotNone(r)

    def test_status(self):
        start(60, "test_timer_xyz")
        r = status("test_timer_xyz")
        self.assertIsNotNone(r)

    def test_format_status(self):
        r = format_status("test_timer_xyz")
        self.assertIsNotNone(r)

    def test_stop(self):
        start(60, "test_timer_xyz")
        r = stop("test_timer_xyz")
        self.assertIsNotNone(r)

    def test_parse_text(self):
        r = timer_parse("start timer")
        self.assertIsNotNone(r)


class TestSysinfo(unittest.TestCase):
    def test_get_info(self):
        r = get_info()
        self.assertIsNotNone(r)

    def test_get_battery(self):
        r = get_battery()
        self.assertIsNotNone(r)

    def test_format_info(self):
        r = format_info()
        self.assertIsNotNone(r)

    def test_format_battery(self):
        r = format_battery()
        self.assertIsNotNone(r)

    def test_format_cpu(self):
        r = format_cpu()
        self.assertIsNotNone(r)

    def test_parse_text(self):
        r = sys_parse("system info")
        self.assertIsNotNone(r)


if __name__ == "__main__":
    unittest.main()
