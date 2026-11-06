"""The change and record-keeping tools, against a fake GitHub/Jira/Mattermost."""

import json
from pathlib import Path

import httpx
import pytest

from sentinel.config import Settings
from sentinel.tools import ToolError, Tools

PR_URL = "https://github.com/Abdeali1310/sentinel-sre/pull/7"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        api_url="http://api.test",
        prometheus_url="http://prom.test",
        alertmanager_url="http://am.test",
        repo_dir=str(tmp_path),
        workspace_dir=str(tmp_path / "workspace"),
        tests_python="python-test",
        secrets=[],
        mattermost_webhook_url="http://mattermost.test/hooks/abc",
        mattermost_channel="#incidents",
        mattermost_allowed_users="alice",
        jira_url="https://jira.test",
        jira_email="agent@example.test",
        jira_api_token="jira-token",
        jira_project_key="KAN",
        jira_issue_type="Task",
        jira_labels="incident,sre-agent",
        github_owner="Abdeali1310",
        github_repo="sentinel-sre",
        github_token="gh-token",
        _env_file=None,
    )
    values.update(overrides)
    return Settings(**values)


def make_tools(tmp_path: Path, handler) -> Tools:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Tools(make_settings(tmp_path), http=client)


class FakeGitHub:
    """Enough GitHub to exercise the Git Data API call sequence."""

    def __init__(self, parent_has_file: bool = True) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.parent_has_file = parent_has_file

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.method, request.url.path, body))
        path = request.url.path

        if path.endswith("/pulls/7"):
            return httpx.Response(
                200,
                json={
                    "merged": True,
                    "merge_commit_sha": "merge-sha",
                    "title": "Fix the crash",
                    "base": {"ref": "main"},
                },
            )
        if path.endswith("/pulls/7/files"):
            files = [{"filename": "payments-api/app/main.py"}]
            if not self.parent_has_file:
                files.append({"filename": "payments-api/tests/test_new.py"})
            return httpx.Response(200, json=files)
        if path.endswith("/git/trees/parent-sha"):
            tree = [
                {"path": "payments-api/app/main.py", "type": "blob", "mode": "100644", "sha": "old"}
            ]
            if self.parent_has_file:
                tree.append(
                    {
                        "path": "payments-api/tests/test_new.py",
                        "type": "blob",
                        "mode": "100644",
                        "sha": "old-test",
                    }
                )
            return httpx.Response(200, json={"tree": tree})
        if path.endswith("/git/commits/merge-sha"):
            return httpx.Response(200, json={"parents": [{"sha": "parent-sha"}]})
        if path.endswith("/git/commits/main-sha"):
            return httpx.Response(200, json={"tree": {"sha": "main-tree"}})
        if path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "main-sha"}})
        if path.endswith("/git/commits/base-sha"):
            return httpx.Response(200, json={"tree": {"sha": "base-tree"}})
        if path.endswith("/git/blobs"):
            return httpx.Response(201, json={"sha": "blob-1"})
        if path.endswith("/git/trees"):
            return httpx.Response(201, json={"sha": "new-tree"})
        if path.endswith("/git/commits") and request.method == "POST":
            return httpx.Response(201, json={"sha": "commit-1"})
        if path.endswith("/git/refs"):
            return httpx.Response(201, json={})
        if "/git/refs/heads/" in path:
            return httpx.Response(200, json={})
        if path.endswith("/pulls") and request.method == "POST":
            return httpx.Response(201, json={"number": 7, "html_url": PR_URL})
        if path.endswith("/status"):
            return httpx.Response(200, json={"state": "success", "target_url": PR_URL})
        if path.endswith("/check-runs"):
            return httpx.Response(200, json={"check_runs": []})
        return httpx.Response(404, json={"message": f"unexpected {request.method} {path}"})


def test_publish_fix_refuses_a_workflow_file_before_touching_github(tmp_path):
    github = FakeGitHub()
    tools = make_tools(tmp_path, github)

    with pytest.raises(ToolError, match="refused"):
        tools.publish_fix(
            "fix/KAN-6-order-id",
            "Fix crash",
            "body",
            {".github/workflows/ci.yml": "name: ci"},
        )

    assert github.calls == []


def test_publish_fix_refuses_a_branch_that_is_not_fix(tmp_path):
    with pytest.raises(ToolError, match="fix/"):
        make_tools(tmp_path, FakeGitHub()).publish_fix(
            "main", "Fix", "body", {"payments-api/app/main.py": "x"}
        )


def test_publish_fix_commits_through_the_git_data_api_and_opens_a_pr(tmp_path):
    github = FakeGitHub()

    result = make_tools(tmp_path, github).publish_fix(
        "fix/KAN-6-order-id",
        "Read order_id from the provider response",
        "Fixes the 500 on POST /payments.",
        {"payments-api/app/main.py": "fixed = True\n"},
        ticket_key="KAN-6",
    )

    assert result["pr_url"] == PR_URL
    assert result["files"] == ["payments-api/app/main.py"]

    methods = [(method, path.rsplit("/repos/", 1)[-1]) for method, path, _ in github.calls]
    assert any(method == "POST" and path.endswith("/git/blobs") for method, path in methods)
    assert any(
        method == "PATCH" and path.endswith("/git/refs/heads/fix/KAN-6-order-id")
        for method, path in methods
    )
    assert all(
        "force" not in body or body.get("force") is False
        for _, path, body in github.calls
        if "/git/refs" in path
    )

    pr_body = next(
        body["body"]
        for method, path, body in github.calls
        if path.endswith("/pulls") and method == "POST"
    )
    assert pr_body.startswith("_Automated remediation by Sentinel (@sre-agent)")
    assert "Jira: KAN-6" in pr_body


def test_publish_fix_accepts_a_test_file(tmp_path):
    result = make_tools(tmp_path, FakeGitHub()).publish_fix(
        "fix/KAN-6-order-id",
        "Fix",
        "body",
        {"payments-api/tests/test_upstream_contract.py": "def test(): pass\n"},
    )

    assert result["pr_url"] == PR_URL


def test_rollback_restores_files_from_before_the_merge(tmp_path):
    github = FakeGitHub()

    result = make_tools(tmp_path, github).rollback(7, reason="Smoke payments still fail.")

    assert result["branch"] == "revert/pr-7"
    tree_call = next(
        body
        for method, path, body in github.calls
        if path.endswith("/git/trees") and method == "POST"
    )
    assert tree_call["tree"] == [
        {"path": "payments-api/app/main.py", "mode": "100644", "type": "blob", "sha": "old"}
    ]
    pr_body = next(
        body["body"]
        for method, path, body in github.calls
        if path.endswith("/pulls") and method == "POST"
    )
    assert "rollback" in pr_body.lower()


def test_rollback_deletes_a_file_the_fix_added(tmp_path):
    github = FakeGitHub(parent_has_file=False)

    make_tools(tmp_path, github).rollback(7)

    tree_call = next(
        body
        for method, path, body in github.calls
        if path.endswith("/git/trees") and method == "POST"
    )
    assert any(entry["sha"] is None for entry in tree_call["tree"])


def test_get_ci_status_turns_a_failed_check_into_failure(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"state": "success"})
        return httpx.Response(
            200,
            json={
                "check_runs": [
                    {"name": "tests", "status": "completed", "conclusion": "failure"},
                ]
            },
        )

    report = make_tools(tmp_path, handler).get_ci_status("fix/KAN-6-order-id")

    assert report["state"] == "failure"
    assert report["checks"][0]["name"] == "tests"


def test_get_ci_status_reports_unknown_when_the_repo_has_no_ci(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"state": "pending", "total_count": 0})
        return httpx.Response(200, json={"check_runs": []})

    report = make_tools(tmp_path, handler).get_ci_status("fix/KAN-7-order-id")

    assert report["state"] == "unknown"
    assert report["checks"] == []


def test_create_jira_ticket_sends_adf_and_labels(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"key": "KAN-9"})

    issue = make_tools(tmp_path, handler).create_jira_ticket(
        "Payments 500 on POST /payments",
        "5xx ratio 45%.\n\nRoot cause: upstream response shape.",
    )

    assert issue["key"] == "KAN-9"
    assert issue["url"] == "https://jira.test/browse/KAN-9"
    fields = seen["body"]["fields"]
    assert fields["issuetype"]["name"] == "Task"
    assert fields["labels"] == ["incident", "sre-agent"]
    assert fields["description"]["content"][0]["content"][0]["text"].startswith("5xx ratio")
    assert seen["url"].endswith("/rest/api/3/issue")


def test_update_jira_ticket_comments_and_transitions_by_name(tmp_path):
    posts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append((request.url.path, json.loads(request.content)))
            return httpx.Response(204)
        assert request.url.path.endswith("/transitions")
        return httpx.Response(
            200,
            json={
                "transitions": [{"id": "41", "name": "Done"}, {"id": "21", "name": "In Progress"}]
            },
        )

    result = make_tools(tmp_path, handler).update_jira_ticket(
        "KAN-9", comment="PR opened: " + PR_URL, transition="Done"
    )

    assert result == {"key": "KAN-9", "comment_added": True, "transition": "Done"}
    assert posts[-1] == ("/rest/api/3/issue/KAN-9/transitions", {"transition": {"id": "41"}})
    assert posts[0][0].endswith("/KAN-9/comment")


def test_update_jira_ticket_lists_the_available_transitions(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transitions": [{"id": "41", "name": "Done"}]})

    with pytest.raises(ToolError, match="Done"):
        make_tools(tmp_path, handler).update_jira_ticket("KAN-9", transition="Shipped")


def test_post_mattermost_sends_the_channel_and_text(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    result = make_tools(tmp_path, handler).post_mattermost("Root cause: KeyError 'order_id'.")

    assert result == {"posted": True, "channel": "#incidents"}
    assert seen["url"] == "http://mattermost.test/hooks/abc"
    assert seen["body"]["text"].startswith("Root cause")


def test_write_tools_refuse_an_operator_outside_the_allowlist(tmp_path):
    with pytest.raises(ToolError, match="allowlist"):
        make_tools(tmp_path, FakeGitHub()).publish_fix(
            "fix/KAN-6-order-id",
            "Fix",
            "body",
            {"payments-api/app/main.py": "x"},
            requested_by="mallory",
        )
