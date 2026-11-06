"""Settings for the Sentinel MCP server.

The root `.env` is the single source of truth for credentials; it is shared
with the two services in `docker compose`.
"""

import base64
import re
import sys
from pathlib import Path

from dotenv import dotenv_values
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_DIR = Path(__file__).resolve().parents[2]
IS_WINDOWS = sys.platform == "win32"

_SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|WEBHOOK)", re.IGNORECASE)


def default_tests_python() -> str:
    python = "Scripts/python.exe" if IS_WINDOWS else "bin/python"
    return str(REPO_DIR / "payments-api" / ".venv" / python)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_url: str = "http://localhost:8001"
    prometheus_url: str = "http://localhost:9091"
    alertmanager_url: str = "http://localhost:9093"

    repo_dir: str = str(REPO_DIR)
    workspace_dir: str = str(REPO_DIR / "sre-agent" / "workspaces" / "sentinel-sre")
    tests_python: str = default_tests_python()

    max_tool_calls: int = 15
    max_wall_clock_seconds: int = 600
    max_output_bytes: int = 20_000
    log_tail_max: int = 2_000

    # Record-keeping and change tools (M5).
    mattermost_webhook_url: str = ""
    mattermost_channel: str = "#incidents"
    mattermost_allowed_users: str = ""

    jira_url: str = ""
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "KAN"
    jira_issue_type: str = "Task"
    jira_labels: str = "incident,sre-agent"
    jira_transition_in_progress: str = "In Progress"
    jira_transition_done: str = "Done"

    github_token: str = ""
    github_owner: str = "Abdeali1310"
    github_repo: str = "sentinel-sre"
    github_base_branch: str = "main"

    @model_validator(mode="after")
    def _split_owner_from_repo(self):
        """`.env.example` allows GITHUB_REPO=owner/repo; the client needs them apart."""
        if "/" in self.github_repo:
            owner, _, repo = self.github_repo.partition("/")
            self.github_owner = owner
            self.github_repo = repo
        return self

    @property
    def jira_site(self) -> str:
        return (self.jira_url or self.jira_base_url).rstrip("/")

    @property
    def jira_auth_header(self) -> str:
        raw = f"{self.jira_email}:{self.jira_api_token}".encode()
        return "Basic " + base64.b64encode(raw).decode("ascii")

    # Filled at startup from .env so a live credential can never be echoed
    # back to the model by accident.
    secrets: list[str] = []


def load_settings(env_file: Path | None = None) -> Settings:
    """Settings plus the literal secret values, so redaction knows them by value."""
    path = env_file or (REPO_DIR / ".env")
    values = dotenv_values(path) if path.is_file() else {}
    secrets = [
        value.strip()
        for name, value in values.items()
        if value and _SECRET_NAME.search(name) and len(value.strip()) >= 8
    ]
    return Settings(secrets=secrets)
