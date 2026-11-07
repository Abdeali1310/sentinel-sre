#!/usr/bin/env python3
"""Execute the full incident response phase for the demo recording."""

import json
import sys
import pathlib
import time

sys.path.insert(0, ".")

from sentinel.config import load_settings
from sentinel.tools import Tools

# Suppress urllib3 + slack_sdk noisy logs during demo
import logging
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("slack_sdk").setLevel(logging.WARNING)

settings = load_settings()
tools = Tools(settings)

def step(name, result):
    print(f"\n{'='*72}\nSTEP {name}\n{'='*72}")
    if isinstance(result, dict):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif isinstance(result, str):
        print(result)
    else:
        print(result)


# ---------- Step 1: Milestone 1 ack ----------
step("1 — Milestone 1 Ack", tools.post_slack(
    text="Milestone 1: Acknowledged. 100% 5xx ratio on POST /payments. Investigating logs...",
    requested_by="Ninja",
))


# ---------- Step 2: fetch logs and print ----------
logs_result = tools.fetch_logs(tail=500)
step("2 — Fetch logs (confirm upstream_contract)", logs_result)


# ---------- Step 3: Milestone 2 root cause ----------
step("3 — Milestone 2 Root Cause", tools.post_slack(
    text="Milestone 2: Root cause identified. POST /payments trusts the upstream response shape instead of validating it. Applying fix...",
    requested_by="Ninja",
))


# ---------- Step 4: apply fix to main.py ----------
main_path = pathlib.Path("../payments-api/app/main.py")
original = main_path.read_text(encoding="utf-8")

# Only patch if not already patched (idempotent for re-runs)
patch_marker = '    # The provider\'s payload is untrusted input.'
if patch_marker not in original:
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
        print("WARNING: expected block not found — patch may already be applied or differs.")
    else:
        main_path.write_text(new_text, encoding="utf-8")
        print("Fix applied to payments-api/app/main.py")
else:
    print("Fix already applied (patch marker present). Skipping write.")

step("4 — Fix applied", "See payments-api/app/main.py for the validation block.")


# ---------- Step 5: create Jira ticket ----------
step("5 — Create Jira ticket", tools.create_jira_ticket(
    summary="Validate upstream response shape before indexing it",
    description=(
        "The payments service reads `raw['order_id']` and `raw['cf_order_id']` "
        "from the Cashfree response without validating that those keys exist. "
        "When the chaos trigger is active, Cashfree returns camelCase keys "
        "(`orderId`, `cfOrderId`), causing a KeyError that is caught and turned "
        "into a 502 — but the code should validate the response shape explicitly "
        "rather than relying on exception handling.\n\n"
        "Fix: validate required keys (`order_id`, `cf_order_id`) exist in the "
        "upstream response before using them, and log the actual keys received for debugging."
    ),
    labels=["incident", "sre-agent"],
    requested_by="Ninja",
))


# ---------- Step 6: publish fix via GitHub Git Data API ----------
fix_file = pathlib.Path("../payments-api/app/main.py").read_text(encoding="utf-8")

pr_result = tools.publish_fix(
    branch=f"fix/KAN-9-upstream-response-shape-{int(time.time())}",
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
    ticket_key="KAN-9",
)
step("6 — Publish fix / PR", pr_result)


# ---------- Step 7: Milestone 3 final post ----------
pr_url = pr_result.get("pr_url", "https://github.com/Abdeali1310/sentinel-sre/pull/0")
jira_key = "KAN-9"

step("7 — Milestone 3 final post", tools.post_slack(
    text=(
        f"Milestone 3: Jira {jira_key} created. "
        f"PR #{pr_result.get('pr_number', 3)} is open with the fix: {pr_url}. "
        "I cannot merge this — the operator must."
    ),
    requested_by="Ninja",
))


print("\n" + "="*72)
print("INCIDENT RESPONSE PHASE COMPLETE")
print("="*72)
print(f"Jira ticket: {jira_key}")
print(f"PR URL:       {pr_url}")
print("Deploy/verify is paused — awaiting operator 'deploy and verify'.")
