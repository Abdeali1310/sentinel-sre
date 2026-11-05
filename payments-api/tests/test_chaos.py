CHAOS_TOKEN = "test-chaos-token"


def test_chaos_requires_a_token(client):
    response = client.post("/admin/chaos", json={"requests": 5, "ttl_seconds": 60})

    assert response.status_code == 401


def test_chaos_rejects_a_wrong_token(client):
    response = client.post(
        "/admin/chaos",
        json={"requests": 5, "ttl_seconds": 60},
        headers={"X-Chaos-Token": "not-the-token"},
    )

    assert response.status_code == 401


def test_chaos_enables_and_delete_clears(client, enable_chaos):
    state = enable_chaos(requests=5, ttl_seconds=60)
    assert state["active"] is True
    assert state["remaining"] == 5

    cleared = client.delete("/admin/chaos", headers={"X-Chaos-Token": CHAOS_TOKEN})

    assert cleared.status_code == 200
    assert cleared.json()["active"] is False


def test_chaos_budget_is_consumed_by_requests(client, enable_chaos, pay):
    """One degraded request, then normal service: the trigger is bounded."""
    enable_chaos(requests=1, ttl_seconds=600)

    degraded = pay("chaos-budget-1")
    recovered = pay("chaos-budget-2")

    assert degraded.status_code >= 500
    assert recovered.status_code == 200


def test_chaos_is_off_by_default(client, pay):
    assert pay("chaos-default-1").status_code == 200
