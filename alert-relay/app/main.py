"""Alertmanager to Slack relay.

Alertmanager sends one webhook per group. Each alert becomes a short message
carrying what the agent needs to start: severity, current value, fingerprint,
runbook, and the literal mention that wakes it.
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings

logger = logging.getLogger("alert-relay")

Poster = Callable[[str], Awaitable[None]]

REQUEST_TIMEOUT_SECONDS = 10.0


def fingerprint_of(labels: dict) -> str:
    canonical = json.dumps(labels, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_message(alert: dict, *, runbook_url: str) -> str:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    name = labels.get("alertname", "Alert")
    severity = labels.get("severity", "unknown")
    fingerprint = alert.get("fingerprint") or fingerprint_of(labels)
    value = annotations.get("description") or annotations.get("summary") or "no detail"

    lines = [
        f"*{name}* · {severity}",
        value,
        f"Fingerprint: `{fingerprint}`",
    ]
    if runbook_url:
        lines.append(f"Runbook: {runbook_url}")
    # Switch wakes an agent on a plain `@name` in the body, matched by its own
    # token regex after the Slack bridge translates the message. Slack's
    # `<@ID>` pill is not required and is not resolved for third-party bots.
    lines.append("@sre-agent")
    return "\n".join(lines)


def resolve_webhook_url(url: str, *, in_container: bool) -> str:
    """A webhook bound to the host's loopback is not reachable from a container."""
    if not in_container:
        return url
    parts = urlsplit(url)
    if parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return url
    netloc = "host.docker.internal"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class SlackPoster:
    def __init__(self, settings: Settings) -> None:
        self.url = resolve_webhook_url(
            settings.slack_webhook_url,
            in_container=Path("/.dockerenv").exists(),
        )

    async def __call__(self, text: str) -> None:
        # The webhook is bound to #incidents, so send text and nothing else.
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(self.url, json={"text": text})
            response.raise_for_status()


def create_app(settings: Settings, poster: Poster | None = None) -> FastAPI:
    app = FastAPI(title="Sentinel alert relay", version="1.0.0")
    app.state.settings = settings
    app.state.poster = poster or SlackPoster(settings)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/webhook")
    async def webhook(request: Request, payload: dict):
        alerts = payload.get("alerts") or []
        posted = 0
        failed = 0
        for alert in alerts:
            try:
                await request.app.state.poster(
                    build_message(alert, runbook_url=settings.runbook_url)
                )
                posted += 1
                logger.info(
                    "alert_posted alertname=%s",
                    (alert.get("labels") or {}).get("alertname", "Alert"),
                )
            except httpx.HTTPError as exc:
                failed += 1
                logger.warning("slack_post_failed error=%s", type(exc).__name__)
        if failed:
            return JSONResponse(status_code=502, content={"posted": posted, "failed": failed})
        return {"posted": posted}

    return app


app = create_app(Settings())
