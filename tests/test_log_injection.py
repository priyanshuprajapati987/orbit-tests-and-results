"""Regression tests: log-injection (CRLF forging) is stripped."""

import logging
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from orbit.orbit.logging_config import LogInjectionFilter


def test_crlf_stripped_from_message():
    f = LogInjectionFilter()
    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "line1\r\nline2", None, None
    )
    assert f.filter(rec) is True
    assert "\n" not in rec.msg and "\r" not in rec.msg
    assert rec.msg == "line1 line2"


def test_crlf_stripped_from_args():
    f = LogInjectionFilter()
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "val=%s", ("a\r\nb",), None)
    assert f.filter(rec) is True
    assert rec.args == ("a b",)


def test_non_str_msg_untouched():
    f = LogInjectionFilter()
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, 12345, None, None)
    assert f.filter(rec) is True
    assert rec.msg == 12345
