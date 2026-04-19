from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from app.json_storage import STORAGE_DB_PATH, load_json_file, save_json_file
from app.keyboards.inline import subscription_inline_keyboard
from app.texts import SUBSCRIPTION_REMINDER_TEXT_TEMPLATE

SUBSCRIPTION_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "subscriptions.json"
SUBSCRIPTIONS_TABLE = "subscriptions"
DEFAULT_SUBSCRIPTION_DAYS = 30
CHECK_INTERVAL_SECONDS = 1800
REMINDER_WINDOWS: tuple[tuple[int, timedelta, timedelta], ...] = (
    (7, timedelta(days=7), timedelta(days=3)),
    (3, timedelta(days=3), timedelta(days=1)),
    (1, timedelta(days=1), timedelta(seconds=0)),
)

_state_lock = Lock()


class SubscriptionRecord(TypedDict):
    expires_at: str
    reminders_sent: list[int]
    plan_name: str


SubscriptionState = dict[str, SubscriptionRecord]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _connect() -> sqlite3.Connection:
    STORAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STORAGE_DB_PATH, timeout=20)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SUBSCRIPTIONS_TABLE} (
            user_id TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL,
            reminders_sent_json TEXT NOT NULL,
            plan_name TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{SUBSCRIPTIONS_TABLE}_expires_at ON {SUBSCRIPTIONS_TABLE}(expires_at)"
    )
    return connection


def _encode_reminders(reminders_sent: list[int]) -> str:
    return json.dumps(sorted({int(item) for item in reminders_sent if isinstance(item, int)}), ensure_ascii=False)


def _decode_reminders(raw: Any) -> list[int]:
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = []
    elif isinstance(raw, list):
        parsed = raw
    else:
        parsed = []

    if not isinstance(parsed, list):
        return []
    return [int(item) for item in parsed if isinstance(item, int)]


def _row_to_record(row: tuple[Any, ...]) -> tuple[str, SubscriptionRecord]:
    user_id = str(row[0])
    return user_id, {
        "expires_at": str(row[1]),
        "reminders_sent": _decode_reminders(row[2]),
        "plan_name": str(row[3]) if isinstance(row[3], str) and row[3] else "Базовый",
    }


def _ensure_seeded() -> None:
    with _connect() as connection:
        existing = connection.execute(f"SELECT COUNT(*) FROM {SUBSCRIPTIONS_TABLE}").fetchone()
        if existing and int(existing[0]) > 0:
            return

        raw_data = load_json_file(SUBSCRIPTION_STORAGE_PATH, {})
        if not isinstance(raw_data, dict) or not raw_data:
            return

        for key, value in raw_data.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue

            expires_at = value.get("expires_at")
            reminders_sent = value.get("reminders_sent", [])
            plan_name = value.get("plan_name", "Базовый")
            if not isinstance(expires_at, str):
                continue

            connection.execute(
                f"""
                INSERT OR REPLACE INTO {SUBSCRIPTIONS_TABLE}
                (user_id, expires_at, reminders_sent_json, plan_name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    key,
                    expires_at,
                    _encode_reminders(reminders_sent if isinstance(reminders_sent, list) else []),
                    plan_name if isinstance(plan_name, str) and plan_name else "Базовый",
                ),
            )

        connection.commit()


def _load_state() -> SubscriptionState:
    _ensure_seeded()
    state: SubscriptionState = {}
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT user_id, expires_at, reminders_sent_json, plan_name FROM {SUBSCRIPTIONS_TABLE}"
        ).fetchall()

    for row in rows:
        user_key, record = _row_to_record(row)
        state[user_key] = record

    return state


def _save_state(state: SubscriptionState) -> None:
    with _connect() as connection:
        connection.execute(f"DELETE FROM {SUBSCRIPTIONS_TABLE}")
        for user_key, record in state.items():
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {SUBSCRIPTIONS_TABLE}
                (user_id, expires_at, reminders_sent_json, plan_name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_key,
                    str(record.get("expires_at") or _now_utc().isoformat()),
                    _encode_reminders(record.get("reminders_sent", [])),
                    str(record.get("plan_name") or "Базовый"),
                ),
            )
        connection.commit()

    save_json_file(SUBSCRIPTION_STORAGE_PATH, state)


def _parse_expires_at(expires_at: str) -> datetime:
    parsed = datetime.fromisoformat(expires_at)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_duration(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    if days > 0:
        if hours > 0:
            day_word = _plural_ru(days, "день", "дня", "дней")
            hour_word = _plural_ru(hours, "час", "часа", "часов")
            return f"{days} {day_word} {hours} {hour_word}"
        return f"{days} {_plural_ru(days, 'день', 'дня', 'дней')}"

    if hours > 0:
        return f"{hours} {_plural_ru(hours, 'час', 'часа', 'часов')}"

    if minutes > 0:
        return f"{minutes} {_plural_ru(minutes, 'минута', 'минуты', 'минут')}"

    return "меньше минуты"


def _plural_ru(value: int, one: str, few: str, many: str) -> str:
    value = abs(value) % 100
    last_digit = value % 10
    if 11 <= value <= 19:
        return many
    if last_digit == 1:
        return one
    if 2 <= last_digit <= 4:
        return few
    return many


def ensure_subscription(user_id: int, initial_days: int = DEFAULT_SUBSCRIPTION_DAYS) -> SubscriptionRecord:
    user_key = str(user_id)
    with _state_lock:
        state = _load_state()
        if user_key not in state:
            state[user_key] = {
                "expires_at": (_now_utc() + timedelta(days=initial_days)).isoformat(),
                "reminders_sent": [],
                "plan_name": "Базовый",
            }
            _save_state(state)
        return state[user_key]


def extend_subscription(user_id: int, days: int, plan_name: str | None = None) -> SubscriptionRecord:
    user_key = str(user_id)
    requested_plan_name = plan_name
    with _state_lock:
        state = _load_state()
        current = state.get(user_key)
        now = _now_utc()
        if current is None:
            base_expires_at = now
            reminders_sent: list[int] = []
            current_plan_name = "Базовый"
        else:
            base_expires_at = _parse_expires_at(current["expires_at"])
            reminders_sent = current.get("reminders_sent", [])
            current_plan_name = current.get("plan_name", "Базовый")

        resolved_plan_name = (
            current_plan_name if isinstance(current_plan_name, str) and current_plan_name else "Базовый"
        )
        if isinstance(requested_plan_name, str) and requested_plan_name.strip():
            resolved_plan_name = requested_plan_name.strip()

        if base_expires_at < now:
            base_expires_at = now

        state[user_key] = {
            "expires_at": (base_expires_at + timedelta(days=days)).isoformat(),
            "reminders_sent": reminders_sent,
            "plan_name": resolved_plan_name,
        }
        _save_state(state)
        return state[user_key]


def set_subscription_plan_name(user_id: int, plan_name: str) -> SubscriptionRecord | None:
    if not isinstance(plan_name, str) or not plan_name.strip():
        return None

    user_key = str(user_id)
    with _state_lock:
        state = _load_state()
        record = state.get(user_key)
        if record is None:
            return None

        record["plan_name"] = plan_name.strip()
        state[user_key] = record
        _save_state(state)
        return record


def delete_subscription(user_id: int) -> SubscriptionRecord | None:
    user_key = str(user_id)
    with _state_lock:
        state = _load_state()
        record = state.pop(user_key, None)
        if record is None:
            return None
        _save_state(state)
        return record


def get_remaining_time(user_id: int) -> timedelta | None:
    user_key = str(user_id)
    state = _load_state()
    record = state.get(user_key)
    if record is None:
        return None
    return _parse_expires_at(record["expires_at"]) - _now_utc()


def get_remaining_text(user_id: int) -> str:
    remaining = get_remaining_time(user_id)
    if remaining is None:
        return "неизвестно"
    return _format_duration(remaining)


def get_subscription_plan_name(user_id: int) -> str:
    state = _load_state()
    record = state.get(str(user_id))
    if record is None:
        return "Базовый"
    plan_name = record.get("plan_name", "Базовый")
    return plan_name if isinstance(plan_name, str) and plan_name else "Базовый"


def get_subscription_record(user_id: int) -> SubscriptionRecord | None:
    state = _load_state()
    record = state.get(str(user_id))
    if not isinstance(record, dict):
        return None
    return record


def is_subscription_active(user_id: int) -> bool:
    record = get_subscription_record(user_id)
    if record is None:
        return False

    try:
        return _parse_expires_at(record["expires_at"]) > _now_utc()
    except Exception:
        return False


def list_active_subscriptions() -> dict[int, SubscriptionRecord]:
    now = _now_utc()
    active: dict[int, SubscriptionRecord] = {}
    state = _load_state()

    for user_key, record in state.items():
        try:
            user_id = int(user_key)
            if _parse_expires_at(record["expires_at"]) <= now:
                continue
        except Exception:
            continue
        active[user_id] = record

    return active


def _build_reminder_candidates(state: SubscriptionState) -> list[tuple[int, int, timedelta]]:
    now = _now_utc()
    candidates: list[tuple[int, int, timedelta]] = []

    for user_key, record in state.items():
        try:
            user_id = int(user_key)
            expires_at = _parse_expires_at(record["expires_at"])
        except Exception:
            continue

        remaining = expires_at - now
        if remaining <= timedelta(seconds=0):
            continue

        sent_thresholds = set(record.get("reminders_sent", []))
        for threshold_days, upper_bound, lower_bound in REMINDER_WINDOWS:
            if threshold_days in sent_thresholds:
                continue
            if lower_bound < remaining <= upper_bound:
                candidates.append((user_id, threshold_days, remaining))
                break

    return candidates


def _mark_reminder_sent(state: SubscriptionState, user_id: int, threshold_days: int) -> None:
    user_key = str(user_id)
    record = state.get(user_key)
    if record is None:
        return

    reminders_sent = set(record.get("reminders_sent", []))
    reminders_sent.add(threshold_days)
    record["reminders_sent"] = sorted(reminders_sent, reverse=True)
    state[user_key] = record


async def send_subscription_reminders(bot) -> None:
    with _state_lock:
        state = _load_state()
        candidates = _build_reminder_candidates(state)

    if not candidates:
        return

    for user_id, threshold_days, remaining in candidates:
        remaining_text = _format_duration(remaining)
        plan_name = get_subscription_plan_name(user_id)
        message_text = SUBSCRIPTION_REMINDER_TEXT_TEMPLATE.format(
            remaining=remaining_text,
            plan_name=plan_name,
        )

        try:
            await bot.send_message(
                user_id,
                message_text,
                reply_markup=subscription_inline_keyboard(),
                disable_web_page_preview=True,
            )
        except Exception:
            logging.exception("Failed to send subscription reminder to user_id=%s", user_id)
            continue

        with _state_lock:
            fresh_state = _load_state()
            _mark_reminder_sent(fresh_state, user_id, threshold_days)
            _save_state(fresh_state)

        logging.info(
            "Sent subscription reminder to user_id=%s threshold_days=%s remaining=%s",
            user_id,
            threshold_days,
            remaining_text,
        )


async def reminder_loop(bot) -> None:
    while True:
        try:
            await send_subscription_reminders(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Subscription reminder loop failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
