"""Publish the KAN-8 fix via GitHub Git Data API."""

import json
import sys
import sys
sys.path.insert(0, ".")

from sentinel.config import load_settings
from sentinel.tools import Tools

settings = load_settings()
tools = Tools(settings)

import pathlib

files = {
    "payments-api/app/main.py": (pathlib.Path("..") / "payments-api" / "app" / "main.py").read_text(encoding="utf-8")
}

result = tools.publish_fix(
    branch="fix/KAN-8-upstream-response-shape",
    title="validate upstream response shape before indexing it",
    body="Validates that the Cashfree upstream response contains the required keys (`order_id`, `cf_order_id`) before using them, instead of relying on KeyError exception handling.\n\n### Changes\n- `payments-api/app/main.py`: validate required keys exist in upstream response before indexing; log actual keys received on failure\n\n### Test\n- `payments-api/tests/test_upstream_contract.py`: existing tests pass; validates 502 + FAILED status on malformed upstream response",
    files=files,
    ticket_key="KAN-8",
    requested_by="Ninja",
)

print(json.dumps(result, indent=2))
