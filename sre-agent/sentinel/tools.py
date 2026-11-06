"""Read-only tools for the Sentinel SRE agent.

Every tool takes plain data (an order id, a PromQL string, a relative path) and
never a shell command, so the model cannot turn a diagnosis into execution.
"""

import fnmatch
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

import httpx

from .budget import Budget
from .clients import GitHubClient, JiraClient, MattermostClient
from .config import Settings
from .errors import ToolError
from .redact import redact

logger = logging.getLogger("sentinel.tools")

REQUEST_TIMEOUT_SECONDS = 15
COMMAND_TIMEOUT_SECONDS = 300
MAX_SEARCH_MATCHES = 50
MAX_SERIES = 50
MAX_TEST_OUTPUT_CHARS = 4_000
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}
ORDER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _default_runner(argv, cwd=None, timeout=None):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)


class Tools:
    def __init__(
        self, settings: Settings, http: httpx.Client | None = None, runner=None, budget=None
    ):
        self.settings = settings
        self.http = http or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        self.runner = runner or _default_runner
        self.budget = budget or Budget(
            max_calls=settings.max_tool_calls,
            max_seconds=settings.max_wall_clock_seconds,
        )
        self.jira = JiraClient(settings, self.http)
        self.github = GitHubClient(settings, self.http)
        self.mattermost = MattermostClient(settings, self.http)

    @property
    def repo(self) -> Path:
        return Path(self.settings.repo_dir)

    @property
    def workspace(self) -> Path:
        return Path(self.settings.workspace_dir).resolve()

    def _clean(self, text: str) -> str:
        return redact(text, self.settings.secrets)

    def _claim(self, tool: str, write: bool = False) -> None:
        self.budget.claim(tool, write=write)

    def _require_operator(self, requested_by: str, action: str) -> None:
        """R7.5: an advisory allowlist, logged whether it allows or refuses."""
        allowed = [
            user.strip().lstrip("@").casefold()
            for user in self.settings.mattermost_allowed_users.split(",")
            if user.strip()
        ]
        who = (requested_by or "").strip().lstrip("@")
        if allowed and who and who.casefold() not in allowed:
            logger.warning("write refused action=%s requested_by=%r", action, who)
            raise ToolError(f"{action}: {who} is not on the operator allowlist")
        logger.info(
            "write allowed action=%s requested_by=%r allowlist=%s",
            action,
            who or "unknown",
            allowed or "unset",
        )

    def _get(self, url: str, **kwargs) -> httpx.Response:
        try:
            return self.http.get(url, **kwargs)
        except httpx.HTTPError as exc:
            raise ToolError(f"{url} unreachable: {type(exc).__name__}") from exc

    # ------------------------------------------------------------------ health

    def health_check(self) -> dict:
        """Preflight: is every dependency this incident depends on alive?"""
        self._claim("health_check")

        checks = {
            "payments-api": (f"{self.settings.api_url}/healthz", True),
            "prometheus": (f"{self.settings.prometheus_url}/-/ready", False),
            "alertmanager": (f"{self.settings.alertmanager_url}/-/healthy", False),
        }
        dependencies = {}
        for name, (url, parse_json) in checks.items():
            try:
                response = self._get(url)
            except ToolError as exc:
                dependencies[name] = {"ok": False, "detail": str(exc)}
                continue
            if not response.is_success:
                dependencies[name] = {"ok": False, "detail": f"HTTP {response.status_code}"}
                continue
            detail = response.json() if parse_json else response.text.strip()
            dependencies[name] = {"ok": True, "detail": detail}

        return {
            "ok": all(item["ok"] for item in dependencies.values()),
            "dependencies": dependencies,
        }

    # -------------------------------------------------------------------- logs

    def fetch_logs(self, tail: int = 200) -> str:
        """Recent payments-api logs. Fixed argv; the model chooses only the depth."""
        self._claim("fetch_logs")
        tail = max(1, min(int(tail), self.settings.log_tail_max))
        argv = [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "logs",
            "--no-color",
            "--tail",
            str(tail),
            "payments-api",
        ]
        completed = self.runner(argv, cwd=str(self.repo), timeout=COMMAND_TIMEOUT_SECONDS)
        return self._clean((completed.stdout or "") + (completed.stderr or ""))

    # --------------------------------------------------------------- metrics

    def query_prometheus(self, query: str) -> dict:
        """Instant PromQL query. Returns the series, not a rendered picture."""
        self._claim("query_prometheus")
        if not query or not query.strip():
            raise ToolError("query is empty")
        response = self._get(
            f"{self.settings.prometheus_url}/api/v1/query", params={"query": query}
        )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ToolError(f"prometheus returned non-JSON (HTTP {response.status_code})") from exc
        if not response.is_success or payload.get("status") != "success":
            raise ToolError(str(payload.get("error") or f"HTTP {response.status_code}"))

        data = payload.get("data") or {}
        result = data.get("result")
        if isinstance(result, list):
            data = {**data, "result": result[:MAX_SERIES]}
        return data

    # -------------------------------------------------------------------- data

    def get_payment(self, order_id: str) -> dict:
        """One payment row, by the id a customer or an alert would quote."""
        self._claim("get_payment")
        if not ORDER_ID.match(order_id or ""):
            raise ToolError(f"invalid order id: {order_id!r}")
        response = self._get(f"{self.settings.api_url}/payments/{quote(order_id, safe='')}")
        if response.status_code == 404:
            detail = response.json().get("detail", "payment not found")
            raise ToolError(f"{order_id}: {detail}")
        if not response.is_success:
            raise ToolError(f"{order_id}: HTTP {response.status_code}")
        return response.json()

    # -------------------------------------------------------------------- code

    def read_file(self, path: str) -> str:
        """A file inside the agent workspace. Escapes are refused, not sanitised."""
        self._claim("read_file")
        target = (self.workspace / path).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise ToolError(f"{path} is outside the workspace")
        if not target.is_file():
            raise ToolError(f"{path} does not exist")
        return self._clean(target.read_text(encoding="utf-8", errors="replace"))

    def search_code(self, pattern: str, glob: str = "*.py") -> list[dict]:
        """Regex search inside the workspace, vendor directories excluded."""
        self._claim("search_code")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ToolError(f"invalid pattern: {exc}") from exc

        matches: list[dict] = []
        for root, directories, files in os.walk(self.workspace):
            directories[:] = [d for d in directories if d not in SKIP_DIRS]
            for name in files:
                if not fnmatch.fnmatch(name, glob):
                    continue
                file_path = Path(root) / name
                try:
                    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for number, line in enumerate(lines, start=1):
                    if compiled.search(line):
                        matches.append(
                            {
                                "path": file_path.relative_to(self.workspace).as_posix(),
                                "line": number,
                                "text": self._clean(line.strip())[:200],
                            }
                        )
                        if len(matches) >= MAX_SEARCH_MATCHES:
                            return matches
        return matches

    # ------------------------------------------------------------------ tests

    def run_tests(self) -> dict:
        """The project suite, run with the project interpreter."""
        self._claim("run_tests")
        completed = self.runner(
            [self.settings.tests_python, "-m", "pytest", "-q"],
            cwd=str(self.repo / "payments-api"),
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return {
            "ok": completed.returncode == 0,
            "output": self._clean(output[-MAX_TEST_OUTPUT_CHARS:]),
        }

    # ----------------------------------------------------------- record-keeping

    def create_jira_ticket(
        self,
        summary: str,
        description: str,
        labels: list[str] | None = None,
        requested_by: str = "",
    ) -> dict:
        """One incident ticket in the configured project."""
        self._claim("create_jira_ticket", write=True)
        self._require_operator(requested_by, "create_jira_ticket")
        if not summary.strip():
            raise ToolError("summary is empty")
        chosen = labels or [
            label.strip() for label in self.settings.jira_labels.split(",") if label.strip()
        ]
        return {**self.jira.create_issue(summary, description, chosen), "labels": chosen}

    def update_jira_ticket(
        self,
        issue_key: str,
        comment: str = "",
        transition: str = "",
        requested_by: str = "",
    ) -> dict:
        """Add a comment and/or move the ticket through its workflow."""
        self._claim("update_jira_ticket", write=True)
        self._require_operator(requested_by, "update_jira_ticket")
        if not comment.strip() and not transition.strip():
            raise ToolError("nothing to update: pass a comment, a transition, or both")
        if comment.strip():
            self.jira.comment(issue_key, comment)
        moved = self.jira.transition(issue_key, transition) if transition.strip() else ""
        return {"key": issue_key, "comment_added": bool(comment.strip()), "transition": moved}

    # ------------------------------------------------------------------- change

    def publish_fix(
        self,
        branch: str,
        title: str,
        body: str,
        files: dict[str, str],
        ticket_key: str = "",
        requested_by: str = "",
    ) -> dict:
        """Commit files through the Git Data API and open a PR. Never pushes."""
        self._claim("publish_fix", write=True)
        self._require_operator(requested_by, "publish_fix")
        return self.github.publish_fix(branch, title, body, files, ticket_key)

    def rollback(self, pr_number: int, reason: str = "", requested_by: str = "") -> dict:
        """Open a revert PR for a merged fix. A human still merges it."""
        self._claim("rollback", write=True)
        self._require_operator(requested_by, "rollback")
        return self.github.rollback(int(pr_number), reason)

    def get_ci_status(self, ref: str) -> dict:
        """Workflow conclusions for a branch or commit."""
        self._claim("get_ci_status")
        if not ref.strip():
            raise ToolError("ref is empty")
        return self.github.ci_status(ref)

    # ------------------------------------------------------------------ reporting

    def post_mattermost(self, text: str, requested_by: str = "") -> dict:
        """Milestone message. Reporting stays available after the write lockout."""
        self._claim("post_mattermost")
        self._require_operator(requested_by, "post_mattermost")
        if not text.strip():
            raise ToolError("message is empty")
        return self.mattermost.post(self._clean(text))
