from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import TypedDict

from app.json_storage import load_json_file, save_json_file
from app.wireguard import ensure_wireguard_profile, get_wireguard_config_filename, remove_peer_from_server, reset_wireguard_profile

FREE_ACCESS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "free_access.json"
FREE_ACCESS_STATS_PATH = Path(__file__).resolve().parents[1] / "data" / "free_access_stats.json"
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
        reminder_thresholds_sent = value.get("reminder_thresholds_sent", [])
        source = value.get("source", "mini_app_ad")

        if not isinstance(access_key, str) or not isinstance(granted_at, str) or not isinstance(expires_at, str):
            continue

        if not isinstance(claims_count, int):
            claims_count = 0
        if not isinstance(reminder_thresholds_sent, list):
            reminder_thresholds_sent = []

        vpn_protocol = value.get("vpn_protocol", "WireGuard")
        vpn_profile_name = value.get("vpn_profile_name", access_key)
        vpn_config_name = value.get("vpn_config_name", f"skull-vpn-{access_key}.conf")
        vpn_configured = value.get("vpn_configured", False)
        peer_public_key = value.get("peer_public_key", "")
        peer_added_to_server = value.get("peer_added_to_server", False)

        state[key] = {
            "access_key": access_key,
            "granted_at": granted_at,
            "expires_at": expires_at,
            "claims_count": claims_count,
            "reminder_thresholds_sent": [
                int(item) for item in reminder_thresholds_sent if isinstance(item, int)
            ],
            "source": source if isinstance(source, str) and source else "mini_app_ad",
            "vpn_protocol": vpn_protocol if isinstance(vpn_protocol, str) and vpn_protocol else "WireGuard",
            "vpn_profile_name": vpn_profile_name if isinstance(vpn_profile_name, str) and vpn_profile_name else access_key,
            "vpn_config_name": vpn_config_name if isinstance(vpn_config_name, str) and vpn_config_name else f"skull-vpn-{access_key}.conf",
            "vpn_configured": bool(vpn_configured),
            "peer_public_key": peer_public_key if isinstance(peer_public_key, str) else "",
            "peer_added_to_server": bool(peer_added_to_server),
        }

    return state


def _save_state(state: FreeAccessState) -> None:
    save_json_file(FREE_ACCESS_STORAGE_PATH, state)


def _load_stats() -> dict[str, object]:
    raw_data = load_json_file(FREE_ACCESS_STATS_PATH, {})
    if not isinstance(raw_data, dict):
        return {"total_claims": 0, "unique_users": 0, "claimed_user_ids": []}

    total_claims = raw_data.get("total_claims", 0)
    unique_users = raw_data.get("unique_users", 0)
    claimed_user_ids = raw_data.get("claimed_user_ids", [])

    if not isinstance(claimed_user_ids, list):
        claimed_user_ids = []

    safe_user_ids = [item for item in claimed_user_ids if isinstance(item, str) and item.isdigit()]
    return {
        "total_claims": total_claims if isinstance(total_claims, int) and total_claims >= 0 else 0,
        "unique_users": unique_users if isinstance(unique_users, int) and unique_users >= 0 else 0,
        "claimed_user_ids": safe_user_ids,
    }


def _save_stats(stats: dict[str, object]) -> None:
    save_json_file(FREE_ACCESS_STATS_PATH, stats)


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
        claimed_user_ids = set(str(item) for item in stats.get("claimed_user_ids", []) if isinstance(item, str))
        if user_key not in claimed_user_ids:
            claimed_user_ids.add(user_key)
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