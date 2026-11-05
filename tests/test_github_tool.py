"""Tests for GitHubTool — repos, issues, PRs, branches, commits, natural language."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

from orbit.orbit.tools.github_tool import GITHUB_AVAILABLE, GitHubTool


def _mock_policy_decision():
    """Return a mock PolicyDecision that allows everything."""
    d = MagicMock()
    d.allowed = True
    return d


def _mock_github():
    mock_client = MagicMock()
    mock_user = MagicMock()
    mock_user.login = "testuser"
    mock_user.name = "Test User"
    mock_user.public_repos = 5
    mock_user.followers = 10
    mock_user.following = 3
    mock_client.get_user.return_value = mock_user
    return mock_client, mock_user


def _mock_repo(full_name="testuser/testrepo", private=False):
    mock_repo = MagicMock()
    mock_repo.full_name = full_name
    mock_repo.name = full_name.split("/")[-1]
    mock_repo.description = "Test repo"
    mock_repo.private = private
    mock_repo.forks_count = 2
    mock_repo.stargazers_count = 5
    mock_repo.open_issues_count = 1
    mock_repo.default_branch = "main"
    mock_repo.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    mock_repo.updated_at.isoformat.return_value = "2026-07-26T00:00:00"
    return mock_repo


def _mock_issue(number=1, title="Test issue", state="open"):
    mock_issue = MagicMock()
    mock_issue.number = number
    mock_issue.title = title
    mock_issue.state = state
    mock_issue.body = "Test body"
    mock_issue.user.login = "testuser"
    mock_issue.labels = []
    mock_issue.created_at.isoformat.return_value = "2026-07-26T00:00:00"
    return mock_issue


def _mock_pr(number=1, title="Test PR", state="open"):
    mock_pr = MagicMock()
    mock_pr.number = number
    mock_pr.title = title
    mock_pr.state = state
    mock_pr.body = "Test body"
    mock_pr.user.login = "testuser"
    mock_pr.head.ref = "feature-branch"
    mock_pr.base.ref = "main"
    mock_pr.mergeable = True
    mock_pr.merged = False
    mock_pr.additions = 10
    mock_pr.deletions = 5
    mock_pr.changed_files = 2
    mock_pr.created_at.isoformat.return_value = "2026-07-26T00:00:00"
    return mock_pr


def _mock_commit(sha="abc123", message="Test commit"):
    mock_commit = MagicMock()
    mock_commit.sha = sha
    mock_commit.commit.message = message
    mock_commit.commit.author.name = "Test User"
    mock_commit.commit.author.date.isoformat.return_value = "2026-07-26T00:00:00"
    return mock_commit


def _mock_branch(name="main"):
    mock_branch = MagicMock()
    mock_branch.name = name
    mock_branch.commit.sha = "abc123"
    return mock_branch


def _mock_workflow(name="CI", state="active"):
    mock_wf = MagicMock()
    mock_wf.id = 12345
    mock_wf.name = name
    mock_wf.state = state
    mock_wf.path = ".github/workflows/ci.yml"
    mock_wf.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    mock_wf.updated_at.isoformat.return_value = "2026-07-26T00:00:00"
    return mock_wf


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolStatus:
    def test_not_configured_no_token(self):
        tool = GitHubTool(token="")
        assert tool.is_configured() is False

    def test_not_configured_no_github(self):
        with patch("orbit.orbit.tools.github_tool.GITHUB_AVAILABLE", False):
            tool = GitHubTool(token="fake")
            status = tool.get_status()
            assert status["available"] is False

    def test_status_no_token(self):
        tool = GitHubTool(token="")
        status = tool.get_status()
        assert status["available"] is True
        assert status["authenticated"] is False

    @patch("orbit.orbit.tools.github_tool.Github")
    def test_status_authenticated(self, MockGithub):
        mock_client, _mock_user = _mock_github()
        MockGithub.return_value = mock_client
        tool = GitHubTool(token="fake-token")
        status = tool.get_status()
        assert status["authenticated"] is True
        assert status["user"] == "testuser"
        assert status["name"] == "Test User"
        assert status["public_repos"] == 5

    @patch("orbit.orbit.tools.github_tool.Github")
    def test_status_auth_error(self, MockGithub):
        MockGithub.side_effect = Exception("Bad credentials")
        tool = GitHubTool(token="bad-token")
        status = tool.get_status()
        assert status["authenticated"] is False
        assert "Bad credentials" in status["error"]


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolRepos:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    def test_list_repos(self, _mock_gate):
        mock_client, mock_user = _mock_github()
        mock_repo1 = _mock_repo("testuser/repo1")
        mock_repo2 = _mock_repo("testuser/repo2")
        mock_user.get_repos.return_value = [mock_repo1, mock_repo2]
        tool = self._tool_with_client(mock_client)
        result = tool.list_repos(limit=2)
        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["repos"]) == 2

    def test_get_repo(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.get_repo("testuser/testrepo")
        assert result["success"] is True
        assert result["repo"]["full_name"] == "testuser/testrepo"

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    def test_create_repo(self, _mock_gate):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo("testuser/new-repo")
        mock_client.get_user.return_value.create_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.create_repo("new-repo", description="Test", private=False)
        assert result["success"] is True
        assert result["repo"]["full_name"] == "testuser/new-repo"

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    def test_delete_repo(self, _mock_gate):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.delete_repo("testuser/testrepo")
        assert result["success"] is True
        mock_repo.delete.assert_called_once()

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    def test_fork_repo(self, _mock_gate):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_forked = _mock_repo("testuser/testrepo")
        mock_repo.create_fork.return_value = mock_forked
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.fork_repo("testuser/testrepo")
        assert result["success"] is True

    def test_search_repos(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_client.search_repositories.return_value = [mock_repo]
        tool = self._tool_with_client(mock_client)
        result = tool.search_repos("python", limit=1)
        assert result["success"] is True
        assert result["count"] == 1


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolIssues:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    def test_list_issues(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_issue1 = _mock_issue(1, "Bug 1")
        mock_issue2 = _mock_issue(2, "Bug 2")
        mock_issue1.pull_request = None
        mock_issue2.pull_request = None
        mock_repo.get_issues.return_value = [mock_issue1, mock_issue2]
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.list_issues("testuser/testrepo", state="open")
        assert result["success"] is True
        assert result["count"] == 2

    def test_create_issue(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_issue = _mock_issue(1, "New Bug")
        mock_repo.create_issue.return_value = mock_issue
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.create_issue("testuser/testrepo", title="New Bug")
        assert result["success"] is True
        assert result["issue"]["number"] == 1

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    def test_close_issue(self, _mock_gate):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_issue = _mock_issue(1, state="open")
        mock_repo.get_issue.return_value = mock_issue
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.close_issue("testuser/testrepo", 1)
        assert result["success"] is True
        mock_issue.edit.assert_called_once_with(state="closed")

    def test_reopen_issue(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_issue = _mock_issue(1, state="closed")
        mock_repo.get_issue.return_value = mock_issue
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.reopen_issue("testuser/testrepo", 1)
        assert result["success"] is True
        mock_issue.edit.assert_called_once_with(state="open")

    def test_comment_issue(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_issue = _mock_issue(1)
        mock_repo.get_issue.return_value = mock_issue
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.comment_issue("testuser/testrepo", 1, "This is a comment")
        assert result["success"] is True

    def test_add_label(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_issue = _mock_issue(1)
        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_repo.get_issue.return_value = mock_issue
        mock_repo.get_labels.return_value = [mock_label]
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.add_label("testuser/testrepo", 1, ["bug"])
        assert result["success"] is True


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolPRs:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    def test_list_prs(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_pr = _mock_pr()
        mock_repo.get_pulls.return_value = [mock_pr]
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.list_prs("testuser/testrepo", state="open")
        assert result["success"] is True
        assert result["count"] == 1

    def test_create_pr(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_pr = _mock_pr()
        mock_repo.create_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.create_pr(
            "testuser/testrepo", title="New PR", head="feature", base="main"
        )
        assert result["success"] is True
        assert result["pr"]["number"] == 1

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    def test_merge_pr(self, _mock_gate):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_pr = _mock_pr(state="open")
        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.merge_pr("testuser/testrepo", 1, "Merged!")
        assert result["success"] is True

    def test_review_pr(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_pr = _mock_pr()
        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.review_pr("testuser/testrepo", 1, "APPROVE", "LGTM")
        assert result["success"] is True

    def test_get_pr_files(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_pr = _mock_pr()
        mock_file = MagicMock()
        mock_file.filename = "test.py"
        mock_file.status = "modified"
        mock_file.additions = 5
        mock_file.deletions = 2
        mock_file.patch = "+test code"
        mock_pr.get_files.return_value = [mock_file]
        mock_repo.get_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.get_pr_files("testuser/testrepo", 1)
        assert result["success"] is True
        assert result["count"] == 1


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolBranches:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    def test_list_branches(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_b1 = _mock_branch("main")
        mock_b2 = _mock_branch("feature")
        mock_repo.get_branches.return_value = [mock_b1, mock_b2]
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.list_branches("testuser/testrepo")
        assert result["success"] is True
        assert result["count"] == 2

    def test_create_branch(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_source = _mock_branch("main")
        mock_repo.get_branch.return_value = mock_source
        mock_repo.create_git_ref.return_value = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.create_branch("testuser/testrepo", "new-branch", "main")
        assert result["success"] is True

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    def test_delete_branch(self, _mock_gate):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_ref = MagicMock()
        mock_repo.get_git_ref.return_value = mock_ref
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.delete_branch("testuser/testrepo", "old-branch")
        assert result["success"] is True
        mock_ref.delete.assert_called_once()


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolCommits:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    def test_list_commits(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_c1 = _mock_commit("abc123", "First commit")
        mock_c2 = _mock_commit("def456", "Second commit")
        mock_repo.get_commits.return_value = [mock_c1, mock_c2]
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.list_commits("testuser/testrepo", limit=2)
        assert result["success"] is True
        assert result["count"] == 2


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolWorkflows:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    def test_list_workflows(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_wf = _mock_workflow("CI", "active")
        mock_repo.get_workflows.return_value = [mock_wf]
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.list_workflows("testuser/testrepo")
        assert result["success"] is True
        assert result["count"] == 1

    def test_trigger_workflow(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_wf = _mock_workflow()
        mock_repo.get_workflow.return_value = mock_wf
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.trigger_workflow("testuser/testrepo", 12345, "main")
        assert result["success"] is True

    def test_list_workflow_runs(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_wf = _mock_workflow()
        mock_run = MagicMock()
        mock_run.id = 999
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.head_branch = "main"
        mock_run.created_at.isoformat.return_value = "2026-07-26T00:00:00"
        mock_run.updated_at.isoformat.return_value = "2026-07-26T01:00:00"
        mock_run.html_url = "https://github.com/testuser/testrepo/actions/runs/999"
        mock_wf.get_runs.return_value = [mock_run]
        mock_repo.get_workflow.return_value = mock_wf
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.list_workflow_runs("testuser/testrepo", 12345, limit=1)
        assert result["success"] is True


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolSearch:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    def test_search_code(self):
        mock_client, _ = _mock_github()
        mock_result = MagicMock()
        mock_result.path = "main.py"
        mock_result.repository.full_name = "testuser/testrepo"
        mock_result.name = "main.py"
        mock_client.search_code.return_value = [mock_result]
        tool = self._tool_with_client(mock_client)
        result = tool.search_code("def main", limit=1)
        assert result["success"] is True
        assert result["count"] == 1

    def test_search_issues(self):
        mock_client, _ = _mock_github()
        mock_issue = _mock_issue(1, "Bug in main")
        mock_client.search_issues.return_value = [mock_issue]
        tool = self._tool_with_client(mock_client)
        result = tool.search_issues("bug in:body", limit=1)
        assert result["success"] is True
        assert result["count"] == 1


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolNaturalLanguage:
    def _tool_with_client(self, mock_client):
        tool = GitHubTool(token="fake-token")
        tool._client = mock_client
        tool._user = mock_client.get_user.return_value
        return tool

    def test_natural_status(self):
        mock_client, _ = _mock_github()
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("what's my github status")
        assert "authenticated" in result or result.get("success") is True

    def test_natural_list_repos(self):
        mock_client, mock_user = _mock_github()
        mock_repo = _mock_repo()
        mock_user.get_repos.return_value = [mock_repo]
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("list my repos")
        assert result["success"] is True
        assert result["count"] == 1

    def test_natural_list_issues(self):
        mock_client, mock_user = _mock_github()
        mock_repo = _mock_repo()
        mock_user.get_repos.return_value = [mock_repo]
        mock_issue = _mock_issue(1, "Bug")
        mock_issue.pull_request = None
        mock_repo.get_issues.return_value = [mock_issue]
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("list my issues")
        assert result["success"] is True

    def test_natural_create_issue(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_issue = _mock_issue(1, "New bug")
        mock_repo.create_issue.return_value = mock_issue
        mock_client.get_repo.return_value = mock_repo
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("create issue for testuser/testrepo: New bug")
        assert result["success"] is True

    def test_natural_git_status(self):
        mock_client, _ = _mock_github()
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("git status")
        assert result["success"] is True

    def test_natural_git_log(self):
        mock_client, _ = _mock_github()
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("git log")
        assert result["success"] is True

    def test_natural_search_repos(self):
        mock_client, _ = _mock_github()
        mock_repo = _mock_repo()
        mock_client.search_repositories.return_value = [mock_repo]
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("search repos python")
        assert result["success"] is True

    def test_natural_unknown(self):
        mock_client, _ = _mock_github()
        tool = self._tool_with_client(mock_client)
        result = tool.handle_natural("do something random")
        assert result["success"] is False


@pytest.mark.skipif(not GITHUB_AVAILABLE, reason="PyGithub not installed")
class TestGitHubToolLocalGit:
    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_status(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="M main.py\n", stderr=""
        )
        tool = GitHubTool(token="fake-token")
        result = tool.git_status()
        assert result["success"] is True
        assert "main.py" in result["status"]

    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_log(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="abc123 Test commit\ndef456 Another commit", stderr=""
        )
        tool = GitHubTool(token="fake-token")
        result = tool.git_log(limit=2)
        assert result["success"] is True
        assert result["count"] == 2

    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_diff(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="diff --git a/main.py\n+new line", stderr=""
        )
        tool = GitHubTool(token="fake-token")
        result = tool.git_diff()
        assert result["success"] is True

    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_pull(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="Already up to date.", stderr=""
        )
        tool = GitHubTool(token="fake-token")
        result = tool.git_pull()
        assert result["success"] is True

    @patch(
        "orbit.orbit.tools.github_tool.check_tool", return_value=_mock_policy_decision()
    )
    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_push(self, mock_subprocess, _mock_gate):
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="Everything up-to-date", stderr=""
        )
        tool = GitHubTool(token="fake-token")
        result = tool.git_push("main")
        assert result["success"] is True

    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_add(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        tool = GitHubTool(token="fake-token")
        result = tool.git_add(["main.py", "test.py"])
        assert result["success"] is True

    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_commit(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="main abc123 commit message", stderr=""
        )
        tool = GitHubTool(token="fake-token")
        result = tool.git_commit("test message")
        assert result["success"] is True

    @patch("orbit.orbit.tools.github_tool.subprocess")
    def test_git_branches(self, mock_subprocess):
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="* main\n  feature\n  dev", stderr=""
        )
        tool = GitHubTool(token="fake-token")
        result = tool.git_branches()
        assert result["success"] is True
        assert result["count"] == 3


class TestGitHubToolWithoutToken:
    def test_factory_no_token(self):
        with patch("orbit.orbit.tools.github_tool.GITHUB_AVAILABLE", True):
            tool = GitHubTool(token="")
            assert tool.is_configured() is False

    def test_status_unavailable(self):
        with patch("orbit.orbit.tools.github_tool.GITHUB_AVAILABLE", False):
            tool = GitHubTool(token="")
            status = tool.get_status()
            assert status["available"] is False
