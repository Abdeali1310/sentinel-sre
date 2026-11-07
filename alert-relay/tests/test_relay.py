"""Behaviour of the alert relay at its public seam: the webhook Alertmanager calls.

The Slack call is replaced by a recorder, so these tests never touch the
network or a real room.
"""

import asyncio

import httpx
import pytest
from app.config import Settings
from app.main import SlackPoster, create_app, resolve_webhook_url
from fastapi.testclient import TestClient

RUNBOOK = "https://example.test/runbook"
FINGERPRINT = "0f1e2d3c4b5a6978"


def alert_payload(**alert_overrides) -> dict:
    alert = {
        "status": "firing",
        "labels": {
            "alertname": "PaymentsApi5xxSpike",
            "severity": "critical",
            "service": "payments-api",
        },
        "annotations": {
            "summary": "Payments API 5xx ratio above 5%",
            "description": "5xx ratio is 18.2% over the last 5 minutes.",
        },
        "startsAt": "2026-11-05T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "http://localhost:9091/graph",
        "fingerprint": FINGERPRINT,
    }
    alert.update(alert_overrides)
    return {
        "version": "4",
        "status": "firing",
        "receiver": "sentinel-relay",
        "groupKey": '{}:{alertname="PaymentsApi5xxSpike"}',
        "alerts": [alert],
    }


class RecordingPoster:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def __call__(self, text: str) -> None:
        self.messages.append(text)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        slack_webhook_url="https://hooks.slack.com/services/test",
        runbook_url=RUNBOOK,
    )


@pytest.fixture
def poster() -> RecordingPoster:
    return RecordingPoster()


@pytest.fixture
def client(settings, poster) -> TestClient:
    return TestClient(create_app(settings, poster=poster))


def test_firing_alert_is_posted_with_the_evidence_the_agent_needs(client, poster):
    response = client.post("/webhook", json=alert_payload())

    assert response.status_code == 200
    assert len(poster.messages) == 1

    text = poster.messages[0]
    assert "PaymentsApi5xxSpike" in text
    assert "critical" in text
    assert "18.2%" in text  # the current value, as Prometheus rendered it
    assert FINGERPRINT in text
    assert RUNBOOK in text
    assert "@sre-agent" in text


def test_missing_fingerprint_falls_back_to_a_stable_hash(client, poster):
    payload = alert_payload(fingerprint="")

    first = client.post("/webhook", json=payload)
    second = client.post("/webhook", json=payload)

    assert first.status_code == second.status_code == 200
    assert len(poster.messages) == 2
    assert poster.messages[0] == poster.messages[1]
    assert "Fingerprint: `" in poster.messages[0]


def test_slack_failure_is_surfaced_so_alertmanager_retries(settings):
    class BrokenPoster:
        async def __call__(self, text: str) -> None:
            raise httpx.ConnectError("slack unreachable")

    client = TestClient(create_app(settings, poster=BrokenPoster()))

    response = client.post("/webhook", json=alert_payload())

    assert response.status_code == 502


def test_empty_alert_batch_is_accepted_without_posting(client, poster):
    response = client.post("/webhook", json={"version": "4", "status": "firing", "alerts": []})

    assert response.status_code == 200
    assert poster.messages == []


def test_loopback_webhook_is_rewritten_for_the_container():
    """A webhook on the host's loopback is reachable from a container only by name."""

    rewritten = resolve_webhook_url("http://localhost:8065/hooks/abc", in_container=True)

    assert rewritten == "http://host.docker.internal:8065/hooks/abc"


def test_remote_webhook_is_left_alone():
    url = "https://hooks.slack.com/services/abc"

    assert resolve_webhook_url(url, in_container=True) == url
    assert resolve_webhook_url("http://localhost:8065/hooks/abc", in_container=False) == (
        "http://localhost:8065/hooks/abc"
    )


def test_poster_sends_text_and_nothing_else(monkeypatch, settings):
    """Slack rejects a body whose only top-level key is not `text`."""
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def post(self, url, json):
            seen["url"] = url
            seen["json"] = json
            return httpx.Response(200, text="ok", request=httpx.Request("POST", url))

    monkeypatch.setattr("app.main.httpx.AsyncClient", FakeClient)

    asyncio.run(SlackPoster(settings)("*PaymentsApi5xxSpike* · critical"))

    assert seen["json"] == {"text": "*PaymentsApi5xxSpike* · critical"}
    assert seen["url"] == "https://hooks.slack.com/services/test"
