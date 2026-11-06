"""Sentinel MCP server.

Registers the read-only diagnosis tools with FastMCP. Every tool delegates to
`sentinel.tools.Tools`, which owns the budget, the jail and the redaction.
"""

from mcp.server.fastmcp import FastMCP

from sentinel.config import load_settings
from sentinel.tools import Tools

settings = load_settings()
tools = Tools(settings)

mcp = FastMCP("sentinel-sre")


@mcp.tool()
def health_check() -> dict:
    """Preflight: payments-api, Prometheus and Alertmanager reachability."""
    return tools.health_check()


@mcp.tool()
def fetch_logs(tail: int = 200) -> str:
    """Recent payments-api container logs. `tail` is capped at 2000 lines."""
    return tools.fetch_logs(tail=tail)


@mcp.tool()
def query_prometheus(query: str) -> dict:
    """Instant PromQL query against the local Prometheus."""
    return tools.query_prometheus(query)


@mcp.tool()
def get_payment(order_id: str) -> dict:
    """One payment ledger row, by order id (for example ORD-1234)."""
    return tools.get_payment(order_id)


@mcp.tool()
def read_file(path: str) -> str:
    """Read a UTF-8 file inside the agent workspace, given a relative path."""
    return tools.read_file(path)


@mcp.tool()
def search_code(pattern: str, glob: str = "*.py") -> list[dict]:
    """Regex search inside the agent workspace; vendor directories are skipped."""
    return tools.search_code(pattern, glob=glob)


@mcp.tool()
def run_tests() -> dict:
    """Run the payments-api pytest suite with the project interpreter."""
    return tools.run_tests()


@mcp.tool()
def create_jira_ticket(
    summary: str, description: str, labels: list[str] | None = None, requested_by: str = ""
) -> dict:
    """Create one incident ticket in the Jira project."""
    return tools.create_jira_ticket(summary, description, labels, requested_by)


@mcp.tool()
def update_jira_ticket(
    issue_key: str, comment: str = "", transition: str = "", requested_by: str = ""
) -> dict:
    """Comment on a ticket and/or move it through its workflow."""
    return tools.update_jira_ticket(issue_key, comment, transition, requested_by)


@mcp.tool()
def publish_fix(
    branch: str,
    title: str,
    body: str,
    files: dict[str, str],
    ticket_key: str = "",
    requested_by: str = "",
) -> dict:
    """Commit files via the Git Data API and open a review PR. Never pushes or merges."""
    return tools.publish_fix(branch, title, body, files, ticket_key, requested_by)


@mcp.tool()
def rollback(pr_number: int, reason: str = "", requested_by: str = "") -> dict:
    """Open a revert PR for a merged fix. A human still merges it."""
    return tools.rollback(pr_number, reason, requested_by)


@mcp.tool()
def get_ci_status(ref: str) -> dict:
    """CI state and check runs for a branch or commit."""
    return tools.get_ci_status(ref)


@mcp.tool()
def post_mattermost(text: str, requested_by: str = "") -> dict:
    """Post a milestone message to the incident room."""
    return tools.post_mattermost(text, requested_by)


if __name__ == "__main__":
    mcp.run(transport="stdio")
