"""SSRF regression tests.

Guards against:
- direct fetch to cloud metadata / private IPs
- redirect-based bypass (302 -> http://169.254.169.254/latest/meta-data/)
- localhost on non-allowlisted ports
"""

from unittest import mock

import pytest

from orbit.orbit.core import safe_http
from orbit.orbit.core.ssrf_guard import get_ssrf_guard


class _FakeResp:
    def __init__(self, status=200, headers=None, url="http://example.com/"):
        self.status_code = status
        self.headers = headers or {}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_metadata_endpoint_blocked():
    err = get_ssrf_guard().validate_outbound("http://169.254.169.254/latest/meta-data/")
    assert err is not None


def test_private_ip_blocked():
    err = get_ssrf_guard().validate_outbound("http://10.0.0.5/admin")
    assert err is not None


def test_localhost_unusual_port_blocked():
    # 127.0.0.1 is allowlisted only on specific ports.
    err = get_ssrf_guard().validate_outbound("http://127.0.0.1:9999/secret")
    assert err is not None


def test_redirect_to_metadata_blocked():
    with (
        mock.patch(
            "requests.request",
            return_value=_FakeResp(
                302,
                {"Location": "http://169.254.169.254/latest/meta-data/"},
                url="http://evil.example/",
            ),
        ),
        pytest.raises(Exception),  # noqa: B017
    ):
        safe_http.safe_requests_get("http://evil.example/")


def test_redirect_to_private_ip_blocked():
    with (
        mock.patch(
            "requests.request",
            return_value=_FakeResp(
                302, {"Location": "http://192.168.1.1/"}, url="http://evil.example/"
            ),
        ),
        pytest.raises(Exception),  # noqa: B017
    ):
        safe_http.safe_requests_get("http://evil.example/")


def test_external_url_allowed():

    pub = ("93.184.216.34", None, None, None, ("93.184.216.34", 0))
    with (
        mock.patch(
            "requests.request",
            return_value=_FakeResp(200, url="http://example.com/"),
        ),
        mock.patch(
            "orbit.orbit.core.ssrf_guard.socket.getaddrinfo",
            return_value=[(None, None, None, None, pub)],
        ),
    ):
        # Should not raise; public IP is allowed through the chain validator.
        try:
            safe_http.assert_safe("http://example.com/")
        except Exception as e:  # noqa: BLE001
            pytest.fail(f"Legitimate external URL wrongly blocked: {e}")


def test_safe_requests_get_does_not_follow_to_internal():
    # Even if the final GET were attempted, the chain validator must stop it
    # before any external/internal fetch.
    with (
        mock.patch(
            "requests.request",
            return_value=_FakeResp(
                302, {"Location": "http://127.0.0.1:9999/"}, url="http://evil.example/"
            ),
        ),
        pytest.raises(Exception),  # noqa: B017
    ):
        safe_http.safe_requests_post("http://evil.example/", json={"x": 1})
