def test_checkout_page_shows_the_amount_and_pay_button(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "\u20b910.00" in response.text
    assert "Pay now" in response.text


def test_checkout_page_has_no_provider_or_debug_detail(client):
    html = client.get("/").text

    for leaked in ("cashfree", "Cashfree", "Traceback", "client_secret"):
        assert leaked not in html


def test_checkout_page_is_accessible(client):
    html = client.get("/").text

    assert 'aria-live="polite"' in html
    assert 'role="alert"' in html
    assert 'lang="en"' in html
