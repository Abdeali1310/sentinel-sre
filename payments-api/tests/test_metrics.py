def test_metrics_expose_request_counter(client):
    client.get("/healthz")

    text = client.get("/metrics").text

    assert "payments_http_requests_total{" in text
    assert 'status_code="200"' in text


def test_metrics_label_routes_not_raw_paths(client, pay):
    created = pay("metrics-0001").json()
    client.get(f"/payments/{created['order_id']}")

    text = client.get("/metrics").text

    # Labelling by concrete order id would grow without bound.
    assert f'path="/payments/{created["order_id"]}"' not in text
    assert 'path="/payments/{order_id}"' in text


def test_metrics_expose_duration_histogram(client):
    client.get("/healthz")

    text = client.get("/metrics").text

    assert "payments_request_duration_seconds_bucket" in text
