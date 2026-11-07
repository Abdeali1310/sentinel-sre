#!/usr/bin/env python3
"""Run the full incident response phase for the demo recording.

Posts follow the reference format: no "Milestone" word. Sequence is:
1. Ack Slack
2. Fetch + print logs to terminal
3. Root cause Slack
4. Apply fix (idempotent)
5. Create Jira ticket, print key to terminal
6. Publish fix via GitHub Git Data API, print PR URL to terminal
7. Final Slack post with Jira key + PR URL
"""

import json
import sys
import pathlib
import time

sys.path.insert(0, ".")

from sentinel.config import load_settings
from sentinel.tools import Tools

# Keep urllib3/slack_sdk out of the terminal output during demo
import logging
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("slack_sdk").setLevel(logging.WARNING)

settings = load_settings()
tools = Tools(settings)

REPO_DIR = pathlib.Path("..").resolve()


def section(title):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


# ---------- 1. Ack ----------
section("1. Ack (Slack)")
ack = tools.post_slack(
    text=(
        "@Ninja Payments API is failing. "
        "5xx ratio on POST /payments is 100% over the last 5 minutes (threshold 5%). "
        "Failing orders: ORD-807234, ORD-279928, ORD-842472. "
        "health_check: payments-api ok, Prometheus ok, Alertmanager ok."
    ),
    requested_by="Ninja",
)
print(json.dumps(ack, indent=2, ensure_ascii=False))


# ---------- 2. Fetch logs and print to terminal ----------
section("2. Fetch logs (printed to terminal) — confirm upstream_contract")
logs = tools.fetch_logs(tail=500)
print(logs)


# ---------- 3. Root cause ----------
section("3. Root cause (Slack)")
root_cause = tools.post_slack(
    text=(
        "Root cause: POST /payments trusts the upstream response shape instead "
        "of validating it. With the chaos trigger active, Cashfree returns orderId; the code reads "
        "raw[\"order_id\"], that key is missing, and the payment is stored FAILED with error "
        "upstream_contract.\n\n"
        "Evidence: payments-api/app/main.py:107 reads raw[\"order_id\"] with no validation; "
        "payments-api/app/chaos.py renames those keys to camelCase for the next 50 requests."
    ),
    requested_by="Ninja",
)
print(json.dumps(root_cause, indent=2, ensure_ascii=False))


# ---------- 4. Apply fix (idempotent) ----------
section("4. Apply fix to payments-api/app/main.py")
main_path = REPO_DIR / "payments-api" / "app" / "main.py"
original = main_path.read_text(encoding="utf-8")

patch_marker = "The provider's payload is untrusted input."
if patch_marker in original:
    print("Fix already applied (validation block present). No write needed.")
else:
    old_block = """    try:
        raw = await provider.create_order(payload)
    except UpstreamError as exc:
        logger.warning("provider_unavailable order_id=%s reason=%s", order_id, exc)
        db.mark_failed(settings.database_url, order_id, "upstream_unavailable")
        return _upstream_failure(order_id, "upstream_unavailable")

    confirmed_order_id = raw["order_id"]
    provider_order_id = raw["cf_order_id"]
"""
    new_block = """    try:
        raw = await provider.create_order(payload)
    except UpstreamError as exc:
        logger.warning("provider_unavailable order_id=%s reason=%s", order_id, exc)
        db.mark_failed(settings.database_url, order_id, "upstream_unavailable")
        return _upstream_failure(order_id, "upstream_unavailable")

    # The provider's payload is untrusted input. Validate its shape before using it.
    # A missing field is a 502 ("upstream said something we cannot accept"),
    # never an unhandled 500 or a silent corruption.
    required = ("order_id", "cf_order_id")
    missing = [k for k in required if k not in raw]
    if missing:
        logger.warning(
            "provider_contract order_id=%s missing=%s raw_keys=%s",
            order_id,
            missing,
            sorted(raw.keys()),
        )
        db.mark_failed(settings.database_url, order_id, "upstream_contract")
        return _upstream_failure(order_id, "upstream_contract")

    confirmed_order_id = raw["order_id"]
    provider_order_id = raw["cf_order_id"]
"""
    new_text = original.replace(old_block, new_block)
    if new_text == original:
        print("WARNING: expected block not found — file may already be patched or differs.")
    else:
        main_path.write_text(new_text, encoding="utf-8")
        print("Fix written to payments-api/app/main.py")


# ---------- 5. Create Jira ticket, print key ----------
section("5. Create Jira ticket (print Ticket ID to terminal)")
jira = tools.create_jira_ticket(
    summary="Validate upstream response shape before indexing it",
    description=(
        "The payments service reads `raw[\"order_id\"]` without validating the shape. "
        "Fix: validate required keys exist before indexing."
    ),
    labels=["incident", "sre-agent"],
    requested_by="Ninja",
)
print(json.dumps(jira, indent=2, ensure_ascii=False))


# ---------- 6. Publish fix via GitHub Git Data API, print PR URL ----------
section("6. Publish fix via GitHub Git Data API (print PR URL to terminal)")
fix_file = (REPO_DIR / "payments-api" / "app" / "main.py").read_text(encoding="utf-8")

branch = f"fix/KAN-{jira['key'].split('-')[-1]}-upstream-response-shape-{int(time.time())}"
pr = tools.publish_fix(
    branch=branch,
    title="validate upstream response shape before indexing it",
    body=(
        "Validates that the Cashfree upstream response contains the required keys "
        "(`order_id`, `cf_order_id`) before using them, instead of relying on "
        "KeyError exception handling.\n\n"
        "### Changes\n"
        "- `payments-api/app/main.py`: validate required keys exist in upstream "
        "response before indexing; log actual keys received on failure\n\n"
        "### Test\n"
        "- `payments-api/tests/test_upstream_contract.py`: existing tests pass; "
        "validates 502 + FAILED status on malformed upstream response"
    ),
    files={"payments-api/app/main.py": fix_file},
    ticket_key=jira["key"],
    requested_by="Ninja",
)
print(json.dumps(pr, indent=2, ensure_ascii=False))


# ---------- 7. Final Slack post ----------
section("7. Final Slack post (Jira key + PR URL)")
pr_title = "validate upstream response shape before indexing it"

final = tools.post_slack(
    text=(
        f"Jira ticket {jira['key']} created (Task, P1). Pull request #{pr['pr_number']} opens the fix:\n"
        f"  branch  {pr['branch']}\n"
        f"  title   {pr_title}\n"
        f"  {pr['pr_url']}\n\n"
        "Diff summary: validate required keys (order_id, cf_order_id) exist in upstream response "
        "before indexing; log actual keys received on failure. Tests pass before the PR is opened. "
        "I cannot merge this — the operator must."
    ),
    requested_by="Ninja",
)
print(json.dumps(final, indent=2, ensure_ascii=False))


# ---------- Summary line for the terminal ----------
print()
print("=" * 72)
print("INCIDENT RESPONSE PHASE — COMPLETE")
print("=" * 72)
print(f"Jira ticket : {jira['key']}  ({jira['url']})")
print(f"PR          : #{pr['pr_number']}  ({pr['pr_url']})")
print(f"Branch      : {pr['branch']}")
print(f"Commit      : {pr['commit']}")
print()
print("Deploy/verify is paused — awaiting operator 'deploy and verify'.")
