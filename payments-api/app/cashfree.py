"""Cashfree client.

The transport is injectable so tests can exercise our parsing and the chaos path
without touching the network. The provider's response is untrusted input.
"""

from collections.abc import Awaitable, Callable

import httpx

from . import chaos
from .config import Settings

Transport = Callable[[Settings, dict], Awaitable[dict]]

REQUEST_TIMEOUT_SECONDS = 10.0


class UpstreamError(Exception):
    """The provider was unreachable or refused the order."""


async def post_order(settings: Settings, payload: dict) -> dict:
    url = f"{settings.cashfree_base_url.rstrip('/')}/orders"
    headers = {
        "x-client-id": settings.cashfree_client_id,
        "x-client-secret": settings.cashfree_client_secret,
        "x-api-version": settings.cashfree_api_version,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"transport failure: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        raise UpstreamError(f"provider returned {response.status_code}")

    return response.json()


def _replay(payload: dict) -> dict:
    """A recorded sandbox response shape, echoing the order we sent.

    Used only when CASHFREE_MODE=replay is set deliberately. There is no
    automatic fallback: a silent replay would hide a real provider outage.
    """
    order_id = payload["order_id"]
    return {
        "cf_order_id": f"cf_{order_id}",
        "order_id": order_id,
        "order_status": "ACTIVE",
        "payment_session_id": f"session_{order_id}",
    }


class CashfreeClient:
    def __init__(self, settings: Settings, transport: Transport | None = None) -> None:
        self.settings = settings
        self.transport = transport or post_order

    async def create_order(self, payload: dict) -> dict:
        degraded = chaos.consume()

        if self.settings.cashfree_mode == "replay":
            raw = _replay(payload)
        else:
            raw = await self.transport(self.settings, _with_customer(payload))

        return chaos.degrade(raw) if degraded else raw


def _with_customer(payload: dict) -> dict:
    """Cashfree refuses an order without customer details (400).

    The checkout has no login, so the order id doubles as the customer id: unique
    per order, and no real personal data leaves the machine. Sandbox-only values.
    """
    if "customer_details" in payload:
        return payload
    order_id = payload["order_id"]
    return {
        **payload,
        "customer_details": {
            "customer_id": order_id,
            "customer_name": "Guest Checkout",
            "customer_email": "guest@example.com",
            "customer_phone": "9999999999",
        },
    }
