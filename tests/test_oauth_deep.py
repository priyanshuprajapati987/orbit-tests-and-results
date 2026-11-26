"""Deep tests for orbit/orbit/core/auth/oauth.py (Loop 11/5).

Covers every statement of the stdlib+requests OAuth code flows:
  * ``is_configured`` — google/github env-pair presence, case folding,
    unknown/None provider.
  * ``make_state`` — (state, verifier, challenge) triple, PKCE S256
    challenge recomputation, 10-min JWT claims, nonce/verifier entropy.
  * ``check_state`` — roundtrip, wrong provider, redirect mismatch,
    skipped redirect check, garbage token, non-dict claims.
  * ``authorize_url`` — google (PKCE params) and github (scope) query
    building, case-insensitive provider, unknown -> None.
  * ``exchange`` google — token/userinfo status gates, missing access,
    missing sub/email, name default, request exceptions.
  * ``exchange`` github — token/user status gates, missing id, direct
    email vs /user/emails fallback (primary+verified), non-200 emails,
    name -> login fallback, request exceptions.
"""

import os
import unittest
from urllib.parse import parse_qs, urlparse
from unittest import mock

from orbit.orbit.core.auth import oauth as oa
from orbit.orbit.core.auth import tokens as tok


def _resp(status, payload):
    m = mock.MagicMock()
    m.status_code = status
    m.json.return_value = payload
    return m


class IsConfiguredTests(unittest.TestCase):
    def test_google_configured(self):
        with mock.patch.dict(os.environ, {
                "GOOGLE_CLIENT_ID": "gid", "GOOGLE_CLIENT_SECRET": "gsec"}):
            self.assertTrue(oa.is_configured("google"))

    def test_google_missing_secret(self):
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "gid"},
                             clear=True):
            self.assertFalse(oa.is_configured("google"))

    def test_github_configured(self):
        with mock.patch.dict(os.environ, {
                "GITHUB_CLIENT_ID": "hid", "GITHUB_CLIENT_SECRET": "hsec"}):
            self.assertTrue(oa.is_configured("github"))

    def test_github_missing_id(self):
        with mock.patch.dict(os.environ, {"GITHUB_CLIENT_SECRET": "hsec"},
                             clear=True):
            self.assertFalse(oa.is_configured("github"))

    def test_case_insensitive_provider(self):
        with mock.patch.dict(os.environ, {
                "GOOGLE_CLIENT_ID": "gid", "GOOGLE_CLIENT_SECRET": "gsec"}):
            self.assertTrue(oa.is_configured("GOOGLE"))

    def test_unknown_provider_false(self):
        self.assertFalse(oa.is_configured("twitter"))

    def test_none_provider_false(self):
        self.assertFalse(oa.is_configured(None))


class StateTests(unittest.TestCase):
    def test_make_state_triple(self):
        state, verifier, challenge = oa.make_state(
            "google", "http://localhost/cb")
        self.assertIsInstance(state, str)
        self.assertIsInstance(verifier, str)
        self.assertTrue(verifier)
        # PKCE S256: challenge = b64url(sha256(verifier)) no padding
        import base64
        import hashlib
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        self.assertEqual(challenge, expected)

    def test_state_claims_and_expiry(self):
        state, _, _ = oa.make_state("github", "http://localhost/cb")
        claims = oa.check_state(state, "github", "http://localhost/cb")
        self.assertIsInstance(claims, dict)
        self.assertEqual(claims["provider"], "github")
        self.assertEqual(claims["redirect"], "http://localhost/cb")
        self.assertEqual(claims["exp"] - claims["iat"], 600)
        self.assertTrue(claims["nonce"])

    def test_entropy_between_calls(self):
        s1, v1, c1 = oa.make_state("google", "u")
        s2, v2, c2 = oa.make_state("google", "u")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(v1, v2)
        self.assertNotEqual(c1, c2)

    def test_oauth_secret_delegates_to_tokens(self):
        self.assertEqual(oa._oauth_secret(), tok._secret())

    def test_check_state_roundtrip(self):
        state, _, _ = oa.make_state("google", "http://x/cb")
        claims = oa.check_state(state, "google", "http://x/cb")
        self.assertEqual(claims["provider"], "google")

    def test_check_state_wrong_provider(self):
        state, _, _ = oa.make_state("google", "u")
        self.assertIsNone(oa.check_state(state, "github", "u"))

    def test_check_state_redirect_mismatch(self):
        state, _, _ = oa.make_state("google", "http://a/cb")
        self.assertIsNone(oa.check_state(state, "google", "http://b/cb"))

    def test_check_state_redirect_check_skipped_when_empty(self):
        state, _, _ = oa.make_state("google", "http://a/cb")
        self.assertIsNotNone(oa.check_state(state, "google"))

    def test_check_state_garbage_token(self):
        self.assertIsNone(oa.check_state("not-a-jwt", "google"))

    def test_check_state_non_dict_claims(self):
        with mock.patch.object(oa.jwt, "decode",
                               return_value=["not", "a", "dict"]):
            self.assertIsNone(oa.check_state("x", "google"))


class AuthorizeUrlTests(unittest.TestCase):
    def test_google_url(self):
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "gid"}):
            url, verifier = oa.authorize_url("google", "http://localhost/cb")
        self.assertTrue(url.startswith(oa.GOOGLE_AUTH + "?"))
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["scope"], ["openid email profile"])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["client_id"], ["gid"])
        self.assertEqual(q["redirect_uri"], ["http://localhost/cb"])
        self.assertTrue(verifier)
        # state inside the URL validates against the same provider+redirect
        self.assertIsNotNone(
            oa.check_state(q["state"][0], "google", "http://localhost/cb"))

    def test_github_url(self):
        with mock.patch.dict(os.environ, {"GITHUB_CLIENT_ID": "hid"}):
            url, verifier = oa.authorize_url("github", "http://localhost/cb")
        self.assertTrue(url.startswith(oa.GITHUB_AUTH + "?"))
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["scope"], ["read:user user:email"])
        self.assertEqual(q["client_id"], ["hid"])
        self.assertTrue(verifier)

    def test_case_insensitive_provider(self):
        url, _ = oa.authorize_url("Google", "u")
        self.assertTrue(url.startswith(oa.GOOGLE_AUTH + "?"))

    def test_unknown_provider_none(self):
        self.assertIsNone(oa.authorize_url("twitter", "u"))


class ExchangeGoogleTests(unittest.TestCase):
    def _exchange(self, token_resp=None, user_resp=None, post_exc=None):
        with mock.patch("requests.post") as post, \
                mock.patch("requests.get") as get:
            if post_exc is not None:
                post.side_effect = post_exc
            else:
                post.return_value = token_resp
            get.return_value = user_resp
            with mock.patch.dict(os.environ, {
                    "GOOGLE_CLIENT_ID": "gid",
                    "GOOGLE_CLIENT_SECRET": "gsec"}):
                result = oa.exchange("google", "thecode",
                                     "http://localhost/cb", "verif")
            return result, post, get

    def test_happy_path(self):
        result, post, get = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"sub": "u1", "email": "a@b.c", "name": "Ann"}))
        self.assertEqual(result, {"subject": "google:u1",
                                  "email": "a@b.c", "name": "Ann"})
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["code"], "thecode")
        self.assertEqual(data["grant_type"], "authorization_code")
        self.assertEqual(data["code_verifier"], "verif")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"],
                         "Bearer at")

    def test_token_http_error(self):
        result, post, _ = self._exchange(token_resp=_resp(400, {}))
        self.assertIsNone(result)

    def test_token_warning_logged(self):
        with mock.patch.object(oa.logger, "warning") as warn:
            self._exchange(token_resp=_resp(500, {}))
        warn.assert_called_once()

    def test_missing_access_token(self):
        result, _, get = self._exchange(_resp(200, {}))
        self.assertIsNone(result)
        get.assert_not_called()

    def test_userinfo_http_error(self):
        result, _, _ = self._exchange(_resp(200, {"access_token": "at"}),
                                      _resp(401, {}))
        self.assertIsNone(result)

    def test_missing_sub(self):
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"email": "a@b.c"}))
        self.assertIsNone(result)

    def test_missing_email(self):
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"sub": "u1"}))
        self.assertIsNone(result)

    def test_name_defaults_to_empty(self):
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"sub": "u1", "email": "a@b.c"}))
        self.assertEqual(result["name"], "")

    def test_request_exception_returns_none(self):
        with mock.patch.object(oa.logger, "warning") as warn:
            result, _, _ = self._exchange(post_exc=RuntimeError("net down"))
        self.assertIsNone(result)
        warn.assert_called_once()


class ExchangeGithubTests(unittest.TestCase):
    def _exchange(self, token_resp, user_resp, emails_resp=None,
                  emails_exc=False):
        with mock.patch("requests.post") as post, \
                mock.patch("requests.get") as get:
            post.return_value = token_resp
            if emails_resp is not None or emails_exc:
                get.side_effect = [user_resp, emails_resp] if not emails_exc \
                    else [user_resp, RuntimeError("net down")]
            else:
                get.return_value = user_resp
            with mock.patch.dict(os.environ, {
                    "GITHUB_CLIENT_ID": "hid",
                    "GITHUB_CLIENT_SECRET": "hsec"}):
                result = oa.exchange("github", "thecode",
                                     "http://localhost/cb")
            return result, post, get

    def test_happy_path_direct_email(self):
        result, post, get = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"id": 7, "email": "a@b.c", "name": "Ann"}))
        self.assertEqual(result, {"subject": "github:7",
                                  "email": "a@b.c", "name": "Ann"})
        self.assertEqual(post.call_args.kwargs["headers"]["Accept"],
                         "application/json")
        get.assert_called_once()  # no /user/emails call needed

    def test_name_falls_back_to_login(self):
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"id": 7, "email": "a@b.c", "login": "ann"}))
        self.assertEqual(result["name"], "ann")

    def test_token_http_error(self):
        result, _, get = self._exchange(_resp(403, {}), _resp(200, {}))
        self.assertIsNone(result)
        get.assert_not_called()

    def test_missing_access_token(self):
        result, _, get = self._exchange(_resp(200, {}), _resp(200, {}))
        self.assertIsNone(result)
        get.assert_not_called()

    def test_user_http_error(self):
        result, _, _ = self._exchange(_resp(200, {"access_token": "at"}),
                                      _resp(401, {}))
        self.assertIsNone(result)

    def test_missing_id(self):
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"email": "a@b.c"}))
        self.assertIsNone(result)

    def test_emails_fallback_primary_verified(self):
        emails = [
            {"email": "other@x.c", "primary": False, "verified": True},
            {"email": "main@x.c", "primary": True, "verified": True},
        ]
        result, _, get = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"id": 7, "email": None, "login": "ann"}),
            emails_resp=_resp(200, emails))
        self.assertEqual(result["email"], "main@x.c")
        self.assertEqual(result["name"], "ann")
        self.assertEqual(get.call_count, 2)
        # both calls share the same auth headers
        self.assertEqual(get.call_args_list[0].kwargs["headers"],
                         get.call_args_list[1].kwargs["headers"])

    def test_emails_fallback_no_primary_verified(self):
        emails = [{"email": "other@x.c", "primary": False, "verified": True}]
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"id": 7, "email": "", "login": "ann"}),
            emails_resp=_resp(200, emails))
        self.assertIsNone(result)

    def test_emails_http_error(self):
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"id": 7, "email": "", "login": "ann"}),
            emails_resp=_resp(500, []))
        self.assertIsNone(result)

    def test_emails_empty_list(self):
        result, _, _ = self._exchange(
            _resp(200, {"access_token": "at"}),
            _resp(200, {"id": 7, "email": "", "login": "ann"}),
            emails_resp=_resp(200, []))
        self.assertIsNone(result)

    def test_request_exception_returns_none(self):
        with mock.patch.object(oa.logger, "warning") as warn:
            result, _, _ = self._exchange(
                _resp(200, {"access_token": "at"}),
                _resp(200, {"id": 7, "email": "", "login": "ann"}),
                emails_exc=True)
        self.assertIsNone(result)
        warn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
