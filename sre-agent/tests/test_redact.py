"""Redaction is the boundary between tool output and the model's context."""

from sentinel.redact import MAX_OUTPUT_BYTES, redact

SECRET = "ghp_9f3c2b1a4d5e6f708192a3b4c5d6e7f80912"


def test_literal_secret_values_are_removed_even_without_a_keyword():
    text = f"connecting with {SECRET} now"

    assert SECRET not in redact(text, secrets=[SECRET])
    assert "[REDACTED]" in redact(text, secrets=[SECRET])


def test_key_value_secrets_are_removed():
    text = "\n".join(
        [
            "Authorization: Bearer abc123def456",
            "client_secret=cf_live_987654",
            "PASSWORD=hunter2",
            "api_key: sk-live-1111",
        ]
    )

    cleaned = redact(text)

    for leaked in ("abc123def456", "cf_live_987654", "hunter2", "sk-live-1111"):
        assert leaked not in cleaned
    assert cleaned.count("[REDACTED]") >= 4


def test_ordinary_log_text_survives():
    text = "POST /payments 500 KeyError: 'order_id' after 42ms"

    assert redact(text) == text


def test_output_is_capped_and_says_so():
    text = "x" * (MAX_OUTPUT_BYTES + 500)

    cleaned = redact(text)

    assert len(cleaned) <= MAX_OUTPUT_BYTES + 20
    assert cleaned.endswith("[truncated]")
