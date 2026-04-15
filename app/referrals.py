from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from threading import Lock
from typing import TypedDict

from app.json_storage import load_json_file, save_json_file
from app.free_access import grant_free_access

REFERRALS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "referrals.json"

_state_lock = Lock()


class UserReferralData(TypedDict):
    referrer_id: int | None
    invited_count: int
    bonus_days: int
    activated: bool
    username: str
    activated_at: str | None


class ReferralInviteInfo(TypedDict):
    user_id: int
    username: str
    activated_at: str


ReferralState = dict[str, UserReferralData]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user_key(user_id: int) -> str:
    return str(user_id)


def _load_state() -> ReferralState:
    raw_data = load_json_file(REFERRALS_STORAGE_PATH, {})
    if not isinstance(raw_data, dict):
        return {}

    state: ReferralState = {}
    for key, value in raw_data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue

        referrer_id = value.get("referrer_id")
        invited_count = value.get("invited_count", 0)
        bonus_days = value.get("bonus_days", 0)
        activated = value.get("activated", False)
        username = value.get("username", "")
        activated_at = value.get("activated_at")

        state[key] = {
            "referrer_id": referrer_id if isinstance(referrer_id, int) else None,
            "invited_count": invited_count if isinstance(invited_count, int) else 0,
            "bonus_days": bonus_days if isinstance(bonus_days, int) else 0,
            "activated": bool(activated),
            "username": username if isinstance(username, str) else "",
            "activated_at": activated_at if isinstance(activated_at, str) else None,
        }

    return state


def _save_state(state: ReferralState) -> None:
    save_json_file(REFERRALS_STORAGE_PATH, state)


def ensure_user(user_id: int, username: str | None = None) -> UserReferralData:
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        if user_key not in state:
            state[user_key] = {
                "referrer_id": None,
                "invited_count": 0,
                "bonus_days": 0,
                "activated": False,
                "username": username or "",
                "activated_at": None,
            }
            _save_state(state)
        elif isinstance(username, str) and username:
            record = state[user_key]
            if record.get("username", "") != username:
                record["username"] = username
                state[user_key] = record
                _save_state(state)
        return state[user_key]


def register_user(user_id: int, username: str | None = None) -> bool:
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        if user_key in state:
            return False

        state[user_key] = {
            "referrer_id": None,
            "invited_count": 0,
            "bonus_days": 0,
            "activated": False,
            "username": username or "",
            "activated_at": None,
        }
        _save_state(state)
        return True


def upsert_username(user_id: int, username: str | None) -> None:
    if not isinstance(username, str) or not username:
        return

    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        user = state.get(
            user_key,
            {
                "referrer_id": None,
                "invited_count": 0,
                "bonus_days": 0,
                "activated": False,
                "username": "",
                "activated_at": None,
            },
        )
        if user.get("username", "") == username:
            return
        user["username"] = username
        state[user_key] = user
        _save_state(state)


def get_user_id_by_username(username: str) -> int | None:
    normalized = username.strip().lstrip("@").lower()
    if not normalized:
        return None

    with _state_lock:
        state = _load_state()

    for user_key, data in state.items():
        saved_username = data.get("username", "")
        if not isinstance(saved_username, str) or not saved_username:
            continue
        if saved_username.strip().lstrip("@").lower() == normalized:
            try:
                return int(user_key)
            except Exception:
                return None

    return None


def get_known_username(user_id: int) -> str | None:
    with _state_lock:
        state = _load_state()
        record = state.get(_user_key(user_id))

    if not isinstance(record, dict):
        return None

    username = record.get("username", "")
    if isinstance(username, str) and username.strip():
        return username.strip().lstrip("@")
    return None


def parse_referrer_id(payload: str | None) -> int | None:
    if not payload or not payload.startswith("ref_"):
        return None

    ref_value = payload[4:]
    if not ref_value.isdigit():
        return None

    return int(ref_value)


def bind_referrer_for_new_user(user_id: int, referrer_id: int) -> bool:
    user_key = _user_key(user_id)
    referrer_key = _user_key(referrer_id)

    with _state_lock:
        state = _load_state()
        user = state.get(user_key)
        if user is None:
            user = {
                "referrer_id": None,
                "invited_count": 0,
                "bonus_days": 0,
                "activated": False,
                "username": "",
                "activated_at": None,
            }
            state[user_key] = user

        if user_id == referrer_id:
            return False
        if user["referrer_id"] is not None:
            return False

        user["referrer_id"] = referrer_id
        state[referrer_key] = state.get(
            referrer_key,
            {
                "referrer_id": None,
                "invited_count": 0,
                "bonus_days": 0,
                "activated": False,
                "username": "",
                "activated_at": None,
            },
        )
        _save_state(state)
        return True


def activate_user_and_apply_bonus(user_id: int, username: str | None = None) -> int | None:
    user_key = _user_key(user_id)

    with _state_lock:
        state = _load_state()
        user = state.get(
            user_key,
            {
                "referrer_id": None,
                "invited_count": 0,
                "bonus_days": 0,
                "activated": False,
                "username": "",
                "activated_at": None,
            },
        )

        if user["activated"]:
            return None

        if isinstance(username, str) and username:
            user["username"] = username
        user["activated"] = True
        user["activated_at"] = _now_iso()
        referrer_id = user["referrer_id"]
        state[user_key] = user

        if referrer_id is None or referrer_id == user_id:
            _save_state(state)
            return None

        referrer_key = _user_key(referrer_id)
        referrer = state.get(
            referrer_key,
            {
                "referrer_id": None,
                "invited_count": 0,
                "bonus_days": 0,
                "activated": False,
                "username": "",
                "activated_at": None,
            },
        )
        referrer["invited_count"] += 1
        referrer["bonus_days"] += 3
        user["bonus_days"] += 1
        state[referrer_key] = referrer
        _save_state(state)

    grant_free_access(referrer_id, 24, source="referral_bonus", force_extend=True)
    grant_free_access(user_id, 48, source="referral", force_extend=True)
    return referrer_id


def get_referral_invites(referrer_id: int) -> list[ReferralInviteInfo]:
    referrer_key = _user_key(referrer_id)
    with _state_lock:
        state = _load_state()

        changed = False
        invites: list[ReferralInviteInfo] = []

        for user_key, data in state.items():
            if user_key == referrer_key:
                continue
            if data.get("referrer_id") != referrer_id:
                continue
            if not data.get("activated"):
                continue

            activated_at = data.get("activated_at")
            # Legacy records may not have activation timestamp yet.
            if not isinstance(activated_at, str) or not activated_at:
                activated_at = _now_iso()
                data["activated_at"] = activated_at
                state[user_key] = data
                changed = True

            username = data.get("username", "")
            if not isinstance(username, str) or not username:
                username = f"user_{user_key}"
                data["username"] = username
                state[user_key] = data
                changed = True

            invites.append(
                {
                    "user_id": int(user_key),
                    "username": username,
                    "activated_at": activated_at,
                }
            )

        if changed:
            _save_state(state)

    invites.sort(key=lambda item: item["activated_at"], reverse=True)
    return invites
