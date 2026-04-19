from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock
from typing import TypedDict

from app.json_storage import STORAGE_DB_PATH, load_json_file
from app.free_access import grant_free_access

REFERRALS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "referrals.json"
REFERRALS_TABLE = "referrals"

_state_lock = Lock()


class UserReferralData(TypedDict):
    referrer_id: int | None
    invited_count: int
    bonus_days: int
    activated: bool
    username: str
    started_at: str | None
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


def _connect() -> sqlite3.Connection:
    STORAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STORAGE_DB_PATH, timeout=20)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REFERRALS_TABLE} (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            invited_count INTEGER NOT NULL,
            bonus_days INTEGER NOT NULL,
            activated INTEGER NOT NULL,
            username TEXT NOT NULL,
            started_at TEXT,
            activated_at TEXT
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{REFERRALS_TABLE}_referrer_id ON {REFERRALS_TABLE}(referrer_id)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{REFERRALS_TABLE}_username ON {REFERRALS_TABLE}(username)"
    )
    return connection


def _normalize_row(row: sqlite3.Row | tuple[object, ...]) -> UserReferralData:
    referrer_id = row[1]
    invited_count = row[2]
    bonus_days = row[3]
    activated = row[4]
    username = row[5]
    started_at = row[6]
    activated_at = row[7]

    return {
        "referrer_id": int(referrer_id) if isinstance(referrer_id, int) else None,
        "invited_count": int(invited_count) if isinstance(invited_count, int) else 0,
        "bonus_days": int(bonus_days) if isinstance(bonus_days, int) else 0,
        "activated": bool(activated),
        "username": username if isinstance(username, str) else "",
        "started_at": started_at if isinstance(started_at, str) and started_at else None,
        "activated_at": activated_at if isinstance(activated_at, str) and activated_at else None,
    }


def _default_user_data(username: str | None = None) -> UserReferralData:
    return {
        "referrer_id": None,
        "invited_count": 0,
        "bonus_days": 0,
        "activated": False,
        "username": username or "",
        "started_at": _now_iso(),
        "activated_at": None,
    }


def _fetch_user(connection: sqlite3.Connection, user_id: int) -> UserReferralData | None:
    row = connection.execute(
        f"SELECT user_id, referrer_id, invited_count, bonus_days, activated, username, started_at, activated_at FROM {REFERRALS_TABLE} WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return _normalize_row(row)


def _upsert_user(connection: sqlite3.Connection, user_id: int, data: UserReferralData) -> None:
    connection.execute(
        f"""
        INSERT OR REPLACE INTO {REFERRALS_TABLE}
        (user_id, referrer_id, invited_count, bonus_days, activated, username, started_at, activated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            data.get("referrer_id"),
            int(data.get("invited_count", 0)),
            int(data.get("bonus_days", 0)),
            1 if data.get("activated") else 0,
            str(data.get("username") or ""),
            data.get("started_at"),
            data.get("activated_at"),
        ),
    )


def _ensure_seeded(connection: sqlite3.Connection) -> None:
    existing = connection.execute(f"SELECT COUNT(*) FROM {REFERRALS_TABLE}").fetchone()
    if existing and int(existing[0]) > 0:
        return

    raw_data = load_json_file(REFERRALS_STORAGE_PATH, {})
    if not isinstance(raw_data, dict) or not raw_data:
        return

    for user_key, value in raw_data.items():
        if not isinstance(user_key, str) or not user_key.isdigit() or not isinstance(value, dict):
            continue

        user_id = int(user_key)
        referrer_id = value.get("referrer_id")
        started_at = value.get("started_at")
        activated_at = value.get("activated_at")

        data: UserReferralData = {
            "referrer_id": int(referrer_id) if isinstance(referrer_id, int) else None,
            "invited_count": int(value.get("invited_count", 0)) if isinstance(value.get("invited_count", 0), int) else 0,
            "bonus_days": int(value.get("bonus_days", 0)) if isinstance(value.get("bonus_days", 0), int) else 0,
            "activated": bool(value.get("activated", False)),
            "username": value.get("username") if isinstance(value.get("username"), str) else "",
            "started_at": started_at if isinstance(started_at, str) and started_at else None,
            "activated_at": activated_at if isinstance(activated_at, str) and activated_at else None,
        }
        _upsert_user(connection, user_id, data)

    connection.commit()


def _load_state() -> ReferralState:
    with _connect() as connection:
        _ensure_seeded(connection)
        rows = connection.execute(
            f"SELECT user_id, referrer_id, invited_count, bonus_days, activated, username, started_at, activated_at FROM {REFERRALS_TABLE}"
        ).fetchall()

    state: ReferralState = {}
    for row in rows:
        user_id = int(row[0])
        state[_user_key(user_id)] = _normalize_row(row)
    return state


def ensure_user(user_id: int, username: str | None = None) -> UserReferralData:
    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            record = _fetch_user(connection, user_id)
            if record is None:
                record = _default_user_data(username)
                _upsert_user(connection, user_id, record)
                connection.commit()
                return record

            changed = False
            if isinstance(username, str) and username and record.get("username", "") != username:
                record["username"] = username
                changed = True

            if not isinstance(record.get("started_at"), str) or not record.get("started_at"):
                record["started_at"] = _now_iso()
                changed = True

            if changed:
                _upsert_user(connection, user_id, record)
                connection.commit()

            return record


def register_user(user_id: int, username: str | None = None) -> bool:
    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            existing = _fetch_user(connection, user_id)
            if existing is not None:
                return False

            _upsert_user(connection, user_id, _default_user_data(username))
            connection.commit()
            return True


def upsert_username(user_id: int, username: str | None) -> None:
    if not isinstance(username, str) or not username:
        return

    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            user = _fetch_user(connection, user_id) or _default_user_data(None)
            if user.get("username", "") == username:
                return
            user["username"] = username
            if not isinstance(user.get("started_at"), str) or not user.get("started_at"):
                user["started_at"] = _now_iso()
            _upsert_user(connection, user_id, user)
            connection.commit()


def get_user_id_by_username(username: str) -> int | None:
    normalized = username.strip().lstrip("@").lower()
    if not normalized:
        return None

    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            rows = connection.execute(
                f"SELECT user_id, username FROM {REFERRALS_TABLE} WHERE username <> ''"
            ).fetchall()

    for row in rows:
        user_id = row[0]
        saved_username = row[1]
        if not isinstance(saved_username, str) or not saved_username:
            continue
        if saved_username.strip().lstrip("@").lower() == normalized:
            return int(user_id)
    return None


def get_known_username(user_id: int) -> str | None:
    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            record = _fetch_user(connection, user_id)

    if record is None:
        return None

    username = record.get("username", "")
    if isinstance(username, str) and username.strip():
        return username.strip().lstrip("@")
    return None


def list_known_user_ids() -> list[int]:
    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            rows = connection.execute(f"SELECT user_id FROM {REFERRALS_TABLE} ORDER BY user_id ASC").fetchall()

    return [int(row[0]) for row in rows]


def parse_referrer_id(payload: str | None) -> int | None:
    if not payload or not payload.startswith("ref_"):
        return None

    ref_value = payload[4:]
    if not ref_value.isdigit():
        return None

    return int(ref_value)


def bind_referrer_for_new_user(user_id: int, referrer_id: int) -> bool:
    with _state_lock:
        if user_id == referrer_id:
            return False

        with _connect() as connection:
            _ensure_seeded(connection)
            user = _fetch_user(connection, user_id) or _default_user_data(None)
            if user.get("referrer_id") is not None:
                return False

            referrer = _fetch_user(connection, referrer_id) or _default_user_data(None)

            user["referrer_id"] = referrer_id
            _upsert_user(connection, user_id, user)
            _upsert_user(connection, referrer_id, referrer)
            connection.commit()
            return True


def activate_user_and_apply_bonus(user_id: int, username: str | None = None) -> int | None:
    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            user = _fetch_user(connection, user_id) or _default_user_data(None)

            if user.get("activated"):
                return None

            if isinstance(username, str) and username:
                user["username"] = username
            if not isinstance(user.get("started_at"), str) or not user.get("started_at"):
                user["started_at"] = _now_iso()

            user["activated"] = True
            user["activated_at"] = _now_iso()
            referrer_id = user.get("referrer_id")
            _upsert_user(connection, user_id, user)

            if referrer_id is None or referrer_id == user_id:
                connection.commit()
                return None

            referrer = _fetch_user(connection, int(referrer_id)) or _default_user_data(None)
            referrer["invited_count"] += 1
            referrer["bonus_days"] += 3
            user["bonus_days"] += 1
            _upsert_user(connection, user_id, user)
            _upsert_user(connection, int(referrer_id), referrer)
            connection.commit()

    grant_free_access(referrer_id, 24, source="referral_bonus", force_extend=True)
    grant_free_access(user_id, 48, source="referral", force_extend=True)
    return referrer_id


def get_referral_invites(referrer_id: int) -> list[ReferralInviteInfo]:
    with _state_lock:
        invites: list[ReferralInviteInfo] = []
        with _connect() as connection:
            _ensure_seeded(connection)
            rows = connection.execute(
                f"""
                SELECT user_id, username, activated_at
                FROM {REFERRALS_TABLE}
                WHERE referrer_id = ? AND activated = 1 AND user_id <> ?
                ORDER BY activated_at DESC
                """,
                (referrer_id, referrer_id),
            ).fetchall()

            changed = False
            for row in rows:
                user_id = int(row[0])
                username = row[1] if isinstance(row[1], str) else ""
                activated_at = row[2] if isinstance(row[2], str) else ""

                if not activated_at:
                    activated_at = _now_iso()
                    connection.execute(
                        f"UPDATE {REFERRALS_TABLE} SET activated_at = ? WHERE user_id = ?",
                        (activated_at, user_id),
                    )
                    changed = True

                if not username:
                    username = f"user_{user_id}"
                    connection.execute(
                        f"UPDATE {REFERRALS_TABLE} SET username = ? WHERE user_id = ?",
                        (username, user_id),
                    )
                    changed = True

                invites.append(
                    {
                        "user_id": user_id,
                        "username": username,
                        "activated_at": activated_at,
                    }
                )

            if changed:
                connection.commit()

    invites.sort(key=lambda item: item["activated_at"], reverse=True)
    return invites


def list_registered_users() -> list[tuple[int, UserReferralData]]:
    with _state_lock:
        with _connect() as connection:
            _ensure_seeded(connection)
            rows = connection.execute(
                f"""
                SELECT user_id, referrer_id, invited_count, bonus_days, activated, username, started_at, activated_at
                FROM {REFERRALS_TABLE}
                ORDER BY COALESCE(started_at, activated_at, '') ASC
                """
            ).fetchall()

    users: list[tuple[int, UserReferralData]] = []
    for row in rows:
        users.append((int(row[0]), _normalize_row(row)))
    return users
