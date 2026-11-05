def test_repeating_an_idempotency_key_returns_the_same_payment(client, pay):
    first = pay("repeat-0001").json()
    second = pay("repeat-0001").json()

    assert first["order_id"] == second["order_id"]


def test_repeating_an_idempotency_key_does_not_call_the_provider_again(client, pay, transport):
    pay("repeat-0002")
    pay("repeat-0002")

    assert len(transport.calls) == 1


def test_distinct_keys_create_distinct_payments(client, pay):
    first = pay("repeat-0003").json()
    second = pay("repeat-0004").json()

    assert first["order_id"] != second["order_id"]
