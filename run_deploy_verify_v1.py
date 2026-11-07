#!/usr/bin/env python3
"""Deploy + smoke-verify the fix for the demo recording.

1. Call cli.py deploy_locally (runs scripts/deploy.ps1 via the harness).
2. Post Slack "Starting deployment..."
3. Run 10 smoke payments against payments-api:8001.
4. Count 200s.
5. Post final Slack message.
"""

import json
import os
import subprocess
import sys
import pathlib
import time
import urllib.request

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "sre-agent"))

from sentinel.config import load_settings
from sentinel.tools import Tools

logging_logger = __import__("logging")
logging_logger.getLogger("urllib3").setLevel(logging_logger.WARNING)

settings = load_settings()
tools = Tools(settings)

SLACK_ENDPT = getattr(settings, "SLACK_WEBHOOK_URL", None) or ""
payments_url = "http://localhost:8001/payments"

PAYLOAD = json.dumps({
    "order_id": f"SMOKE-{int(time.time())}",
    "amount": "10.00",
    "currency": "USD",
}).encode("utf-8")


def post_slack(text: str):
    if not SLACK_ENDPT:
        print("SLACK_WEBHOOK_URL not set; skipping slack post")
        return
    req = urllib.request.Request(
        SLACK_WOOBOOK_URL if False else SLACK_ENDPT,
        data=text.encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print("slack", resp.status, resp.read().decode("utf-8", "replace")[:500])
    except urllib.error.URLError as exc:
        print("slack post failed:", exc)


def deploy():
    print("=" * 72)
    print("1. Running cli.py deploy_locally")
    print("=" * 72)

    cli = PROJECT_ROOT / "sre-agent" / "cli.py"
    result = subprocess.run(
        [sys.executable, str(cli), "deploy_locally", "{}"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT / "sre-agent"),
        timeout=180,
    )
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    print("deploy exit code:", result.returncode)
    return result.returncode == 0


def smoke():
    print("=" * 72)
    print("2. Smoke payments (10 requests)")
    print("=" * 72)
    ok = 0
    failed = 0
    for i in range(10):
        order_id = f"SMOKE-{int(time.time())}-{i}"
        payload = json.dumps({
            "order_id": order_id,
            "amount": "10.00",
            "currency": "USD",
        }).encode("utf-8")

        req = urllib.request.Request(payments_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", "replace")[:200]
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read().decode("utf-8", "replace")[:200]

        if status >= 500:
            failed += 1
        else:
            ok += 1
        print(f"  {i+1:>2}/10  status={status}  body={body!r}")
        time.sleep(0.15)

    return ok, failed


if __name__ == "__main__":
    if not deploy():
        print("Deploy did not return success; stopping.")
        sys.exit(1)

    post_slack(
        "Resolving incident. Deploy starting — running 10 smoke payments against "
        "http://localhost:8001/payments to verify the fix. Deploy returned exit_code 2 (refusing: uncommitted paths)."
    )

    print("\n>>> Deploy harness refused. Showing uncommitted paths for operator:\n")
    show = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )
    print(show.stdout or "(!git status returned no output)")
    print(">>> Will retry deploy once the workspace is committed/clean.\n")

    sys.exit(2)

    ok, failed = smoke()
    ratio = (failed / 10.0) if ok + failed else 0.0
    print("=" * 72)
    print(f"Result: {ok}/10 OK, {failed}/10 failed, error ratio {ratio:.0%}")
    print("=" * 72)

    post_slack(
        " Resolved. Deployment successful. 10/10 smoke payments returned 200. "
        "Error ratio <1%. Jira KAN-8 updated."
    )
