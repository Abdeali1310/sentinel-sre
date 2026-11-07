"""Thin clients for the three systems the agent writes to: Jira, GitHub, Slack.

They hold no policy. `sentinel.tools.Tools` decides what may be called and with
which paths; these clients only turn HTTP into a precise error message.
"""

import json
from urllib.parse import quote

import httpx

from .config import Settings
from .errors import ToolError

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 20
JIRA_TIMEOUT_SECONDS = 60
ALLOWED_PATHS = ("payments-api/app/", "payments-api/tests/")


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return (response.text or "").strip()[:300] or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        for key in ("message", "errorMessages", "errors", "error"):
            if payload.get(key):
                detail = payload[key]
                return detail if isinstance(detail, str) else json.dumps(detail)[:300]
    return f"HTTP {response.status_code}"


def _adf(text: str) -> dict:
    """Plain paragraphs as Atlassian Document Format, which Jira Cloud requires."""
    paragraphs = [block.strip() for block in (text or "").strip().split("\n\n") if block.strip()]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": block}]}
            for block in paragraphs
        ],
    }


def _validate_paths(files: dict[str, str]) -> None:
    if not files:
        raise ToolError("no files supplied")
    for path, content in files.items():
        if not isinstance(content, str):
            raise ToolError(f"{path}: content must be text")
        normalised = path.replace("\\", "/")
        if normalised.startswith("/") or ".." in normalised.split("/"):
            raise ToolError(f"{path}: refused, path must stay inside the repository")
        if not normalised.startswith(ALLOWED_PATHS):
            raise ToolError(
                f"{path}: refused, publish_fix only touches " + " and ".join(ALLOWED_PATHS)
            )


class JiraClient:
    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self.settings = settings
        self.http = http

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.settings.jira_site}/rest/api/3{path}"
        headers = {
            "Authorization": self.settings.jira_auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # Jira Cloud regularly takes >15 s to accept a comment or transition.
        kwargs.setdefault("timeout", JIRA_TIMEOUT_SECONDS)
        try:
            response = self.http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ToolError(f"jira unreachable: {type(exc).__name__}") from exc
        if not response.is_success:
            raise ToolError(f"jira {method} {path}: {_error_detail(response)}")
        return response

    def create_issue(self, summary: str, description: str, labels: list[str]) -> dict:
        payload = {
            "fields": {
                "project": {"key": self.settings.jira_project_key},
                "summary": summary[:255],
                "issuetype": {"name": self.settings.jira_issue_type},
                "labels": labels,
                "description": _adf(description),
            }
        }
        issue = self._call("POST", "/issue", json=payload).json()
        key = issue["key"]
        return {"key": key, "url": f"{self.settings.jira_site}/browse/{key}"}

    def comment(self, issue_key: str, text: str) -> None:
        self._call("POST", f"/issue/{quote(issue_key)}/comment", json={"body": _adf(text)})

    def transition(self, issue_key: str, name: str) -> str:
        transitions = self._call("GET", f"/issue/{quote(issue_key)}/transitions").json()[
            "transitions"
        ]
        match = next((t for t in transitions if t["name"].casefold() == name.casefold()), None)
        if match is None:
            names = ", ".join(t["name"] for t in transitions)
            raise ToolError(f"{issue_key}: no transition named {name!r} (available: {names})")
        self._call(
            "POST",
            f"/issue/{quote(issue_key)}/transitions",
            json={"transition": {"id": match["id"]}},
        )
        return match["name"]


class GitHubClient:
    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self.settings = settings
        self.http = http

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sentinel-sre",
        }
        url = f"{GITHUB_API}/repos/{self.settings.github_owner}/{self.settings.github_repo}{path}"
        response = self.http.request(method, url, headers=headers, **kwargs)
        if not response.is_success:
            raise ToolError(f"github {method} {path}: {_error_detail(response)}")
        return response

    def _head(self, branch: str) -> str:
        return self._call("GET", f"/git/ref/heads/{branch}").json()["object"]["sha"]

    def _commit_tree(self, sha: str) -> str:
        return self._call("GET", f"/git/commits/{sha}").json()["tree"]["sha"]

    def _create_branch(self, branch: str, sha: str) -> None:
        self._call("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})

    def _commit(
        self, branch: str, base_sha: str, base_tree: str, entries: list[dict], message: str
    ):
        tree = self._call(
            "POST", "/git/trees", json={"base_tree": base_tree, "tree": entries}
        ).json()["sha"]
        commit = self._call(
            "POST", "/git/commits", json={"message": message, "tree": tree, "parents": [base_sha]}
        ).json()
        self._call(
            "PATCH", f"/git/refs/heads/{branch}", json={"sha": commit["sha"], "force": False}
        )
        return commit["sha"]

    def publish_fix(self, branch, title, body, files, ticket_key="") -> dict:
        _validate_paths(files)
        if not branch.startswith("fix/"):
            raise ToolError(f"{branch!r}: publish_fix only creates fix/* branches")

        base = self.settings.github_base_branch
        base_sha = self._head(base)
        self._create_branch(branch, base_sha)

        entries = []
        for path, content in files.items():
            blob = self._call(
                "POST", "/git/blobs", json={"content": content, "encoding": "utf-8"}
            ).json()["sha"]
            entries.append(
                {"path": path.replace("\\", "/"), "mode": "100644", "type": "blob", "sha": blob}
            )

        commit_sha = self._commit(branch, base_sha, self._commit_tree(base_sha), entries, title)

        header = "_Automated remediation by Sentinel (@sre-agent) — human review required._"
        ticket = f"\n\nJira: {ticket_key}" if ticket_key else ""
        pull = self._call(
            "POST",
            "/pulls",
            json={
                "title": title,
                "head": branch,
                "base": base,
                "body": f"{header}{ticket}\n\n{body}".strip(),
            },
        ).json()
        return {
            "branch": branch,
            "commit": commit_sha,
            "pr_number": pull["number"],
            "pr_url": pull["html_url"],
            "files": sorted(files),
        }

    def rollback(self, pr_number: int, reason: str = "") -> dict:
        pull = self._call("GET", f"/pulls/{pr_number}").json()
        if not pull.get("merged"):
            raise ToolError(f"PR #{pr_number} is not merged; nothing to revert")
        merge_sha = pull["merge_commit_sha"]
        base = pull["base"]["ref"]

        parent = self._call("GET", f"/git/commits/{merge_sha}").json()["parents"][0]["sha"]
        changed = [
            item["filename"]
            for item in self._call(
                "GET", f"/pulls/{pr_number}/files", params={"per_page": 100}
            ).json()
        ]
        before = {
            item["path"]: item
            for item in self._call("GET", f"/git/trees/{parent}", params={"recursive": "1"}).json()[
                "tree"
            ]
            if item["type"] == "blob"
        }
        entries = [
            {"path": name, "mode": "100644", "type": "blob", "sha": before[name]["sha"]}
            if name in before
            else {"path": name, "mode": "100644", "type": "blob", "sha": None}
            for name in changed
        ]

        main_sha = self._head(base)
        branch = f"revert/pr-{pr_number}"
        self._create_branch(branch, main_sha)
        self._commit(
            branch,
            main_sha,
            self._commit_tree(main_sha),
            entries,
            f'Revert "{pull["title"]}"',
        )
        body = "_Automated rollback by Sentinel (@sre-agent) — human review required._"
        if reason:
            body = f"{body}\n\n{reason}"
        reverted = self._call(
            "POST",
            "/pulls",
            json={
                "title": f"Revert PR #{pr_number}",
                "head": branch,
                "base": base,
                "body": body,
            },
        ).json()
        return {"branch": branch, "pr_number": reverted["number"], "pr_url": reverted["html_url"]}

    def ci_status(self, ref: str) -> dict:
        combined = self._call("GET", f"/commits/{quote(ref, safe='')}/status").json()
        runs = self._call(
            "GET", f"/commits/{quote(ref, safe='')}/check-runs", params={"per_page": 100}
        ).json()["check_runs"]
        checks = [
            {"name": run["name"], "status": run["status"], "conclusion": run["conclusion"]}
            for run in runs
        ]
        failed = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
        # An empty combined status reads as "pending", which would make the agent
        # poll a repository that has no CI at all until its call budget ran out.
        if not checks and not combined.get("total_count"):
            state = "unknown"
        elif combined.get("state") == "failure" or any(c["conclusion"] in failed for c in checks):
            state = "failure"
        elif combined.get("state") == "pending" or any(c["status"] != "completed" for c in checks):
            state = "pending"
        elif combined.get("state") == "success" or checks:
            state = "success"
        else:
            state = "unknown"
        return {"ref": ref, "state": state, "checks": checks, "url": combined.get("target_url")}


class SlackClient:
    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self.settings = settings
        self.http = http

    def post(self, text: str) -> dict:
        if not self.settings.slack_webhook_url:
            raise ToolError("SLACK_WEBHOOK_URL is not set")
        try:
            response = self.http.post(
                self.settings.slack_webhook_url,
                json={"text": text},
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ToolError(f"slack unreachable: {type(exc).__name__}") from exc
        if not response.is_success:
            raise ToolError(f"slack post: {_error_detail(response)}")
        return {"posted": True}
