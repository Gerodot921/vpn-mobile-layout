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
from app.wireguard import ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_profile, remove_peer_from_server

FREE_ACCESS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "free_access.json"
DEFAULT_FREE_ACCESS_HOURS = 1
FREE_ACCESS_CLEANUP_INTERVAL_SECONDS = 60

_state_lock = Lock()


class FreeAccessRecord(TypedDict):
    access_key: str
    granted_at: str
    expires_at: str
    claims_count: int
    source: str
    vpn_protocol: str
    vpn_profile_name: str
    vpn_config_name: str
    vpn_configured: bool


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

        vpn_protocol = value.get("vpn_protocol", "WireGuard")
        vpn_profile_name = value.get("vpn_profile_name", access_key)
        vpn_config_name = value.get("vpn_config_name", f"skull-vpn-{access_key}.conf")
        vpn_configured = value.get("vpn_configured", False)

        state[key] = {
            "access_key": access_key,
            "granted_at": granted_at,
            "expires_at": expires_at,
            "claims_count": claims_count,
            "source": source if isinstance(source, str) and source else "mini_app_ad",
            "vpn_protocol": vpn_protocol if isinstance(vpn_protocol, str) and vpn_protocol else "WireGuard",
            "vpn_profile_name": vpn_profile_name if isinstance(vpn_profile_name, str) and vpn_profile_name else access_key,
            "vpn_config_name": vpn_config_name if isinstance(vpn_config_name, str) and vpn_config_name else f"skull-vpn-{access_key}.conf",
            "vpn_configured": bool(vpn_configured),
        }

    return state


def _save_state(state: FreeAccessState) -> None:
    save_json_file(FREE_ACCESS_STORAGE_PATH, state)


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
    hours: int | None = None,
    source: str = "mini_app_ad",
    force_extend: bool = False,
) -> tuple[FreeAccessRecord, bool]:
    effective_hours = _configured_free_access_hours() if hours is None else max(hours, 1)
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        now = _now_utc()
        current = state.get(user_key)
        profile = ensure_wireguard_profile(user_id)

        if current is not None:
            try:
                current_expires_at = _parse_dt(current["expires_at"])
                if current_expires_at > now and not force_extend:
                    return current, False
                base_expires_at = current_expires_at if current_expires_at > now else now
            except Exception:
                base_expires_at = now
        else:
            base_expires_at = now

        new_record: FreeAccessRecord = {
            "access_key": profile["profile_id"],
            "granted_at": now.isoformat(),
            "expires_at": (base_expires_at + timedelta(hours=effective_hours)).isoformat(),
            "claims_count": (current.get("claims_count", 0) if current else 0) + 1,
            "source": source,
            "vpn_protocol": "WireGuard",
            "vpn_profile_name": profile["profile_id"],
            "vpn_config_name": get_wireguard_config_filename(user_id),
            "vpn_configured": profile["configured"],
        }
        state[user_key] = new_record
        _save_state(state)
        return new_record, True


def revoke_expired_free_access() -> int:
    now = _now_utc()
    with _state_lock:
        state = _load_state()
        expired_user_ids: list[int] = []

        for user_key, record in list(state.items()):
            try:
                if _parse_dt(record["expires_at"]) > now:
                    continue
                user_id = int(user_key)
            except Exception:
                continue

            expired_user_ids.append(user_id)
            del state[user_key]

        if expired_user_ids:
            _save_state(state)

    revoked_count = 0
    for user_id in expired_user_ids:
        profile = get_wireguard_profile(user_id)
        if profile is None:
            continue
        if remove_peer_from_server(profile.get("public_key", ""), user_id):
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