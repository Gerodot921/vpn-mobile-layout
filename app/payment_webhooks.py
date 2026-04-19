from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from threading import Lock
from typing import Any, TypedDict

from app.json_storage import STORAGE_DB_PATH

PAYMENT_WEBHOOK_EVENTS_TABLE = "payment_webhook_events"

_state_lock = Lock()


class PaymentWebhookEvent(TypedDict):
    id: int
    provider: str
    event_type: str
    status: str
    order_id: str | None
    provider_invoice_id: str | None
    http_status: int
    message: str
    payload: dict[str, Any] | None
    created_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    STORAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STORAGE_DB_PATH, timeout=20)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {PAYMENT_WEBHOOK_EVENTS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            order_id TEXT,
            provider_invoice_id TEXT,
            http_status INTEGER NOT NULL,
            message TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{PAYMENT_WEBHOOK_EVENTS_TABLE}_provider_created_at ON {PAYMENT_WEBHOOK_EVENTS_TABLE}(provider, created_at DESC)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{PAYMENT_WEBHOOK_EVENTS_TABLE}_status_created_at ON {PAYMENT_WEBHOOK_EVENTS_TABLE}(status, created_at DESC)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{PAYMENT_WEBHOOK_EVENTS_TABLE}_order_id ON {PAYMENT_WEBHOOK_EVENTS_TABLE}(order_id)"
    )
    return connection


def _trim_message(value: str, limit: int = 300) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}..."


def log_payment_webhook_event(
    *,
    provider: str,
    event_type: str,
    status: str,
    http_status: int,
    message: str,
    order_id: str | None = None,
    provider_invoice_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    payload_json = None
    if isinstance(payload, dict):
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except Exception:
            payload_json = None

    with _state_lock:
        with _connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {PAYMENT_WEBHOOK_EVENTS_TABLE}
                (provider, event_type, status, order_id, provider_invoice_id, http_status, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider.strip().lower() or "unknown",
                    event_type.strip().lower() or "unknown",
                    status.strip().lower() or "unknown",
                    order_id.strip() if isinstance(order_id, str) and order_id.strip() else None,
                    provider_invoice_id.strip() if isinstance(provider_invoice_id, str) and provider_invoice_id.strip() else None,
                    int(http_status),
                    _trim_message(message or "-"),
                    payload_json,
                    _now_iso(),
                ),
            )
            connection.commit()


def list_recent_payment_webhook_events(
    *,
    limit: int = 20,
    provider: str | None = None,
    status: str | None = None,
) -> list[PaymentWebhookEvent]:
    safe_limit = min(max(int(limit), 1), 100)
    provider_filter = provider.strip().lower() if isinstance(provider, str) and provider.strip() else None
    status_filter = status.strip().lower() if isinstance(status, str) and status.strip() else None

    with _state_lock:
        with _connect() as connection:
            query = (
                f"SELECT id, provider, event_type, status, order_id, provider_invoice_id, http_status, message, payload_json, created_at "
                f"FROM {PAYMENT_WEBHOOK_EVENTS_TABLE}"
            )
            args: list[Any] = []
            where_parts: list[str] = []

            if provider_filter:
                where_parts.append("provider = ?")
                args.append(provider_filter)
            if status_filter:
                where_parts.append("status = ?")
                args.append(status_filter)

            if where_parts:
                query += " WHERE " + " AND ".join(where_parts)

            query += " ORDER BY id DESC LIMIT ?"
            args.append(safe_limit)
            rows = connection.execute(query, tuple(args)).fetchall()

    events: list[PaymentWebhookEvent] = []
    for row in rows:
        payload_raw = row[8]
        parsed_payload = None
        if isinstance(payload_raw, str) and payload_raw:
            try:
                maybe_dict = json.loads(payload_raw)
                if isinstance(maybe_dict, dict):
                    parsed_payload = maybe_dict
            except Exception:
                parsed_payload = None

        events.append(
            {
                "id": int(row[0]),
                "provider": str(row[1]),
                "event_type": str(row[2]),
                "status": str(row[3]),
                "order_id": str(row[4]) if row[4] is not None else None,
                "provider_invoice_id": str(row[5]) if row[5] is not None else None,
                "http_status": int(row[6]),
                "message": str(row[7]),
                "payload": parsed_payload,
                "created_at": str(row[9]),
            }
        )

    return events


def get_payment_webhook_status_summary(*, provider: str | None = None) -> dict[str, int]:
    provider_filter = provider.strip().lower() if isinstance(provider, str) and provider.strip() else None

    with _state_lock:
        with _connect() as connection:
            if provider_filter:
                rows = connection.execute(
                    f"SELECT status, COUNT(*) FROM {PAYMENT_WEBHOOK_EVENTS_TABLE} WHERE provider = ? GROUP BY status",
                    (provider_filter,),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"SELECT status, COUNT(*) FROM {PAYMENT_WEBHOOK_EVENTS_TABLE} GROUP BY status"
                ).fetchall()

    summary: dict[str, int] = {}
    for row in rows:
        status = str(row[0]) if row[0] is not None else "unknown"
        summary[status] = int(row[1])

    return summary
