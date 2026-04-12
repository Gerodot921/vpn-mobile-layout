from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import TypedDict

from app.json_storage import load_json_file, save_json_file
from app.subscriptions import extend_subscription

REFERRALS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "referrals.json"

_state_lock = Lock()


class UserReferralData(TypedDict):
    referrer_id: int | None
    invited_count: int
    bonus_days: int
    activated: bool


ReferralState = dict[str, UserReferralData]


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

        state[key] = {
            "referrer_id": referrer_id if isinstance(referrer_id, int) else None,
            "invited_count": invited_count if isinstance(invited_count, int) else 0,
            "bonus_days": bonus_days if isinstance(bonus_days, int) else 0,
            "activated": bool(activated),
        }

    return state


def _save_state(state: ReferralState) -> None:
    save_json_file(REFERRALS_STORAGE_PATH, state)


def ensure_user(user_id: int) -> UserReferralData:
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        if user_key not in state:
            state[user_key] = {
                "referrer_id": None,
                "invited_count": 0,
                "bonus_days": 0,
                "activated": False,
            }
            _save_state(state)
        return state[user_key]


def register_user(user_id: int) -> bool:
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
        }
        _save_state(state)
        return True


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
            },
        )
        _save_state(state)
        return True


def activate_user_and_apply_bonus(user_id: int) -> int | None:
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
            },
        )

        if user["activated"]:
            return None

        user["activated"] = True
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
            },
        )
        referrer["invited_count"] += 1
        referrer["bonus_days"] += 3
        user["bonus_days"] += 1
        state[referrer_key] = referrer
        _save_state(state)

    extend_subscription(referrer_id, 3)
    extend_subscription(user_id, 1)
    return referrer_id
