"""Upstream response contract.

The provider's payload is untrusted input. This module pins the behaviour we
require when it stops matching what we expect.
"""

import json


def test_malformed_upstream_response_returns_502_and_marks_payment_failed(client, enable_chaos):
    """A camelCase provider payload must be rejected at the boundary.

    Accepting it silently would be worse than failing: the payment row would
    claim success while no order exists upstream.
    """
    enable_chaos(requests=10, ttl_seconds=600)

    response = client.post(
        "/payments",
        json={"amount": 10.00, "currency": "USD"},
        headers={"Idempotency-Key": "shape-0001"},
    )

    # 502: "the provider said something we cannot accept". Not 500: that would
    # mean we have an unhandled defect, and the operator would be told to look
    # in the wrong place.
    assert response.status_code == 502

    body = response.json()
    assert body["order_id"].startswith("ORD-")
    assert "camelCase" not in json.dumps(body)
    assert "orderId" not in json.dumps(body)
    assert "Traceback" not in json.dumps(body)

    # The payment must be parked as FAILED and never counted as revenue.
    stored = client.get(f"/payments/{body['order_id']}")
    assert stored.status_code == 200
    assert stored.json()["status"] == "FAILED"
    assert stored.json()["error"] == "upstream_contract"


def test_malformed_upstream_does_not_leak_provider_internals(client, enable_chaos):
    """The customer-facing body carries an order id and nothing else."""
    enable_chaos(requests=10, ttl_seconds=600)

    response = client.post(
        "/payments",
        json={"amount": 10.00, "currency": "USD"},
        headers={"Idempotency-Key": "shape-0002"},
    )

    body = response.json()
    assert set(body) <= {"error", "message", "order_id"}
    assert response.headers["content-type"].startswith("application/json")
