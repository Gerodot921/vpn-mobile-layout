from __future__ import annotations

from typing import TypedDict


class UserReferralData(TypedDict):
    referrer_id: int | None
    invited_count: int
    bonus_days: int
    activated: bool


users: dict[int, UserReferralData] = {}


def ensure_user(user_id: int) -> UserReferralData:
    if user_id not in users:
        users[user_id] = {
            "referrer_id": None,
            "invited_count": 0,
            "bonus_days": 0,
            "activated": False,
        }
    return users[user_id]


def register_user(user_id: int) -> bool:
    if user_id in users:
        return False
    ensure_user(user_id)
    return True


def parse_referrer_id(payload: str | None) -> int | None:
    if not payload or not payload.startswith("ref_"):
        return None

    ref_value = payload[4:]
    if not ref_value.isdigit():
        return None

    return int(ref_value)


def bind_referrer_for_new_user(user_id: int, referrer_id: int) -> bool:
    user = ensure_user(user_id)

    if user_id == referrer_id:
        return False
    if user["referrer_id"] is not None:
        return False

    user["referrer_id"] = referrer_id
    ensure_user(referrer_id)
    return True


def activate_user_and_apply_bonus(user_id: int) -> int | None:
    user = ensure_user(user_id)

    if user["activated"]:
        return None

    user["activated"] = True
    referrer_id = user["referrer_id"]

    if referrer_id is None or referrer_id == user_id:
        return None

    referrer = ensure_user(referrer_id)
    referrer["invited_count"] += 1
    referrer["bonus_days"] += 3
    user["bonus_days"] += 1

    return referrer_id
