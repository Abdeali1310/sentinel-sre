import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import chaos  # noqa: E402
from app.cashfree import CashfreeClient  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app, get_client  # noqa: E402

CHAOS_TOKEN = "test-chaos-token"


class StubTransport:
    """Stands in for the provider's HTTP call. Records what we sent."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, settings, payload):
        self.calls.append(payload)
        return {
            "cf_order_id": f"cf_{payload['order_id']}",
            "order_id": payload["order_id"],
            "order_status": "ACTIVE",
            "payment_session_id": "session_stub",
        }


@pytest.fixture(autouse=True)
def _reset_chaos():
    chaos.reset()
    yield
    chaos.reset()


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'payments.db'}",
        chaos_token=CHAOS_TOKEN,
        cashfree_mode="sandbox",
        cashfree_client_id="test-client",
        cashfree_client_secret="test-secret",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def transport(app, settings):
    stub = StubTransport()
    app.dependency_overrides[get_client] = lambda: CashfreeClient(settings, transport=stub)
    return stub


@pytest.fixture
def client(app, transport):
    # raise_server_exceptions=False: an unhandled defect must be observed as the
    # 500 a customer would see, not swallowed as a test-time exception.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def enable_chaos(client):
    def _enable(requests: int = 50, ttl_seconds: int = 600) -> dict:
        response = client.post(
            "/admin/chaos",
            json={"requests": requests, "ttl_seconds": ttl_seconds},
            headers={"X-Chaos-Token": CHAOS_TOKEN},
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _enable


@pytest.fixture
def pay(client):
    def _pay(idempotency_key: str = "key-0001", amount: float = 10.00):
        return client.post(
            "/payments",
            json={"amount": amount, "currency": "INR"},
            headers={"Idempotency-Key": idempotency_key},
        )

    return _pay
