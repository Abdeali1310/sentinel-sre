"""CLI harness for the Sentinel tools.

Used to prove each tool works against the live stack without a chat provider:

    python cli.py health_check
    python cli.py query_prometheus '{"query": "up"}'

The argument is JSON, and only names in `TOOLS` can be dispatched. On Windows,
pass `-` and pipe the JSON through stdin: quoting survives intact that way.
"""

import json
import sys

from sentinel.config import load_settings
from sentinel.tools import ToolError, Tools

TOOLS = {
    "health_check",
    "fetch_logs",
    "query_prometheus",
    "get_payment",
    "read_file",
    "search_code",
    "run_tests",
    "create_jira_ticket",
    "update_jira_ticket",
    "publish_fix",
    "rollback",
    "deploy_locally",
    "get_ci_status",
    "post_mattermost",
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in TOOLS:
        print("usage: python cli.py <" + "|".join(sorted(TOOLS)) + "> [json-args]", file=sys.stderr)
        return 2

    name = argv[1]
    if len(argv) > 2 and argv[2] == "-":
        raw = sys.stdin.read()
    else:
        raw = argv[2] if len(argv) > 2 else "{}"
    arguments = json.loads(raw)
    tool = Tools(load_settings())

    try:
        result = getattr(tool, name)(**arguments)
    except ToolError as exc:
        print(json.dumps({"tool_error": str(exc)}, ensure_ascii=False))
        return 1
    except Exception as exc:  # surfaced, never swallowed
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
