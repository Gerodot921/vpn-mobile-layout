from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import TypedDict

from app.json_storage import load_json_file, save_json_file

FREE_ACCESS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "free_access.json"
DEFAULT_FREE_ACCESS_HOURS = 2

_state_lock = Lock()


class FreeAccessRecord(TypedDict):
    access_key: str
    granted_at: str
    expires_at: str
    claims_count: int
    source: str


FreeAccessState = dict[str, FreeAccessRecord]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_state() -> FreeAccessState:
    raw_data = load_json_file(FREE_ACCESS_STORAGE_PATH, {})
    if not isinstance(raw_data, dict):
        return {}

    state: FreeAccessState = {}
    for key, value in raw_data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue

        access_key = value.get("access_key")
        granted_at = value.get("granted_at")
        expires_at = value.get("expires_at")
        claims_count = value.get("claims_count", 0)
        source = value.get("source", "mini_app_ad")

        if not isinstance(access_key, str) or not isinstance(granted_at, str) or not isinstance(expires_at, str):
            continue

        if not isinstance(claims_count, int):
            claims_count = 0

        state[key] = {
            "access_key": access_key,
            "granted_at": granted_at,
            "expires_at": expires_at,
            "claims_count": claims_count,
            "source": source if isinstance(source, str) and source else "mini_app_ad",
        }

    return state


def _save_state(state: FreeAccessState) -> None:
    save_json_file(FREE_ACCESS_STORAGE_PATH, state)


def _new_key() -> str:
    return f"SKULL-{secrets.token_urlsafe(8).upper()}"


def _user_key(user_id: int) -> str:
    return str(user_id)


def get_free_access_record(user_id: int) -> FreeAccessRecord | None:
    with _state_lock:
        state = _load_state()
        return state.get(_user_key(user_id))


def is_free_access_active(user_id: int) -> bool:
    record = get_free_access_record(user_id)
    if record is None:
        return False

    try:
        return _parse_dt(record["expires_at"]) > _now_utc()
    except Exception:
        return False


def get_free_access_remaining(user_id: int) -> timedelta | None:
    record = get_free_access_record(user_id)
    if record is None:
        return None

    try:
        return _parse_dt(record["expires_at"]) - _now_utc()
    except Exception:
        return None


def format_free_access_remaining_text(user_id: int) -> str:
    remaining = get_free_access_remaining(user_id)
    if remaining is None:
        return "неизвестно"

    total_seconds = max(int(remaining.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60

    if hours > 0:
        if minutes > 0:
            return f"{hours} ч {minutes} мин"
        return f"{hours} ч"

    if minutes > 0:
        return f"{minutes} мин"

    return "меньше минуты"


def grant_free_access(
    user_id: int,
    hours: int = DEFAULT_FREE_ACCESS_HOURS,
    source: str = "mini_app_ad",
) -> tuple[FreeAccessRecord, bool]:
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        now = _now_utc()
        current = state.get(user_key)

        if current is not None:
            try:
                if _parse_dt(current["expires_at"]) > now:
                    return current, False
            except Exception:
                pass

        new_record: FreeAccessRecord = {
            "access_key": _new_key(),
            "granted_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=hours)).isoformat(),
            "claims_count": (current.get("claims_count", 0) if current else 0) + 1,
            "source": source,
        }
        state[user_key] = new_record
        _save_state(state)
        return new_record, True