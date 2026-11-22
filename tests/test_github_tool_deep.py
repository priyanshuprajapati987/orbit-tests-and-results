"""Deep coverage tests for orbit/orbit/tools/github_tool.py (782 lines).

test_github_tool.py covers the happy paths; this file targets everything it
misses: gate-denied returns, _check / import-failure branches, _get_client
fallbacks, every method's exception path, limit-break pagination, None-field
handling (PR issues, missing users/authors), mergeable/review-event guards,
workflow_id branching, git subprocess failures, and handle_natural fallbacks.
The PyGithub client is a fake object graph — no network.
"""

import importlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("ORBIT_SKIP_STARTUP", "1")
os.environ.setdefault("ORBIT_API_AUTH_ENABLED", "0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orbit"))

from orbit.orbit.tools import github_tool as gh  # noqa: E402


# ---------------------------------------------------------------------------
# Fake object graph
# ---------------------------------------------------------------------------


def _repo(name="repo-a", full="me/repo-a"):
    r = MagicMock(name=f"repo:{name}")
    r.name = name
    r.full_name = full
    r.description = "desc"
    r.language = "Python"
    r.stargazers_count = 10
    r.forks_count = 2
    r.open_issues_count = 1
    r.private = False
    r.default_branch = "main"
    r.created_at = "2026-01-01"
    r.updated_at = "2026-01-02"
    r.html_url = f"https://github.com/{full}"
    r.license = None
    r.get_topics.return_value = ["ai"]
    return r


def _issue(number=1, title="bug", pr=None, user="alice"):
    i = MagicMock(name=f"issue:{number}")
    i.number = number
    i.title = title
    i.state = "open"
    i.body = "body" * 100
    i.labels = [SimpleNamespace(name="bug")]
    i.assignees = [SimpleNamespace(login="bob")]
    i.comments = 3
    i.created_at = "2026-01-01"
    i.updated_at = "2026-01-02"
    i.html_url = f"https://github.com/me/repo-a/issues/{number}"
    i.pull_request = pr  # None -> real issue; truthy -> skipped in listing
    i.user = SimpleNamespace(login=user) if user else None
    return i


def _pr(number=7, mergeable=True):
    p = MagicMock(name=f"pr:{number}")
    p.number = number
    p.title = "feat"
    p.state = "open"
    p.body = "pr body"
    p.user = SimpleNamespace(login="carol")
    p.head = SimpleNamespace(ref="feature")
    p.base = SimpleNamespace(ref="main")
    p.mergeable = mergeable
    p.merged = False
    p.comments = 1
    p.review_comments = 2
    p.changed_files = 3
    p.additions = 10
    p.deletions = 5
    p.created_at = "2026-01-01"
    p.updated_at = "2026-01-02"
    p.html_url = "https://github.com/me/repo-a/pull/7"
    return p


def _commit(sha="abcdef1234567890", author=True):
    c = MagicMock(name="commit")
    c.sha = sha
    c.commit.message = "fix stuff"
    c.commit.author = (SimpleNamespace(name="Dev", date="2026-01-01")
                       if author else None)
    c.html_url = "https://github.com/me/repo-a/commit/x"
    return c


def _client(**overrides):
    """Fake PyGithub client with a configured repo/user."""
    c = MagicMock(name="github-client")
    c.get_repo.return_value = _repo()
    u = MagicMock(name="user")
    u.login = "me"
    u.name = "Me"
    u.public_repos = 5
    u.followers = 6
    u.following = 7
    c.get_user.return_value = u
    c.search_repositories.return_value = [_repo("s1", "me/s1"),
                                          _repo("s2", "me/s2")]
    for k, v in overrides.items():
        getattr(c, k).return_value = v
    return c


class GithubBase(unittest.TestCase):
    def make_tool(self, client=None, user=None, token="tok"):
        t = gh.GitHubTool(token=token)
        t._client = client if client is not None else _client()
        t._user = user  # None -> _user_obj falls back to client.get_user()
        return t

    @staticmethod
    def allow():
        return patch.object(gh, "check_tool",
                            return_value=SimpleNamespace(allowed=True))

    @staticmethod
    def deny():
        # Real policy: strict mode denies every github action.
        return patch.object(
            gh, "check_tool",
            return_value=SimpleNamespace(
                allowed=False, reason="strict_mode",
                to_dict=lambda: {"allowed": False, "reason": "strict_mode"}))


# ---------------------------------------------------------------------------
# Module-level: _check / import failure / factory
# ---------------------------------------------------------------------------


class TestModuleGuards(GithubBase):
    def test_check_raises_when_unavailable(self):
        with patch.object(gh, "GITHUB_AVAILABLE", False):
            with self.assertRaises(RuntimeError) as cm:
                gh._check()
        self.assertIn("PyGithub", str(cm.exception))

    def test_check_passes_when_available(self):
        with patch.object(gh, "GITHUB_AVAILABLE", True):
            gh._check()  # must not raise

    def test_import_failure_branch(self):
        # Simulate PyGithub missing at import time (lines 25-26), then
        # restore the module so later tests see the real availability.
        try:
            with patch.dict(sys.modules, {"github": None}):
                importlib.reload(gh)
                self.assertFalse(gh.GITHUB_AVAILABLE)
                t = gh.GitHubTool(token="tok")
                with self.assertRaises(RuntimeError):
                    t._get_client()
                self.assertEqual(
                    t.get_status(),
                    {"available": False,
                     "error": "PyGithub not installed"})
        finally:
            importlib.reload(gh)
        self.assertTrue(gh.GITHUB_AVAILABLE)

    def test_factory_returns_configured_tool(self):
        t = gh.get_github_tool(token="abc")
        self.assertIsInstance(t, gh.GitHubTool)
        self.assertEqual(t._token, "abc")
        t2 = gh.get_github_tool()
        self.assertEqual(t2._token, os.environ.get("GITHUB_TOKEN", ""))


# ---------------------------------------------------------------------------
# _gate (40-48) — denied path via REAL policy
# ---------------------------------------------------------------------------


class TestGateDenied(GithubBase):
    GATED = [
        ("create_repo", ("name",)),
        ("delete_repo", ("me/repo-a",)),
        ("fork_repo", ("me/repo-a",)),
        ("create_issue", ("me/repo-a", "title")),
        ("close_issue", ("me/repo-a", 1)),
        ("reopen_issue", ("me/repo-a", 1)),
        ("comment_issue", ("me/repo-a", 1, "hi")),
        ("add_label", ("me/repo-a", 1, ["bug"])),
        ("create_pr", ("me/repo-a", "title")),
        ("merge_pr", ("me/repo-a", 7)),
        ("review_pr", ("me/repo-a", 7)),
        ("create_branch", ("me/repo-a", "feat")),
        ("delete_branch", ("me/repo-a", "feat")),
        ("trigger_workflow", ("me/repo-a", 1)),
        ("git_add", ()),
        ("git_commit", ("msg",)),
        ("git_push", ()),
    ]

    def test_all_gated_methods_deny_under_strict_policy(self):
        t = self.make_tool()
        with self.deny():  # deterministic — real policy mode is global state
            for method, args in self.GATED:
                with self.subTest(method=method):
                    out = getattr(t, method)(*args)
                    self.assertFalse(out["success"])
                    self.assertIn("Access denied", out["error"])
                    self.assertIn("github.", out["error"])
                    self.assertFalse(out["policy"]["allowed"])

    def test_gate_returns_policy_dict(self):
        t = self.make_tool()
        with self.deny():
            out = t.create_repo("x")
        self.assertEqual(out["error"],
                         "Access denied (strict_mode): github.create_repo")
        self.assertEqual(out["policy"], {"allowed": False,
                                         "reason": "strict_mode"})


# ---------------------------------------------------------------------------
# _get_client / _user_obj / status (50-87)
# ---------------------------------------------------------------------------


class TestClientAndStatus(GithubBase):
    def test_get_client_uses_token(self):
        t = gh.GitHubTool(token="sekret")
        fake_g = MagicMock(name="Github")
        with patch.object(gh, "Github", fake_g), \
             patch.object(gh, "_check") as chk:
            client = t._get_client()
        chk.assert_called_once()
        fake_g.assert_called_once_with("sekret")
        self.assertIs(client, fake_g.return_value)
        self.assertIs(t._user, fake_g.return_value.get_user.return_value)

    def test_get_client_without_token_calls_no_arg(self):
        t = gh.GitHubTool(token="")
        fake_g = MagicMock(name="Github")
        with patch.object(gh, "Github", fake_g):
            t._get_client()
        fake_g.assert_called_once_with()

    def test_get_client_get_user_failure_sets_none(self):
        t = gh.GitHubTool(token="sekret")
        fake_g = MagicMock(name="Github")
        fake_g.return_value.get_user.side_effect = RuntimeError("401")
        with patch.object(gh, "Github", fake_g):
            client = t._get_client()
        self.assertIs(client, fake_g.return_value)
        self.assertIsNone(t._user)  # swallowed

    def test_get_client_cached_single_instance(self):
        t = self.make_tool()
        with patch.object(gh, "_check") as chk:
            a = t._get_client()
            b = t._get_client()
        self.assertIs(a, b)
        chk.assert_not_called()

    def test_user_obj_falls_back_to_client(self):
        t = self.make_tool(user=None)
        out = t._user_obj()
        t._client.get_user.assert_called_with()
        self.assertIs(out, t._client.get_user.return_value)

    def test_is_configured(self):
        self.assertTrue(gh.GitHubTool(token="x").is_configured())
        self.assertFalse(gh.GitHubTool(token="").is_configured())
        with patch.object(gh, "GITHUB_AVAILABLE", False):
            self.assertFalse(gh.GitHubTool(token="x").is_configured())

    def test_status_unavailable(self):
        with patch.object(gh, "GITHUB_AVAILABLE", False):
            out = gh.GitHubTool(token="x").get_status()
        self.assertEqual(out, {"available": False,
                               "error": "PyGithub not installed"})

    def test_status_no_token(self):
        out = gh.GitHubTool(token="").get_status()
        self.assertTrue(out["available"])
        self.assertFalse(out["authenticated"])

    def test_status_success(self):
        user = SimpleNamespace(login="me", name=None, public_repos=5,
                               followers=6, following=7)
        t = self.make_tool(user=user)
        out = t.get_status()
        self.assertTrue(out["authenticated"])
        self.assertEqual(out["user"], "me")
        self.assertEqual(out["name"], "me")  # name None -> login
        self.assertEqual(out["public_repos"], 5)

    def test_status_exception(self):
        t = self.make_tool(user=None)
        t._client.get_user.side_effect = RuntimeError("rate limited")
        out = t.get_status()
        self.assertFalse(out["authenticated"])
        self.assertIn("rate limited", out["error"])


# ---------------------------------------------------------------------------
# Success-with-edge-cases the old file misses (limits, None fields, skips)
# ---------------------------------------------------------------------------


class TestListEdges(GithubBase):
    def test_list_repos_respects_limit(self):
        repos = [_repo(f"r{i}", f"me/r{i}") for i in range(5)]
        user = MagicMock()
        user.get_repos.return_value = repos
        t = self.make_tool(user=user)
        out = t.list_repos(limit=2)
        self.assertEqual(out["count"], 2)
        user.get_repos.assert_called_once_with(sort="updated")

    def test_list_repos_none_fields(self):
        r = _repo()
        r.description = None
        r.language = None
        user = MagicMock()
        user.get_repos.return_value = [r]
        t = self.make_tool(user=user)
        out = t.list_repos()
        self.assertEqual(out["repos"][0]["description"], "")
        self.assertEqual(out["repos"][0]["language"], "unknown")

    def test_list_repos_error(self):
        user = MagicMock()
        user.get_repos.side_effect = RuntimeError("api down")
        t = self.make_tool(user=user)
        out = t.list_repos()
        self.assertFalse(out["success"])
        self.assertIn("api down", out["error"])

    def test_get_repo_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("404")
        out = t.get_repo("me/nope")
        self.assertFalse(out["success"])

    def test_search_repos_limit_and_none_fields(self):
        repos = [_repo(f"s{i}", f"me/s{i}") for i in range(4)]
        repos[0].description = None
        repos[0].language = None
        t = self.make_tool()
        t._client.search_repositories.return_value = repos
        out = t.search_repos("ai", limit=2)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["repos"][0]["description"], "")
        self.assertEqual(out["repos"][0]["language"], "unknown")

    def test_search_repos_error(self):
        t = self.make_tool()
        t._client.search_repositories.side_effect = RuntimeError("403")
        out = t.search_repos("ai")
        self.assertFalse(out["success"])

    def test_list_issues_skips_pull_requests(self):
        issues = [_issue(1, pr=None), _issue(2, pr=MagicMock()),
                  _issue(3, pr=None)]
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.get_issues.return_value = issues
        out = t.list_issues("me/repo-a")
        self.assertEqual(out["count"], 2)
        self.assertEqual([i["number"] for i in out["issues"]], [1, 3])

    def test_list_issues_limit_and_none_user(self):
        issues = [_issue(n, user=None) for n in range(1, 6)]
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.get_issues.return_value = issues
        out = t.list_issues("me/repo-a", state="closed", limit=2)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["issues"][0]["user"], "unknown")
        repo.get_issues.assert_called_once_with(state="closed",
                                                sort="updated")

    def test_list_issues_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("boom")
        out = t.list_issues("me/repo-a")
        self.assertFalse(out["success"])

    def test_create_issue_defaults_none_lists(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.create_issue.return_value = SimpleNamespace(
            number=9, title="t", html_url="u")
        with self.allow():
            out = t.create_issue("me/repo-a", "t")
        self.assertTrue(out["success"])
        kwargs = repo.create_issue.call_args.kwargs
        self.assertEqual(kwargs["labels"], [])
        self.assertEqual(kwargs["assignees"], [])

    def test_create_issue_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("validation")
        with self.allow():
            out = t.create_issue("me/repo-a", "t")
        self.assertFalse(out["success"])

    def test_close_reopen_comment_label_errors(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("gone")
        with self.allow():
            for method, args in [
                ("close_issue", ("me/repo-a", 1)),
                ("reopen_issue", ("me/repo-a", 1)),
                ("comment_issue", ("me/repo-a", 1, "x")),
                ("add_label", ("me/repo-a", 1, ["a"])),
            ]:
                with self.subTest(method=method):
                    out = getattr(t, method)(*args)
                    self.assertFalse(out["success"])

    def test_close_issue_success(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        issue = _issue()
        repo.get_issue.return_value = issue
        with self.allow():
            out = t.close_issue("me/repo-a", 1)
        self.assertEqual(out["state"], "closed")
        issue.edit.assert_called_once_with(state="closed")

    def test_reopen_issue_success(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        issue = _issue()
        repo.get_issue.return_value = issue
        with self.allow():
            out = t.reopen_issue("me/repo-a", 1)
        self.assertEqual(out["state"], "open")

    def test_comment_issue_success(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        issue = _issue()
        issue.create_comment.return_value = SimpleNamespace(
            id=55, html_url="u")
        repo.get_issue.return_value = issue
        with self.allow():
            out = t.comment_issue("me/repo-a", 1, "hello")
        self.assertEqual(out["comment_id"], 55)

    def test_add_label_success(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        issue = _issue()
        repo.get_issue.return_value = issue
        with self.allow():
            out = t.add_label("me/repo-a", 1, ["bug", "urgent"])
        issue.add_to_labels.assert_called_once_with("bug", "urgent")
        self.assertEqual(out["labels"], ["bug", "urgent"])


# ---------------------------------------------------------------------------
# PRs (327-430)
# ---------------------------------------------------------------------------


class TestPullRequests(GithubBase):
    def test_list_prs_limit_and_none_user(self):
        prs = [_pr(n) for n in range(1, 6)]
        prs[0].user = None
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.get_pulls.return_value = prs
        out = t.list_prs("me/repo-a", limit=2)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["prs"][0]["user"], "unknown")
        repo.get_pulls.assert_called_once_with(state="open",
                                               sort="updated")

    def test_list_prs_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("nope")
        out = t.list_prs("me/repo-a")
        self.assertFalse(out["success"])

    def test_create_pr_success_and_error(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.create_pull.return_value = SimpleNamespace(
            number=3, title="t", html_url="u")
        with self.allow():
            out = t.create_pr("me/repo-a", "t", head="feat")
        self.assertTrue(out["success"])
        repo.create_pull.assert_called_once_with(
            title="t", body="", head="feat", base="main")

        t._client.get_repo.side_effect = RuntimeError("conflict")
        with self.allow():
            out = t.create_pr("me/repo-a", "t")
        self.assertFalse(out["success"])

    def test_merge_pr_not_mergeable(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.get_pull.return_value = _pr(mergeable=False)
        with self.allow():
            out = t.merge_pr("me/repo-a", 7)
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "PR not mergeable")

    def test_merge_pr_success_with_default_message(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        pr = _pr(mergeable=True)
        repo.get_pull.return_value = pr
        with self.allow():
            out = t.merge_pr("me/repo-a", 7)
        self.assertTrue(out["merged"])
        pr.merge.assert_called_once_with(commit_message="Merge PR #7")

    def test_merge_pr_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("405")
        with self.allow():
            out = t.merge_pr("me/repo-a", 7)
        self.assertFalse(out["success"])

    def test_review_pr_invalid_event_coerced_to_comment(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        pr = _pr()
        pr.create_review.return_value = SimpleNamespace(id=8, state="COMMENTED")
        repo.get_pull.return_value = pr
        with self.allow():
            out = t.review_pr("me/repo-a", 7, event="SHIP IT")
        pr.create_review.assert_called_once_with(body="", event="COMMENT")
        self.assertEqual(out["review_id"], 8)

    def test_review_pr_valid_event_passthrough(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        pr = _pr()
        pr.create_review.return_value = SimpleNamespace(id=9,
                                                        state="APPROVED")
        repo.get_pull.return_value = pr
        with self.allow():
            t.review_pr("me/repo-a", 7, event="APPROVE", body="lgm")
        pr.create_review.assert_called_once_with(body="lgm",
                                                 event="APPROVE")

    def test_review_pr_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("review failed")
        with self.allow():
            out = t.review_pr("me/repo-a", 7)
        self.assertFalse(out["success"])

    def test_get_pr_files_none_patch_and_error(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        pr = _pr()
        f = SimpleNamespace(filename="a.py", status="modified",
                            additions=1, deletions=2, changes=3, patch=None)
        pr.get_files.return_value = [f]
        repo.get_pull.return_value = pr
        out = t.get_pr_files("me/repo-a", 7)
        self.assertEqual(out["files"][0]["patch"], "")
        self.assertEqual(out["count"], 1)

        t2 = self.make_tool()
        t2._client.get_repo.side_effect = RuntimeError("404")
        out = t2.get_pr_files("me/repo-a", 7)
        self.assertFalse(out["success"])


# ---------------------------------------------------------------------------
# Branches / commits / user / search (434-580)
# ---------------------------------------------------------------------------


class TestBranchesCommitsUser(GithubBase):
    def test_list_branches_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("no repo")
        out = t.list_branches("me/repo-a")
        self.assertFalse(out["success"])

    def test_create_branch_success(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        source = MagicMock()
        source.commit.sha = "deadbeef"
        repo.get_branch.return_value = source
        with self.allow():
            out = t.create_branch("me/repo-a", "feat", from_branch="dev")
        repo.create_git_ref.assert_called_once_with(
            ref="refs/heads/feat", sha="deadbeef")
        self.assertEqual(out["from"], "dev")

    def test_create_branch_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("exists")
        with self.allow():
            out = t.create_branch("me/repo-a", "feat")
        self.assertFalse(out["success"])

    def test_delete_branch_success_and_error(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        ref = MagicMock()
        repo.get_git_ref.return_value = ref
        with self.allow():
            out = t.delete_branch("me/repo-a", "feat")
        self.assertTrue(out["success"])
        ref.delete.assert_called_once()
        repo.get_git_ref.assert_called_once_with("heads/feat")

        t2 = self.make_tool()
        t2._client.get_repo.side_effect = RuntimeError("404")
        with self.allow():
            out = t2.delete_branch("me/repo-a", "feat")
        self.assertFalse(out["success"])

    def test_list_commits_limit_and_none_author(self):
        commits = [_commit(author=(n % 2 == 0)) for n in range(5)]
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.get_commits.return_value = commits
        out = t.list_commits("me/repo-a", sha="dev", limit=3)
        self.assertEqual(out["count"], 3)
        self.assertEqual(out["commits"][1]["author"], "unknown")
        self.assertEqual(out["commits"][1]["date"], "")
        repo.get_commits.assert_called_once_with(sha="dev")

    def test_list_commits_error(self):
        t = self.make_tool()
        t._client.get_repo.side_effect = RuntimeError("no git")
        out = t.list_commits("me/repo-a")
        self.assertFalse(out["success"])

    def test_get_user_info_named_and_self(self):
        other = SimpleNamespace(login="bob", name="Bob", bio=None,
                                public_repos=1, followers=2, following=3,
                                avatar_url="a", html_url="h", company=None,
                                location=None)
        t = self.make_tool()
        t._client.get_user.return_value = other
        out = t.get_user_info("bob")
        t._client.get_user.assert_called_with("bob")
        self.assertEqual(out["user"]["name"], "Bob")
        self.assertEqual(out["user"]["bio"], "")

        t2 = self.make_tool(user=other)
        out = t2.get_user_info()
        self.assertEqual(out["user"]["login"], "bob")

    def test_get_user_info_error(self):
        t = self.make_tool()
        t._client.get_user.side_effect = RuntimeError("404")
        out = t.get_user_info("ghost")
        self.assertFalse(out["success"])

    def test_list_starred_limit_and_none_fields(self):
        stars = [_repo(f"st{i}", f"me/st{i}") for i in range(4)]
        stars[0].description = None
        user = MagicMock()
        user.get_starred.return_value = stars
        t = self.make_tool(user=user)
        out = t.list_starred(limit=2)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["starred"][0]["description"], "")

    def test_list_starred_error(self):
        user = MagicMock()
        user.get_starred.side_effect = RuntimeError("api")
        t = self.make_tool(user=user)
        out = t.list_starred()
        self.assertFalse(out["success"])

    def test_search_code_limit_and_error(self):
        t = self.make_tool()
        items = [SimpleNamespace(name=f"f{i}", path=f"p/f{i}",
                                 repository=SimpleNamespace(
                                     full_name="me/repo-a"),
                                 html_url="u") for i in range(4)]
        t._client.search_code.return_value = items
        out = t.search_code("q", limit=2)
        self.assertEqual(out["count"], 2)

        t._client.search_code.side_effect = RuntimeError("403")
        out = t.search_code("q")
        self.assertFalse(out["success"])

    def test_search_issues_limit_none_repo_and_error(self):
        t = self.make_tool()
        issues = [SimpleNamespace(number=i, title="t", state="open",
                                  repository=(SimpleNamespace(
                                      full_name="me/repo-a")
                                      if i % 2 else None),
                                  html_url="u") for i in range(4)]
        t._client.search_issues.return_value = issues
        out = t.search_issues("q", limit=3)
        self.assertEqual(out["count"], 3)
        self.assertEqual(out["results"][0]["repository"], "")  # i=0 -> None

        t._client.search_issues.side_effect = RuntimeError("422")
        out = t.search_issues("q")
        self.assertFalse(out["success"])


# ---------------------------------------------------------------------------
# Actions (584-645)
# ---------------------------------------------------------------------------


class TestWorkflows(GithubBase):
    def _wf(self):
        return SimpleNamespace(id=11, name="CI", state="active",
                               path=".github/workflows/ci.yml",
                               html_url="u", create_dispatch=MagicMock(),
                               get_runs=MagicMock())

    def test_list_workflows_success_and_error(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.get_workflows.return_value = [self._wf()]
        out = t.list_workflows("me/repo-a")
        self.assertEqual(out["count"], 1)

        t2 = self.make_tool()
        t2._client.get_repo.side_effect = RuntimeError("404")
        out = t2.list_workflows("me/repo-a")
        self.assertFalse(out["success"])

    def test_trigger_workflow_success_and_error(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        wf = self._wf()
        repo.get_workflow.return_value = wf
        with self.allow():
            out = t.trigger_workflow("me/repo-a", 11, ref="dev")
        self.assertTrue(out["success"])
        wf.create_dispatch.assert_called_once_with("dev")

        t2 = self.make_tool()
        t2._client.get_repo.side_effect = RuntimeError("bad ref")
        with self.allow():
            out = t2.trigger_workflow("me/repo-a", 11)
        self.assertFalse(out["success"])

    @staticmethod
    def _run():
        return SimpleNamespace(id=1, name="CI", status="completed",
                              conclusion="success", head_branch="main",
                              event="push", created_at="2026-01-01",
                              updated_at="2026-01-02", html_url="u")

    def test_workflow_runs_with_workflow_id(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        wf = self._wf()
        wf.get_runs.return_value = [self._run()]
        repo.get_workflow.return_value = wf
        out = t.list_workflow_runs("me/repo-a", workflow_id=11, limit=5)
        self.assertEqual(out["count"], 1)
        repo.get_workflow.assert_called_once_with(11)
        repo.get_workflow_runs.assert_not_called()

    def test_workflow_runs_without_id_and_limit(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        repo.get_workflow_runs.return_value = [self._run()
                                               for _ in range(4)]
        out = t.list_workflow_runs("me/repo-a", limit=2)
        self.assertEqual(out["count"], 2)
        repo.get_workflow_runs.assert_called_once()

    def test_workflow_runs_none_conclusion_and_error(self):
        t = self.make_tool()
        repo = t._client.get_repo.return_value
        run = self._run()
        run.conclusion = None
        repo.get_workflow_runs.return_value = [run]
        out = t.list_workflow_runs("me/repo-a")
        self.assertEqual(out["runs"][0]["conclusion"], "")

        t2 = self.make_tool()
        t2._client.get_repo.side_effect = RuntimeError("500")
        out = t2.list_workflow_runs("me/repo-a")
        self.assertFalse(out["success"])


# ---------------------------------------------------------------------------
# git subprocess operations (649-727)
# ---------------------------------------------------------------------------


class TestGitOps(GithubBase):
    @staticmethod
    def _proc(returncode=0, stdout="", stderr=""):
        return SimpleNamespace(returncode=returncode, stdout=stdout,
                               stderr=stderr)

    def _run_case(self, method, proc, args=()):
        # git_add/git_commit/git_push are policy-gated; allow unconditionally
        # so the subprocess assertion is what's being tested here.
        with patch.object(gh.subprocess, "run", return_value=proc) as run, \
             patch.object(gh, "check_tool",
                          return_value=SimpleNamespace(allowed=True)):
            out = getattr(self.make_tool(), method)(*args)
        return out, run

    def test_git_status_success_and_fail(self):
        out, _ = self._run_case("git_status", self._proc(stdout=" M file\n"))
        self.assertTrue(out["success"])
        self.assertEqual(out["status"], "M file")

        out, _ = self._run_case(
            "git_status",
            self._proc(returncode=128, stderr="fatal: not a git repo"))
        self.assertFalse(out["success"])
        self.assertIn("not a git repo", out["error"])

    def test_git_status_empty_error_fallback(self):
        out, _ = self._run_case("git_status", self._proc(returncode=1))
        self.assertFalse(out["success"])
        self.assertEqual(out["error"], "git status failed")

    def test_git_status_exception(self):
        with patch.object(gh.subprocess, "run",
                          side_effect=FileNotFoundError("git")):
            out = self.make_tool().git_status()
        self.assertFalse(out["success"])
        self.assertIn("git", out["error"])

    def test_git_log_success_fail_empty_exception(self):
        out, _ = self._run_case(
            "git_log", self._proc(stdout="abc one\ndef two\n"))
        self.assertEqual(out["count"], 2)

        out, _ = self._run_case("git_log",
                                self._proc(returncode=1, stderr="bad"))
        self.assertFalse(out["success"])

        out, _ = self._run_case("git_log", self._proc(stdout="  \n"))
        self.assertEqual(out["commits"], [])
        self.assertEqual(out["count"], 0)

        with patch.object(gh.subprocess, "run",
                          side_effect=RuntimeError("timeout")):
            out = self.make_tool().git_log()
        self.assertFalse(out["success"])

    def test_git_add_with_files_and_default_dot(self):
        out, run = self._run_case("git_add", self._proc(),
                                  args=(["a.txt", "b.txt"],))
        self.assertTrue(out["success"])
        self.assertEqual(run.call_args.args[0],
                         ["git", "add", "a.txt", "b.txt"])

        out, run = self._run_case("git_add", self._proc())
        self.assertEqual(run.call_args.args[0], ["git", "add", "."])

    def test_git_add_failure_and_exception(self):
        out, _ = self._run_case("git_add",
                                self._proc(returncode=1, stderr="nope"))
        self.assertFalse(out["success"])

        with patch.object(gh.subprocess, "run",
                          side_effect=RuntimeError("denied")), \
             patch.object(gh, "check_tool",
                          return_value=SimpleNamespace(allowed=True)):
            out = self.make_tool().git_add()
        self.assertFalse(out["success"])

    def test_git_commit_success_failure_exception(self):
        out, run = self._run_case("git_commit", self._proc(),
                                  args=("msg here",))
        self.assertTrue(out["success"])
        self.assertEqual(run.call_args.args[0],
                         ["git", "commit", "-m", "msg here"])

        out, _ = self._run_case("git_commit",
                                self._proc(returncode=1, stderr="nothing"),
                                args=("msg here",))
        self.assertFalse(out["success"])

        with patch.object(gh.subprocess, "run",
                          side_effect=RuntimeError("lock")), \
             patch.object(gh, "check_tool",
                          return_value=SimpleNamespace(allowed=True)):
            out = self.make_tool().git_commit("m")
        self.assertFalse(out["success"])

    def test_git_push_success_failure_exception(self):
        out, run = self._run_case("git_push", self._proc(stdout="ok"),
                                  args=("dev",))
        self.assertTrue(out["success"])
        self.assertEqual(run.call_args.args[0],
                         ["git", "push", "origin", "dev"])

        out, _ = self._run_case("git_push",
                                self._proc(returncode=1, stderr="rejected"))
        self.assertFalse(out["success"])
        self.assertIn("rejected", out["error"])

        with patch.object(gh.subprocess, "run",
                          side_effect=RuntimeError("net")), \
             patch.object(gh, "check_tool",
                          return_value=SimpleNamespace(allowed=True)):
            out = self.make_tool().git_push()
        self.assertFalse(out["success"])

    def test_git_pull_success_failure_exception(self):
        out, _ = self._run_case("git_pull", self._proc(stdout="ok"))
        self.assertTrue(out["success"])

        out, _ = self._run_case("git_pull",
                                self._proc(returncode=1, stderr="diverged"))
        self.assertFalse(out["success"])

        with patch.object(gh.subprocess, "run",
                          side_effect=RuntimeError("offline")):
            out = self.make_tool().git_pull()
        self.assertFalse(out["success"])

    def test_git_branches_success_fail_parse_exception(self):
        out, _ = self._run_case(
            "git_branches",
            self._proc(stdout="* main\n  dev\n  feature/x\n"))
        self.assertEqual(out["branches"], ["main", "dev", "feature/x"])

        out, _ = self._run_case("git_branches",
                                self._proc(returncode=1, stderr="bad"))
        self.assertFalse(out["success"])

        out, _ = self._run_case("git_branches", self._proc(stdout=""))
        self.assertEqual(out["branches"], [])

        with patch.object(gh.subprocess, "run",
                          side_effect=RuntimeError("gone")):
            out = self.make_tool().git_branches()
        self.assertFalse(out["success"])

    def test_git_diff_success_fail_exception(self):
        out, _ = self._run_case("git_diff", self._proc(stdout="+a\n-b\n"))
        self.assertTrue(out["success"])
        self.assertIn("+a", out["diff"])

        out, _ = self._run_case("git_diff",
                                self._proc(returncode=1, stderr="oops"))
        self.assertFalse(out["success"])

        with patch.object(gh.subprocess, "run",
                          side_effect=RuntimeError("e")):
            out = self.make_tool().git_diff()
        self.assertFalse(out["success"])


# ---------------------------------------------------------------------------
# handle_natural fallbacks (731-778)
# ---------------------------------------------------------------------------


class TestHandleNatural(GithubBase):
    def test_list_issues_falls_back_when_repos_fail(self):
        t = self.make_tool()
        with patch.object(t, "list_repos",
                          return_value={"success": False}), \
             patch.object(t, "list_issues",
                          return_value={"success": True}) as li:
            out = t.handle_natural("show my issues")
        li.assert_called_once_with("priyanshu0602/ORBIT")
        self.assertTrue(out["success"])

    def test_list_issues_uses_first_repo(self):
        t = self.make_tool()
        with patch.object(t, "list_repos",
                          return_value={"success": True,
                                        "repos": [{"full_name": "a/b"}]}), \
             patch.object(t, "list_issues",
                          return_value={"success": True}) as li:
            t.handle_natural("list my issues")
        li.assert_called_once_with("a/b")

    def test_git_pull_phrase(self):
        t = self.make_tool()
        with patch.object(t, "git_pull",
                          return_value={"success": True}) as gp:
            out = t.handle_natural("please git pull now")
        gp.assert_called_once()
        self.assertTrue(out["success"])

    def test_pull_latest_phrase(self):
        t = self.make_tool()
        with patch.object(t, "git_pull",
                          return_value={"success": True}) as gp:
            t.handle_natural("pull latest changes")
        gp.assert_called_once()

    def test_push_changes_phrase(self):
        t = self.make_tool()
        with patch.object(t, "git_push",
                          return_value={"success": True}) as gpush:
            out = t.handle_natural("push changes now")
        gpush.assert_called_once()
        self.assertTrue(out["success"])

    def test_git_push_phrase(self):
        t = self.make_tool()
        with patch.object(t, "git_push",
                          return_value={"success": True}) as gpush:
            t.handle_natural("git push")
        gpush.assert_called_once()


if __name__ == "__main__":
    unittest.main()
