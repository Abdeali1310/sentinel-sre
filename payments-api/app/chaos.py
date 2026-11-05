"""Operator-controlled upstream degradation.

State lives in process memory and nowhere else: a restart is a guaranteed clean
slate, which is what makes post-deploy verification trustworthy. See
sre-agent/docs/adr/0002-in-memory-fault-trigger.md.
"""

import threading
import time
from dataclasses import dataclass

# Simulates a provider that renamed its response fields. The defect under test
# is that our code indexes the response instead of validating it.
CAMEL_CASE_KEYS = {
    "order_id": "orderId",
    "order_status": "orderStatus",
    "cf_order_id": "cfOrderId",
    "payment_session_id": "paymentSessionId",
    "order_amount": "orderAmount",
    "order_currency": "orderCurrency",
}


@dataclass
class _State:
    remaining: int = 0
    expires_at: float = 0.0


_lock = threading.Lock()
_state = _State()


def reset() -> None:
    global _state
    with _lock:
        _state = _State()


def _snapshot_locked() -> dict:
    active = _state.remaining > 0 and time.time() < _state.expires_at
    return {
        "active": active,
        "remaining": _state.remaining if active else 0,
        "expires_in_seconds": (max(0, int(_state.expires_at - time.time())) if active else 0),
    }


def enable(requests: int, ttl_seconds: int) -> dict:
    global _state
    with _lock:
        _state = _State(
            remaining=max(1, requests),
            expires_at=time.time() + max(1, ttl_seconds),
        )
        return _snapshot_locked()


def disable() -> dict:
    global _state
    with _lock:
        _state = _State()
        return _snapshot_locked()


def is_active() -> bool:
    with _lock:
        return _snapshot_locked()["active"]


def consume() -> bool:
    """Claim one degraded response. Returns True when this request is affected."""
    global _state
    with _lock:
        if not _snapshot_locked()["active"]:
            _state = _State()
            return False
        _state.remaining -= 1
        if _state.remaining <= 0:
            _state = _State()
        return True


def degrade(payload: dict) -> dict:
    return {CAMEL_CASE_KEYS.get(key, key): value for key, value in payload.items()}
