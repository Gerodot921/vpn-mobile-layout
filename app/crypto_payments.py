from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from app.json_storage import STORAGE_DB_PATH, load_json_file

CRYPTO_ORDERS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "crypto_orders.json"
CRYPTO_ORDERS_TABLE = "crypto_orders"

_state_lock = Lock()
_seed_checked = False


class CryptoOrderRecord(TypedDict):
    order_id: str
    provider: str
    user_id: int
    plan_code: str
    plan_name: str
    days: int
    amount_rub: float
    status: str
    provider_invoice_id: str | None
    invoice_url: str | None
    created_at: str
    paid_at: str | None
    last_payload: dict[str, Any] | None


CryptoOrdersState = dict[str, CryptoOrderRecord]


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
        CREATE TABLE IF NOT EXISTS {CRYPTO_ORDERS_TABLE} (
            order_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            plan_code TEXT NOT NULL,
            plan_name TEXT NOT NULL,
            days INTEGER NOT NULL,
            amount_rub REAL NOT NULL,
            status TEXT NOT NULL,
            provider_invoice_id TEXT,
            invoice_url TEXT,
            created_at TEXT NOT NULL,
            paid_at TEXT,
            last_payload_json TEXT
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{CRYPTO_ORDERS_TABLE}_provider_invoice_id ON {CRYPTO_ORDERS_TABLE}(provider_invoice_id)"
    )
    return connection


def _row_to_record(row: sqlite3.Row | tuple[Any, ...]) -> CryptoOrderRecord:
    payload_raw = row[12]
    last_payload = None
    if isinstance(payload_raw, str) and payload_raw:
        try:
            parsed_payload = json.loads(payload_raw)
            if isinstance(parsed_payload, dict):
                last_payload = parsed_payload
        except Exception:
            last_payload = None

    return {
        "order_id": str(row[0]),
        "provider": str(row[1]),
        "user_id": int(row[2]),
        "plan_code": str(row[3]),
        "plan_name": str(row[4]),
        "days": int(row[5]),
        "amount_rub": float(row[6]),
        "status": str(row[7]),
        "provider_invoice_id": str(row[8]) if row[8] is not None else None,
        "invoice_url": str(row[9]) if row[9] is not None else None,
        "created_at": str(row[10]),
        "paid_at": str(row[11]) if row[11] is not None else None,
        "last_payload": last_payload,
    }


def _ensure_seeded() -> None:
    global _seed_checked
    if _seed_checked:
        return

    with _connect() as connection:
        existing = connection.execute(f"SELECT COUNT(*) FROM {CRYPTO_ORDERS_TABLE}").fetchone()
        if existing and int(existing[0]) > 0:
            _seed_checked = True
            return

        raw = load_json_file(CRYPTO_ORDERS_STORAGE_PATH, {})
        if not isinstance(raw, dict) or not raw:
            return

        for order_id, item in raw.items():
            if not isinstance(order_id, str) or not isinstance(item, dict):
                continue

            user_id = item.get("user_id")
            days = item.get("days")
            amount_rub = item.get("amount_rub")
            if not isinstance(user_id, int) or not isinstance(days, int):
                continue
            if not isinstance(amount_rub, (int, float)):
                continue

            connection.execute(
                f"""
                INSERT OR REPLACE INTO {CRYPTO_ORDERS_TABLE}
                (order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status, provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    str(item.get("provider") or "cryptocloud"),
                    user_id,
                    str(item.get("plan_code") or "basic"),
                    str(item.get("plan_name") or "Базовый"),
                    days,
                    float(amount_rub),
                    str(item.get("status") or "pending"),
                    str(item.get("provider_invoice_id")) if item.get("provider_invoice_id") else None,
                    str(item.get("invoice_url")) if item.get("invoice_url") else None,
                    str(item.get("created_at") or _now_iso()),
                    str(item.get("paid_at")) if item.get("paid_at") else None,
                    json.dumps(item.get("last_payload"), ensure_ascii=False, sort_keys=True)
                    if isinstance(item.get("last_payload"), dict)
                    else None,
                ),
            )

        connection.commit()
    _seed_checked = True


def _load_state() -> CryptoOrdersState:
    _ensure_seeded()
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status, provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json FROM {CRYPTO_ORDERS_TABLE}"
        ).fetchall()

    state: CryptoOrdersState = {}
    for row in rows:
        record = _row_to_record(row)
        state[record["order_id"]] = record
    return state


def create_crypto_order(
    *,
    order_id: str,
    user_id: int,
    plan_code: str,
    plan_name: str,
    days: int,
    amount_rub: float,
    provider_invoice_id: str | None,
    invoice_url: str | None,
) -> CryptoOrderRecord:
    with _state_lock:
        record: CryptoOrderRecord = {
            "order_id": order_id,
            "provider": "cryptocloud",
            "user_id": user_id,
            "plan_code": plan_code,
            "plan_name": plan_name,
            "days": days,
            "amount_rub": float(amount_rub),
            "status": "pending",
            "provider_invoice_id": provider_invoice_id,
            "invoice_url": invoice_url,
            "created_at": _now_iso(),
            "paid_at": None,
            "last_payload": None,
        }
        _ensure_seeded()
        with _connect() as connection:
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {CRYPTO_ORDERS_TABLE}
                (order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status, provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["order_id"],
                    record["provider"],
                    record["user_id"],
                    record["plan_code"],
                    record["plan_name"],
                    record["days"],
                    record["amount_rub"],
                    record["status"],
                    record["provider_invoice_id"],
                    record["invoice_url"],
                    record["created_at"],
                    record["paid_at"],
                    None,
                ),
            )
            connection.commit()
        return record


def get_order_by_id(order_id: str) -> CryptoOrderRecord | None:
    with _state_lock:
        _ensure_seeded()
        with _connect() as connection:
            row = connection.execute(
                f"SELECT order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status, provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json FROM {CRYPTO_ORDERS_TABLE} WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        return _row_to_record(row) if row is not None else None


def get_order_by_provider_invoice_id(provider_invoice_id: str) -> CryptoOrderRecord | None:
    with _state_lock:
        _ensure_seeded()
        with _connect() as connection:
            row = connection.execute(
                f"SELECT order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status, provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json FROM {CRYPTO_ORDERS_TABLE} WHERE provider_invoice_id = ?",
                (provider_invoice_id,),
            ).fetchone()
        return _row_to_record(row) if row is not None else None


def mark_order_paid(order_id: str, payload: dict[str, Any] | None = None) -> tuple[CryptoOrderRecord | None, bool]:
    with _state_lock:
        _ensure_seeded()
        with _connect() as connection:
            row = connection.execute(
                f"SELECT order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status, provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json FROM {CRYPTO_ORDERS_TABLE} WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if row is None:
                return None, False

            record = _row_to_record(row)
            if record.get("status") == "paid":
                return record, False

            payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True) if isinstance(payload, dict) else None
            paid_at = _now_iso()
            connection.execute(
                f"UPDATE {CRYPTO_ORDERS_TABLE} SET status = ?, paid_at = ?, last_payload_json = ? WHERE order_id = ?",
                ("paid", paid_at, payload_json, order_id),
            )
            connection.commit()
            record["status"] = "paid"
            record["paid_at"] = paid_at
            record["last_payload"] = payload if isinstance(payload, dict) else None
            return record, True


def list_recent_orders(limit: int = 20, status: str | None = None) -> list[CryptoOrderRecord]:
    safe_limit = min(max(int(limit), 1), 100)
    status_filter = status.strip().lower() if isinstance(status, str) and status.strip() else None
    with _state_lock:
        _ensure_seeded()
        with _connect() as connection:
            if status_filter:
                rows = connection.execute(
                    f"""
                    SELECT order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status,
                           provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json
                    FROM {CRYPTO_ORDERS_TABLE}
                    WHERE lower(status) = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status_filter, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT order_id, provider, user_id, plan_code, plan_name, days, amount_rub, status,
                           provider_invoice_id, invoice_url, created_at, paid_at, last_payload_json
                    FROM {CRYPTO_ORDERS_TABLE}
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()

    return [_row_to_record(row) for row in rows]