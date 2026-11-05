import asyncio

from app.cashfree import CashfreeClient
from app.config import Settings


def _replay_settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'p.db'}",
        cashfree_mode="replay",
        cashfree_client_id="test",
        cashfree_client_secret="test",
    )


def test_replay_mode_echoes_the_order_without_calling_the_provider(tmp_path):
    called = False

    async def transport(settings, payload):
        nonlocal called
        called = True
        raise AssertionError("replay mode must not reach the network")

    client = CashfreeClient(_replay_settings(tmp_path), transport=transport)
    payload = {"order_id": "ORD-500001", "order_amount": 10.0, "order_currency": "USD"}

    raw = asyncio.run(client.create_order(payload))

    assert called is False
    assert raw["order_id"] == "ORD-500001"
    assert raw["cf_order_id"] == "cf_ORD-500001"


def test_order_payload_carries_customer_details(tmp_path):
    """Cashfree answers 400 without customer_details; this pins the fix."""
    captured = {}

    async def transport(settings, payload):
        captured.update(payload)
        return {
            "cf_order_id": f"cf_{payload['order_id']}",
            "order_id": payload["order_id"],
            "order_status": "ACTIVE",
        }

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'p.db'}",
        cashfree_mode="sandbox",
        cashfree_client_id="test",
        cashfree_client_secret="test",
    )
    client = CashfreeClient(settings, transport=transport)
    payload = {"order_id": "ORD-500002", "order_amount": 10.0, "order_currency": "USD"}

    asyncio.run(client.create_order(payload))

    details = captured["customer_details"]
    assert details["customer_id"] == "ORD-500002"
    assert details["customer_email"]


def test_replay_mode_must_be_explicit(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'p.db'}",
        cashfree_mode="sandbox",
    )

    assert settings.cashfree_mode == "sandbox"
