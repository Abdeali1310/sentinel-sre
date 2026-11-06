"""R7.2: nothing leaves a tool unredacted or larger than the cap."""

import re

MAX_OUTPUT_BYTES = 20_000

_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}")
_KEY_VALUE = re.compile(
    r"(?i)\b(client_secret|api[_-]?key|access[_-]?token|token|password|secret)\b"
    r"\s*[:=]\s*[^\s,;\"']+"
)
_MIN_SECRET_LENGTH = 8


def redact(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret and len(secret) >= _MIN_SECRET_LENGTH:
            text = text.replace(secret, "[REDACTED]")

    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _KEY_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)

    if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        text = text[: MAX_OUTPUT_BYTES - 16] + "\n[truncated]"
    return text
