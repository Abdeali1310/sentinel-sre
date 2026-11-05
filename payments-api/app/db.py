"""SQLite persistence.

One table, four operations. Deliberately not an ORM: the incident story does not
need one, and a plain query is what the agent will read in `fetch_logs`.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id          TEXT    NOT NULL UNIQUE,
    idempotency_key   TEXT    NOT NULL UNIQUE,
    amount            REAL    NOT NULL,
    currency          TEXT    NOT NULL,
    status            TEXT    NOT NULL CHECK (status IN ('CREATED', 'PAID', 'FAILED')),
    provider_order_id TEXT,
    error             TEXT,
    created_at        TEXT    NOT NULL
);
"""


def _path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite:/// URLs are supported")
    return database_url[len(prefix) :]


@contextmanager
def connect(database_url: str) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_path(database_url))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(database_url: str) -> None:
    with connect(database_url) as connection:
        connection.executescript(SCHEMA)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def insert_payment(
    database_url: str,
    *,
    order_id: str,
    idempotency_key: str,
    amount: float,
    currency: str,
) -> None:
    with connect(database_url) as connection:
        connection.execute(
            "INSERT INTO payments"
            " (order_id, idempotency_key, amount, currency, status, created_at)"
            " VALUES (?, ?, ?, ?, 'CREATED', ?)",
            (order_id, idempotency_key, amount, currency, _utc_now()),
        )


def get_by_idempotency(database_url: str, key: str) -> dict | None:
    with connect(database_url) as connection:
        row = connection.execute(
            "SELECT * FROM payments WHERE idempotency_key = ?", (key,)
        ).fetchone()
    return dict(row) if row else None


def get_by_order_id(database_url: str, order_id: str) -> dict | None:
    with connect(database_url) as connection:
        row = connection.execute(
            "SELECT * FROM payments WHERE order_id = ?", (order_id,)
        ).fetchone()
    return dict(row) if row else None


def mark_paid(database_url: str, order_id: str, provider_order_id: str) -> None:
    with connect(database_url) as connection:
        connection.execute(
            "UPDATE payments SET status = 'PAID', provider_order_id = ?, error = NULL"
            " WHERE order_id = ?",
            (provider_order_id, order_id),
        )


def mark_failed(database_url: str, order_id: str, error: str) -> None:
    with connect(database_url) as connection:
        connection.execute(
            "UPDATE payments SET status = 'FAILED', error = ? WHERE order_id = ?",
            (error, order_id),
        )
