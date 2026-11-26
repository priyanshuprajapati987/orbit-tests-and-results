"""Deep tests for orbit/orbit/text_utils.py (Loop 12/4).

Covers every statement:
  * ``word_count`` — empty, single word, multi-line, sentence counting.
  * ``count_format`` — exact formatted output.
  * ``base64_encode`` / ``base64_decode`` — round-trip + invalid input.
  * ``hash_text`` — md5/sha1/sha256/sha512 + default + unknown algo
    fallback to sha256.
  * ``case_convert`` — upper/lower/title/capitalize/swap/unknown.
  * ``extract_urls`` / ``extract_emails``.
  * ``remove_extra_spaces``.
  * ``slugify``.
  * ``parse_and_handle`` — every branch (wordcount, base64 encode/decode,
    hash, case, slug, urls) + fallthrough unknown.
"""

import base64
import hashlib
import unittest

from orbit.orbit import text_utils as tu


class WordCountTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(tu.word_count(""), {
            "words": 0, "characters": 0, "characters_no_space": 0,
            "lines": 1, "sentences": 0})

    def test_basic(self):
        r = tu.word_count("Hello world. How are you?")
        self.assertEqual(r["words"], 5)
        self.assertEqual(r["characters"], 25)
        self.assertEqual(r["characters_no_space"], 21)
        self.assertEqual(r["lines"], 1)
        self.assertEqual(r["sentences"], 2)

    def test_multiline(self):
        r = tu.word_count("a\nb\nc")
        self.assertEqual(r["lines"], 3)
        self.assertEqual(r["words"], 3)

    def test_sentences_with_exclamation(self):
        r = tu.word_count("Hi! Bye?")
        self.assertEqual(r["sentences"], 2)


class CountFormatTests(unittest.TestCase):
    def test_format(self):
        counts = {"words": 2, "characters": 11,
                  "characters_no_space": 9, "lines": 1, "sentences": 1}
        self.assertEqual(tu.count_format(counts),
                         "📊 **Text Stats:**\n"
                         "  Words: 2\n"
                         "  Characters: 11 (9 no space)\n"
                         "  Lines: 1\n"
                         "  Sentences: 1")


class Base64Tests(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(tu.base64_decode(tu.base64_encode("hello")), "hello")

    def test_encode_known(self):
        self.assertEqual(tu.base64_encode("hi"), base64.b64encode(b"hi").decode())

    def test_decode_invalid(self):
        self.assertEqual(tu.base64_decode("!!!not-base64!!!"),
                         "Invalid base64 input.")


class HashTests(unittest.TestCase):
    def test_default_sha256(self):
        r = tu.hash_text("abc")
        self.assertEqual(r["algorithm"], "sha256")
        self.assertEqual(r["hash"], hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(r["hex_length"], 64)

    def test_all_algos(self):
        for algo, fn in [("md5", hashlib.md5), ("sha1", hashlib.sha1),
                         ("sha256", hashlib.sha256),
                         ("sha512", hashlib.sha512)]:
            r = tu.hash_text("x", algo)
            self.assertEqual(r["algorithm"], algo)
            self.assertEqual(r["hash"], fn(b"x").hexdigest())
            self.assertEqual(r["hex_length"], len(fn(b"x").hexdigest()))

    def test_unknown_algo_falls_back_to_sha256(self):
        r = tu.hash_text("abc", "nope")
        self.assertEqual(r["algorithm"], "nope")
        self.assertEqual(r["hash"], hashlib.sha256(b"abc").hexdigest())


class CaseConvertTests(unittest.TestCase):
    def test_upper(self):
        self.assertEqual(tu.case_convert("hi", "upper"), "HI")

    def test_lower(self):
        self.assertEqual(tu.case_convert("HI", "lower"), "hi")

    def test_title(self):
        self.assertEqual(tu.case_convert("hello world", "title"), "Hello World")

    def test_capitalize(self):
        self.assertEqual(tu.case_convert("hello world", "capitalize"),
                         "Hello world")

    def test_swap(self):
        self.assertEqual(tu.case_convert("AbC", "swap"), "aBc")

    def test_unknown_returns_text(self):
        self.assertEqual(tu.case_convert("hi", "nope"), "hi")


class ExtractTests(unittest.TestCase):
    def test_extract_urls(self):
        self.assertEqual(tu.extract_urls("see https://a.com/x and http://b.org"),
                         ["https://a.com/x", "http://b.org"])

    def test_extract_urls_none(self):
        self.assertEqual(tu.extract_urls("no urls here"), [])

    def test_extract_emails(self):
        self.assertEqual(tu.extract_emails("mail me at a@b.com or c@d.org"),
                         ["a@b.com", "c@d.org"])

    def test_extract_emails_none(self):
        self.assertEqual(tu.extract_emails("no email"), [])


class RemoveExtraSpacesTests(unittest.TestCase):
    def test_collapses(self):
        self.assertEqual(tu.remove_extra_spaces("a   b\n\nc"), "a b c")

    def test_strip(self):
        self.assertEqual(tu.remove_extra_spaces("  hi  "), "hi")


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(tu.slugify("My Cool Post!"), "my-cool-post")

    def test_underscores(self):
        self.assertEqual(tu.slugify("a_b c"), "a-b-c")

    def test_strip_dashes(self):
        self.assertEqual(tu.slugify("  -hi-  "), "hi")


class ParseAndHandleTests(unittest.TestCase):
    def test_wordcount_branch(self):
        r = tu.parse_and_handle("word count hello world")
        self.assertEqual(r["type"], "wordcount")
        self.assertIn("Words: 2", r["result"])

    def test_wordcount_via_shabdon(self):
        r = tu.parse_and_handle("shabdon ki ginti foo bar baz")
        self.assertEqual(r["type"], "wordcount")

    def test_wordcount_short_text_falls_through(self):
        # cmd_text too short -> no wordcount return
        r = tu.parse_and_handle("count hi")
        # "hi" len 2 not > 2 -> falls to unknown
        self.assertEqual(r["type"], "unknown")

    def test_base64_decode_branch(self):
        import base64 as b64
        enc = b64.b64encode(b"secret").decode()
        r = tu.parse_and_handle(f"base64 decode {enc}")
        self.assertEqual(r["type"], "base64")
        self.assertIn("Decoded: `secret`", r["result"])

    def test_base64_decode_invalid(self):
        r = tu.parse_and_handle("base64 decode !!!")
        self.assertEqual(r["type"], "base64")
        self.assertIn("Decoded: ``", r["result"])

    def test_base64_encode_branch(self):
        r = tu.parse_and_handle("base64 encode hello")
        self.assertEqual(r["type"], "base64")
        self.assertIn("Base64: `", r["result"])

    def test_base64_encode_no_text_falls_through(self):
        r = tu.parse_and_handle("base64 encode")
        # cmd_text empty -> no return -> unknown
        self.assertEqual(r["type"], "unknown")

    def test_hash_branch_sha256(self):
        r = tu.parse_and_handle("sha256 hash abc")
        self.assertEqual(r["type"], "hash")
        self.assertIn("SHA256:", r["result"])

    def test_hash_branch_md5(self):
        r = tu.parse_and_handle("md5 hash abc")
        self.assertEqual(r["type"], "hash")
        self.assertIn("MD5:", r["result"])

    def test_hash_short_text_falls_through(self):
        r = tu.parse_and_handle("hash hi")
        self.assertEqual(r["type"], "unknown")

    def test_case_uppercase(self):
        r = tu.parse_and_handle("uppercase hello world")
        self.assertEqual(r["type"], "case")
        self.assertIn("Upper:", r["result"])
        self.assertIn("HELLO WORLD", r["result"])

    def test_case_lowercase(self):
        r = tu.parse_and_handle("lowercase HELLO")
        self.assertEqual(r["type"], "case")
        self.assertIn("Lower:", r["result"])

    def test_case_title(self):
        r = tu.parse_and_handle("title case hello world")
        self.assertEqual(r["type"], "case")
        self.assertIn("Title:", r["result"])

    def test_case_capitalize(self):
        r = tu.parse_and_handle("capitalize hello world")
        self.assertEqual(r["type"], "case")
        self.assertIn("Capitalize:", r["result"])

    def test_case_swap(self):
        r = tu.parse_and_handle("swap case AbC")
        self.assertEqual(r["type"], "case")
        self.assertIn("Swap:", r["result"])

    def test_case_short_text_falls_through(self):
        r = tu.parse_and_handle("uppercase hi")
        self.assertEqual(r["type"], "unknown")

    def test_slug_branch(self):
        r = tu.parse_and_handle("slugify My Cool Post")
        self.assertEqual(r["type"], "slug")
        self.assertIn("**Slug:** ify-my-cool-post", r["result"])

    def test_slug_no_text_falls_through(self):
        r = tu.parse_and_handle("slug")
        self.assertEqual(r["type"], "unknown")

    def test_urls_branch_found(self):
        r = tu.parse_and_handle("extract urls https://a.com/x http://b.org")
        self.assertEqual(r["type"], "urls")
        self.assertIn("https://a.com/x", r["result"])

    def test_urls_branch_none(self):
        r = tu.parse_and_handle("find urls in this text")
        self.assertEqual(r["type"], "info")
        self.assertIn("Koi URL nahi mila", r["result"])

    def test_unknown_fallthrough(self):
        r = tu.parse_and_handle("xyz qwerty")
        self.assertEqual(r["type"], "unknown")
        self.assertIn("Kya karna hai", r["result"])


if __name__ == "__main__":
    unittest.main()
