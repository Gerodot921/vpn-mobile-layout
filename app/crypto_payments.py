from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from app.json_storage import load_json_file, save_json_file

CRYPTO_ORDERS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "crypto_orders.json"

_state_lock = Lock()


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


def _load_state() -> CryptoOrdersState:
    raw = load_json_file(CRYPTO_ORDERS_STORAGE_PATH, {})
    if not isinstance(raw, dict):
        return {}

    state: CryptoOrdersState = {}
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

        state[order_id] = {
            "order_id": order_id,
            "provider": str(item.get("provider") or "cryptocloud"),
            "user_id": user_id,
            "plan_code": str(item.get("plan_code") or "basic"),
            "plan_name": str(item.get("plan_name") or "Базовый"),
            "days": days,
            "amount_rub": float(amount_rub),
            "status": str(item.get("status") or "pending"),
            "provider_invoice_id": str(item.get("provider_invoice_id")) if item.get("provider_invoice_id") else None,
            "invoice_url": str(item.get("invoice_url")) if item.get("invoice_url") else None,
            "created_at": str(item.get("created_at") or _now_iso()),
            "paid_at": str(item.get("paid_at")) if item.get("paid_at") else None,
            "last_payload": item.get("last_payload") if isinstance(item.get("last_payload"), dict) else None,
        }

    return state


def _save_state(state: CryptoOrdersState) -> None:
    save_json_file(CRYPTO_ORDERS_STORAGE_PATH, state)


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
        state = _load_state()
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
        state[order_id] = record
        _save_state(state)
        return record


def get_order_by_id(order_id: str) -> CryptoOrderRecord | None:
    with _state_lock:
        state = _load_state()
        return state.get(order_id)


def get_order_by_provider_invoice_id(provider_invoice_id: str) -> CryptoOrderRecord | None:
    with _state_lock:
        state = _load_state()
        for record in state.values():
            if record.get("provider_invoice_id") == provider_invoice_id:
                return record
        return None


def mark_order_paid(order_id: str, payload: dict[str, Any] | None = None) -> tuple[CryptoOrderRecord | None, bool]:
    with _state_lock:
        state = _load_state()
        record = state.get(order_id)
        if record is None:
            return None, False

        if record.get("status") == "paid":
            return record, False

        record["status"] = "paid"
        record["paid_at"] = _now_iso()
        record["last_payload"] = payload if isinstance(payload, dict) else None
        state[order_id] = record
        _save_state(state)
        return record, True