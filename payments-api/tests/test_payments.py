def test_create_payment_returns_paid_order(client, pay):
    response = pay("order-0001")

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"].startswith("ORD-")
    assert body["status"] == "PAID"
    assert body["amount"] == 10.00
    assert body["currency"] == "INR"
    assert body["provider_order_id"].startswith("cf_")


def test_payment_is_readable_after_creation(client, pay):
    created = pay("order-0002").json()

    stored = client.get(f"/payments/{created['order_id']}")

    assert stored.status_code == 200
    assert stored.json()["order_id"] == created["order_id"]
    assert stored.json()["status"] == "PAID"


def test_unknown_payment_returns_404(client):
    response = client.get("/payments/ORD-000000")

    assert response.status_code == 404


def test_missing_idempotency_key_is_rejected(client):
    response = client.post("/payments", json={"amount": 10.00, "currency": "USD"})

    assert response.status_code == 422


def test_invalid_currency_is_rejected(client):
    response = client.post(
        "/payments",
        json={"amount": 10.00, "currency": "usd"},
        headers={"Idempotency-Key": "order-0003"},
    )

    assert response.status_code == 422


def test_non_positive_amount_is_rejected(client):
    response = client.post(
        "/payments",
        json={"amount": 0, "currency": "USD"},
        headers={"Idempotency-Key": "order-0004"},
    )

    assert response.status_code == 422


def test_provider_outage_returns_502_and_marks_payment_failed(client, pay, app, settings):
    async def unreachable(settings, payload):
        from app.cashfree import UpstreamError

        raise UpstreamError("connection reset")

    from app.cashfree import CashfreeClient
    from app.main import get_client

    app.dependency_overrides[get_client] = lambda: CashfreeClient(settings, transport=unreachable)

    response = pay("order-0005")

    assert response.status_code == 502
    order_id = response.json()["order_id"]
    assert client.get(f"/payments/{order_id}").json()["status"] == "FAILED"
