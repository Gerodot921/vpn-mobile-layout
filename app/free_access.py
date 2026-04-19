from __future__ import annotations

import asyncio
import logging
import os
import json
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from app.json_storage import STORAGE_DB_PATH, load_json_file, save_json_file
from app.wireguard import ensure_wireguard_profile, get_wireguard_config_filename, remove_peer_from_server, reset_wireguard_profile

FREE_ACCESS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "free_access.json"
FREE_ACCESS_STATS_PATH = Path(__file__).resolve().parents[1] / "data" / "free_access_stats.json"
FREE_ACCESS_TABLE = "free_access"
FREE_ACCESS_STATS_TABLE = "free_access_stats"
DEFAULT_FREE_ACCESS_HOURS = 1
FREE_ACCESS_CLEANUP_INTERVAL_SECONDS = 60
FREE_ACCESS_REMINDER_THRESHOLDS = (10, 5, 1)

_state_lock = Lock()


class FreeAccessRecord(TypedDict):
    access_key: str
    granted_at: str
    expires_at: str
    claims_count: int
    reminder_thresholds_sent: list[int]
    source: str
    vpn_protocol: str
    vpn_profile_name: str
    vpn_config_name: str
    vpn_configured: bool
    peer_public_key: str
    peer_added_to_server: bool


FreeAccessState = dict[str, FreeAccessRecord]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _connect() -> sqlite3.Connection:
    STORAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STORAGE_DB_PATH, timeout=20)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FREE_ACCESS_TABLE} (
            user_id TEXT PRIMARY KEY,
            access_key TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            claims_count INTEGER NOT NULL,
            reminder_thresholds_sent_json TEXT NOT NULL,
            source TEXT NOT NULL,
            vpn_protocol TEXT NOT NULL,
            vpn_profile_name TEXT NOT NULL,
            vpn_config_name TEXT NOT NULL,
            vpn_configured INTEGER NOT NULL,
            peer_public_key TEXT NOT NULL,
            peer_added_to_server INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{FREE_ACCESS_TABLE}_expires_at ON {FREE_ACCESS_TABLE}(expires_at)"
    )
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {FREE_ACCESS_STATS_TABLE} (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_claims INTEGER NOT NULL,
            unique_users INTEGER NOT NULL,
            claimed_user_ids_json TEXT NOT NULL
        )
        """
    )
    return connection


def _encode_int_list(items: list[int]) -> str:
    return json.dumps(sorted({int(item) for item in items if isinstance(item, int)}), ensure_ascii=False)


def _decode_int_list(raw: Any) -> list[int]:
    parsed: Any
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


def _row_to_record(row: tuple[Any, ...]) -> tuple[str, FreeAccessRecord]:
    user_key = str(row[0])
    return user_key, {
        "access_key": str(row[1]),
        "granted_at": str(row[2]),
        "expires_at": str(row[3]),
        "claims_count": int(row[4]),
        "reminder_thresholds_sent": _decode_int_list(row[5]),
        "source": str(row[6]),
        "vpn_protocol": str(row[7]),
        "vpn_profile_name": str(row[8]),
        "vpn_config_name": str(row[9]),
        "vpn_configured": bool(row[10]),
        "peer_public_key": str(row[11]),
        "peer_added_to_server": bool(row[12]),
    }


def _row_to_stats(row: tuple[Any, ...] | None) -> dict[str, object]:
    if row is None:
        return {"total_claims": 0, "unique_users": 0, "claimed_user_ids": []}

    return {
        "total_claims": int(row[0]),
        "unique_users": int(row[1]),
        "claimed_user_ids": _decode_int_list(row[2]),
    }


def _ensure_seeded() -> None:
    with _connect() as connection:
        existing = connection.execute(f"SELECT COUNT(*) FROM {FREE_ACCESS_TABLE}").fetchone()
        if existing and int(existing[0]) > 0:
            return

        raw_data = load_json_file(FREE_ACCESS_STORAGE_PATH, {})
        if isinstance(raw_data, dict) and raw_data:
            for key, value in raw_data.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue

                access_key = value.get("access_key")
                granted_at = value.get("granted_at")
                expires_at = value.get("expires_at")
                if not isinstance(access_key, str) or not isinstance(granted_at, str) or not isinstance(expires_at, str):
                    continue

                connection.execute(
                    f"""
                    INSERT OR REPLACE INTO {FREE_ACCESS_TABLE}
                    (user_id, access_key, granted_at, expires_at, claims_count, reminder_thresholds_sent_json, source, vpn_protocol, vpn_profile_name, vpn_config_name, vpn_configured, peer_public_key, peer_added_to_server)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        access_key,
                        granted_at,
                        expires_at,
                        int(value.get("claims_count", 0)) if isinstance(value.get("claims_count", 0), int) else 0,
                        _encode_int_list(value.get("reminder_thresholds_sent", []) if isinstance(value.get("reminder_thresholds_sent", []), list) else []),
                        str(value.get("source") or "mini_app_ad"),
                        str(value.get("vpn_protocol") or "WireGuard"),
                        str(value.get("vpn_profile_name") or access_key),
                        str(value.get("vpn_config_name") or f"skull-vpn-{access_key}.conf"),
                        1 if bool(value.get("vpn_configured", False)) else 0,
                        str(value.get("peer_public_key") or ""),
                        1 if bool(value.get("peer_added_to_server", False)) else 0,
                    ),
                )

        stats_raw = load_json_file(FREE_ACCESS_STATS_PATH, {})
        if isinstance(stats_raw, dict) and stats_raw:
            claimed_user_ids = stats_raw.get("claimed_user_ids", [])
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {FREE_ACCESS_STATS_TABLE}
                (id, total_claims, unique_users, claimed_user_ids_json)
                VALUES (1, ?, ?, ?)
                """,
                (
                    int(stats_raw.get("total_claims", 0)) if isinstance(stats_raw.get("total_claims", 0), int) else 0,
                    int(stats_raw.get("unique_users", 0)) if isinstance(stats_raw.get("unique_users", 0), int) else 0,
                    _encode_int_list(
                        [int(item) for item in claimed_user_ids if isinstance(item, int) or (isinstance(item, str) and item.isdigit())]
                    ),
                ),
            )

        connection.commit()


def _load_state() -> FreeAccessState:
    _ensure_seeded()
    state: FreeAccessState = {}
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT user_id, access_key, granted_at, expires_at, claims_count, reminder_thresholds_sent_json, source, vpn_protocol, vpn_profile_name, vpn_config_name, vpn_configured, peer_public_key, peer_added_to_server FROM {FREE_ACCESS_TABLE}"
        ).fetchall()

    for row in rows:
        user_key, record = _row_to_record(row)
        state[user_key] = record

    return state


def _save_state(state: FreeAccessState) -> None:
    with _connect() as connection:
        connection.execute(f"DELETE FROM {FREE_ACCESS_TABLE}")
        for user_key, record in state.items():
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {FREE_ACCESS_TABLE}
                (user_id, access_key, granted_at, expires_at, claims_count, reminder_thresholds_sent_json, source, vpn_protocol, vpn_profile_name, vpn_config_name, vpn_configured, peer_public_key, peer_added_to_server)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_key,
                    str(record.get("access_key") or ""),
                    str(record.get("granted_at") or _now_utc().isoformat()),
                    str(record.get("expires_at") or _now_utc().isoformat()),
                    int(record.get("claims_count", 0)) if isinstance(record.get("claims_count", 0), int) else 0,
                    _encode_int_list(record.get("reminder_thresholds_sent", []) if isinstance(record.get("reminder_thresholds_sent", []), list) else []),
                    str(record.get("source") or "mini_app_ad"),
                    str(record.get("vpn_protocol") or "WireGuard"),
                    str(record.get("vpn_profile_name") or record.get("access_key") or ""),
                    str(record.get("vpn_config_name") or f"skull-vpn-{record.get('access_key', 'access')}.conf"),
                    1 if bool(record.get("vpn_configured", False)) else 0,
                    str(record.get("peer_public_key") or ""),
                    1 if bool(record.get("peer_added_to_server", False)) else 0,
                ),
            )
        connection.commit()

    save_json_file(FREE_ACCESS_STORAGE_PATH, state)


def _load_stats() -> dict[str, object]:
    _ensure_seeded()
    with _connect() as connection:
        row = connection.execute(
            f"SELECT total_claims, unique_users, claimed_user_ids_json FROM {FREE_ACCESS_STATS_TABLE} WHERE id = 1"
        ).fetchone()

    return _row_to_stats(row)


def _save_stats(stats: dict[str, object]) -> None:
    total_claims = int(stats.get("total_claims", 0)) if isinstance(stats.get("total_claims", 0), int) else 0
    unique_users = int(stats.get("unique_users", 0)) if isinstance(stats.get("unique_users", 0), int) else 0
    claimed_user_ids = stats.get("claimed_user_ids", [])
    claimed_ids = [int(item) for item in claimed_user_ids if isinstance(item, int) or (isinstance(item, str) and item.isdigit())]

    with _connect() as connection:
        connection.execute(
            f"""
            INSERT OR REPLACE INTO {FREE_ACCESS_STATS_TABLE}
            (id, total_claims, unique_users, claimed_user_ids_json)
            VALUES (1, ?, ?, ?)
            """,
            (
                total_claims,
                unique_users,
                _encode_int_list(claimed_ids),
            ),
        )
        connection.commit()

    save_json_file(FREE_ACCESS_STATS_PATH, {
        "total_claims": total_claims,
        "unique_users": unique_users,
        "claimed_user_ids": [str(item) for item in claimed_ids],
    })


def _new_key() -> str:
    return f"SKULL-{secrets.token_urlsafe(8).upper()}"


def _user_key(user_id: int) -> str:
    return str(user_id)


def _configured_free_access_hours() -> int:
    raw_value = os.getenv("FREE_ACCESS_HOURS", str(DEFAULT_FREE_ACCESS_HOURS)).strip()
    try:
        hours = int(raw_value)
    except Exception:
        hours = DEFAULT_FREE_ACCESS_HOURS
    return min(max(hours, 1), 168)


def _configured_cleanup_interval_seconds() -> int:
    raw_value = os.getenv("FREE_ACCESS_CLEANUP_INTERVAL_SECONDS", str(FREE_ACCESS_CLEANUP_INTERVAL_SECONDS)).strip()
    try:
        seconds = int(raw_value)
    except Exception:
        seconds = FREE_ACCESS_CLEANUP_INTERVAL_SECONDS
    return min(max(seconds, 10), 3600)


def get_free_access_record(user_id: int) -> FreeAccessRecord | None:
    with _state_lock:
        state = _load_state()
        return state.get(_user_key(user_id))


def get_total_free_claims() -> int:
    with _state_lock:
        stats = _load_stats()
        return int(stats.get("total_claims", 0))


def get_total_free_users() -> int:
    with _state_lock:
        stats = _load_stats()
        return int(stats.get("unique_users", 0))


def list_active_free_access_records() -> dict[int, FreeAccessRecord]:
    now = _now_utc()
    active: dict[int, FreeAccessRecord] = {}
    with _state_lock:
        state = _load_state()

    for user_key, record in state.items():
        try:
            user_id = int(user_key)
            if _parse_dt(record["expires_at"]) <= now:
                continue
        except Exception:
            continue
        active[user_id] = record

    return active


def mark_free_access_peer_added(user_id: int) -> bool:
    """Mark that the peer for free access has been added to the server."""
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        record = state.get(user_key)
        if record is None:
            return False
        record["peer_added_to_server"] = True
        state[user_key] = record
        _save_state(state)
        return True


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


def delete_free_access(user_id: int) -> FreeAccessRecord | None:
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        record = state.pop(user_key, None)
        if record is None:
            return None
        _save_state(state)
        return record


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
    hours: int | None = None,
    source: str = "mini_app_ad",
    force_extend: bool = False,
) -> tuple[FreeAccessRecord, bool]:
    """Grant free access to a user.
    
    If access is still active: return existing record (reuse same peer)
    If access expired/doesn't exist: create BRAND NEW profile with new private key and peer
    
    This ensures 1 person can only have 1 device connected at a time.
    If they share the config with friends, those friends get rejected (old key).
    """
    effective_hours = _configured_free_access_hours() if hours is None else max(hours, 1)
    user_key = _user_key(user_id)
    
    # Check if access is still active without recreating
    with _state_lock:
        state = _load_state()
        now = _now_utc()
        current = state.get(user_key)
        
        if current is not None:
            try:
                current_expires_at = _parse_dt(current["expires_at"])
                if current_expires_at > now and not force_extend:
                    # Still valid - return existing record without creating new peer
                    return current, False
            except Exception:
                pass
    
    # Access expired or doesn't exist - create BRAND NEW profile
    # First, remove the old peer from server if it exists
    old_peer_public_key = None
    with _state_lock:
        state = _load_state()
        current = state.get(user_key)
        if current and current.get("peer_public_key"):
            old_peer_public_key = current.get("peer_public_key")
    
    if old_peer_public_key:
        try:
            remove_peer_from_server(old_peer_public_key, user_id)
            logging.info("Removed old free access peer for user_id=%s", user_id)
        except Exception:
            logging.warning("Failed to remove old free access peer for user_id=%s", user_id)
    
    # Reset profile to get completely new private key
    reset_wireguard_profile(user_id)
    profile = ensure_wireguard_profile(user_id)
    
    # Create new free access record with new peer
    with _state_lock:
        state = _load_state()
        now = _now_utc()
        current = state.get(user_key)
        claims_count = (current.get("claims_count", 0) if current else 0) + 1
        
        new_record: FreeAccessRecord = {
            "access_key": profile["profile_id"],
            "granted_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=effective_hours)).isoformat(),
            "claims_count": claims_count,
            "reminder_thresholds_sent": [],
            "source": source,
            "vpn_protocol": "WireGuard",
            "vpn_profile_name": profile["profile_id"],
            "vpn_config_name": get_wireguard_config_filename(user_id),
            "vpn_configured": profile["configured"],
            "peer_public_key": profile["public_key"],
            "peer_added_to_server": False,
        }
        state[user_key] = new_record
        _save_state(state)

        stats = _load_stats()
        stats["total_claims"] = int(stats.get("total_claims", 0)) + 1
        claimed_user_ids = set(
            int(item)
            for item in stats.get("claimed_user_ids", [])
            if isinstance(item, int) or (isinstance(item, str) and item.isdigit())
        )
        user_id_int = int(user_key)
        if user_id_int not in claimed_user_ids:
            claimed_user_ids.add(user_id_int)
            stats["unique_users"] = int(stats.get("unique_users", 0)) + 1
        stats["claimed_user_ids"] = sorted(claimed_user_ids)
        _save_stats(stats)

        return new_record, True


def revoke_expired_free_access() -> int:
    now = _now_utc()
    with _state_lock:
        state = _load_state()
        expired_records: list[tuple[str, FreeAccessRecord]] = []

        for user_key, record in list(state.items()):
            try:
                if _parse_dt(record["expires_at"]) > now:
                    continue
            except Exception:
                continue

            expired_records.append((user_key, record))
            del state[user_key]

        if expired_records:
            _save_state(state)

    revoked_count = 0
    for user_key, record in expired_records:
        peer_public_key = record.get("peer_public_key", "")
        if not peer_public_key:
            continue
        try:
            user_id = int(user_key)
        except Exception:
            continue
        if remove_peer_from_server(peer_public_key, user_id):
            revoked_count += 1

    return revoked_count


async def free_access_cleanup_loop() -> None:
    while True:
        try:
            revoked = revoke_expired_free_access()
            if revoked > 0:
                logging.info("Revoked expired free access peers: %s", revoked)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Free access cleanup loop failed")

        await asyncio.sleep(_configured_cleanup_interval_seconds())


async def send_free_access_reminders(bot) -> int:
    """Send reminder alerts at 10, 5, and 1 minute before expiry."""
    now = _now_utc()
    reminder_sent_count = 0

    def _minutes_left(expires_at: datetime) -> int:
        remaining_seconds = int((expires_at - now).total_seconds())
        if remaining_seconds <= 0:
            return 0
        return (remaining_seconds + 59) // 60

    def _format_minutes_text(minutes_left: int) -> str:
        if minutes_left == 1:
            return "1 минуту"
        return f"{minutes_left} минут"

    with _state_lock:
        state = _load_state()
        for user_key, record in state.items():
            try:
                user_id = int(user_key)
                expires_at = _parse_dt(record["expires_at"])
            except Exception:
                continue

            if expires_at <= now:
                continue

            minutes_left = _minutes_left(expires_at)
            if minutes_left not in FREE_ACCESS_REMINDER_THRESHOLDS:
                continue

            sent_thresholds = record.get("reminder_thresholds_sent", [])
            if not isinstance(sent_thresholds, list):
                sent_thresholds = []
            sent_thresholds = [int(item) for item in sent_thresholds if isinstance(item, int)]
            if minutes_left in sent_thresholds:
                continue

            record["reminder_thresholds_sent"] = sorted(set(sent_thresholds + [minutes_left]), reverse=True)
            state[user_key] = record
            reminder_sent_count += 1

        if reminder_sent_count > 0:
            _save_state(state)

    from app.keyboards.inline import subscription_inline_keyboard
    for user_key, record in state.items():
        try:
            user_id = int(user_key)
        except Exception:
            continue

        if not any(threshold in record.get("reminder_thresholds_sent", []) for threshold in FREE_ACCESS_REMINDER_THRESHOLDS):
            continue

        minutes_left = 0
        try:
            expires_at = _parse_dt(record["expires_at"])
            minutes_left = _minutes_left(expires_at)
        except Exception:
            continue

        if minutes_left not in FREE_ACCESS_REMINDER_THRESHOLDS:
            continue

        sent_thresholds = record.get("reminder_thresholds_sent", [])
        if minutes_left not in sent_thresholds:
            continue

        message = (
            f"⏰ Ваш бесплатный доступ к SkullVPN заканчивается через {_format_minutes_text(minutes_left)}!\n\n"
            "Купите любой из доступных тарифов, чтобы продолжить пользоваться VPN без перерывов."
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=subscription_inline_keyboard(),
            )
            logging.info("Sent expiry reminder to user_id=%s", user_id)
        except Exception:
            logging.warning("Failed to send expiry reminder to user_id=%s", user_id, exc_info=True)

    return reminder_sent_count


async def free_access_reminder_loop(bot) -> None:
    """Periodically check and send free access expiry reminders."""
    while True:
        try:
            sent = await send_free_access_reminders(bot)
            if sent > 0:
                logging.info("Sent %d free access expiry reminders", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Free access reminder loop failed")

        await asyncio.sleep(60)  # Check every minute