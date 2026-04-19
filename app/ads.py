from __future__ import annotations

import os
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from app.json_storage import STORAGE_DB_PATH, load_json_file

ADS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "ads.json"
AD_SESSIONS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "ad_sessions.json"
ADS_STATE_TABLE = "ads_state"
AD_SESSIONS_TABLE = "ad_sessions"

DEFAULT_AD_ASSET_URL = "https://media.tenor.com/zPU3mLwPo0IAAAAM/laughing-you-got-the-whole-squad-laughing.gif"
DEFAULT_AD_DURATION_SECONDS = 30
DEFAULT_SESSION_TTL_SECONDS = 600

_state_lock = Lock()
_seed_checked = False


class Ad(TypedDict):
    ad_id: str
    title: str
    asset_url: str
    click_url: str
    duration_sec: int
    active: bool


class AdSession(TypedDict):
    user_id: int
    ad_id: str
    started_at: str
    expires_at: str
    required_seconds: int
    completed: bool
    clicked: bool


class AdState(TypedDict):
    active_ad: Ad
    impressions: int
    completions: int
    clicks: int


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
        CREATE TABLE IF NOT EXISTS {ADS_STATE_TABLE} (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            active_ad_json TEXT NOT NULL,
            impressions INTEGER NOT NULL,
            completions INTEGER NOT NULL,
            clicks INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AD_SESSIONS_TABLE} (
            session_token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            ad_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            required_seconds INTEGER NOT NULL DEFAULT 30,
            completed INTEGER NOT NULL,
            clicked INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # Lightweight schema migration for existing DBs.
    state_columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({ADS_STATE_TABLE})").fetchall()
        if len(row) >= 2
    }
    if "clicks" not in state_columns:
        connection.execute(f"ALTER TABLE {ADS_STATE_TABLE} ADD COLUMN clicks INTEGER NOT NULL DEFAULT 0")

    session_columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({AD_SESSIONS_TABLE})").fetchall()
        if len(row) >= 2
    }
    if "required_seconds" not in session_columns:
        connection.execute(
            f"ALTER TABLE {AD_SESSIONS_TABLE} ADD COLUMN required_seconds INTEGER NOT NULL DEFAULT {DEFAULT_AD_DURATION_SECONDS}"
        )
    if "clicked" not in session_columns:
        connection.execute(f"ALTER TABLE {AD_SESSIONS_TABLE} ADD COLUMN clicked INTEGER NOT NULL DEFAULT 0")
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{AD_SESSIONS_TABLE}_user_id ON {AD_SESSIONS_TABLE}(user_id)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{AD_SESSIONS_TABLE}_expires_at ON {AD_SESSIONS_TABLE}(expires_at)"
    )
    return connection


def _serialize_ad(ad: Ad) -> str:
    return json.dumps(ad, ensure_ascii=False, sort_keys=True)


def _deserialize_ad(raw: Any) -> Ad | None:
    if isinstance(raw, str) and raw:
        try:
            payload = json.loads(raw)
        except Exception:
            return None
    elif isinstance(raw, dict):
        payload = raw
    else:
        return None

    if not isinstance(payload, dict):
        return None

    return {
        "ad_id": str(payload.get("ad_id", "ad-default")),
        "title": str(payload.get("title", "Рекламное предложение")),
        "asset_url": str(payload.get("asset_url", _default_ad()["asset_url"])),
        "click_url": str(payload.get("click_url", _default_ad()["click_url"])),
        "duration_sec": int(payload.get("duration_sec", _default_ad()["duration_sec"])),
        "active": bool(payload.get("active", True)),
    }


def _ensure_seeded() -> None:
    global _seed_checked
    if _seed_checked:
        return

    with _connect() as connection:
        existing = connection.execute(f"SELECT COUNT(*) FROM {ADS_STATE_TABLE}").fetchone()
        if existing and int(existing[0]) > 0:
            _seed_checked = True
            return

        raw_data = load_json_file(ADS_STORAGE_PATH, {})
        active_ad = _default_ad()
        impressions = 0
        completions = 0
        clicks = 0

        if isinstance(raw_data, dict):
            deserialized = _deserialize_ad(raw_data.get("active_ad"))
            if deserialized is not None:
                active_ad = deserialized
            impressions_value = raw_data.get("impressions", 0)
            completions_value = raw_data.get("completions", 0)
            clicks_value = raw_data.get("clicks", 0)
            if isinstance(impressions_value, int) and impressions_value >= 0:
                impressions = impressions_value
            if isinstance(completions_value, int) and completions_value >= 0:
                completions = completions_value
            if isinstance(clicks_value, int) and clicks_value >= 0:
                clicks = clicks_value

        connection.execute(
            f"INSERT OR REPLACE INTO {ADS_STATE_TABLE} (id, active_ad_json, impressions, completions, clicks) VALUES (1, ?, ?, ?, ?)",
            (_serialize_ad(active_ad), impressions, completions, clicks),
        )

        raw_sessions = load_json_file(AD_SESSIONS_STORAGE_PATH, {})
        if isinstance(raw_sessions, dict):
            for token, value in raw_sessions.items():
                if not isinstance(token, str) or not isinstance(value, dict):
                    continue
                user_id = value.get("user_id")
                ad_id = value.get("ad_id")
                started_at = value.get("started_at")
                expires_at = value.get("expires_at")
                completed = value.get("completed", False)
                clicked = value.get("clicked", False)
                required_seconds = value.get("required_seconds", _default_ad()["duration_sec"])
                if not isinstance(user_id, int) or not all(isinstance(item, str) for item in [ad_id, started_at, expires_at]):
                    continue
                try:
                    required_seconds_value = int(required_seconds)
                except Exception:
                    required_seconds_value = _default_ad()["duration_sec"]
                required_seconds_value = min(max(required_seconds_value, 5), 300)
                connection.execute(
                    f"""
                    INSERT OR REPLACE INTO {AD_SESSIONS_TABLE}
                    (session_token, user_id, ad_id, started_at, expires_at, required_seconds, completed, clicked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        token,
                        user_id,
                        ad_id,
                        started_at,
                        expires_at,
                        required_seconds_value,
                        1 if bool(completed) else 0,
                        1 if bool(clicked) else 0,
                    ),
                )

        connection.commit()
    _seed_checked = True


def _default_ad() -> Ad:
    asset_url = os.getenv("AD_DEFAULT_ASSET_URL", DEFAULT_AD_ASSET_URL).strip() or DEFAULT_AD_ASSET_URL
    click_url = os.getenv("AD_DEFAULT_CLICK_URL", asset_url).strip() or asset_url
    title = os.getenv("AD_DEFAULT_TITLE", "Рекламное предложение").strip() or "Рекламное предложение"

    duration_raw = os.getenv("AD_DURATION_SECONDS", str(DEFAULT_AD_DURATION_SECONDS)).strip()
    try:
        duration_sec = int(duration_raw)
    except Exception:
        duration_sec = DEFAULT_AD_DURATION_SECONDS
    duration_sec = min(max(duration_sec, 5), 300)

    return {
        "ad_id": "ad-default",
        "title": title,
        "asset_url": asset_url,
        "click_url": click_url,
        "duration_sec": duration_sec,
        "active": True,
    }


def _load_ad_state() -> AdState:
    _ensure_seeded()
    with _connect() as connection:
        row = connection.execute(
            f"SELECT active_ad_json, impressions, completions, clicks FROM {ADS_STATE_TABLE} WHERE id = 1"
        ).fetchone()

    active_ad = _default_ad()
    impressions = 0
    completions = 0
    clicks = 0
    if row is not None:
        parsed_ad = _deserialize_ad(row[0])
        if parsed_ad is not None:
            active_ad = parsed_ad
        impressions = int(row[1]) if isinstance(row[1], int) and row[1] >= 0 else 0
        completions = int(row[2]) if isinstance(row[2], int) and row[2] >= 0 else 0
        clicks = int(row[3]) if isinstance(row[3], int) and row[3] >= 0 else 0

    if active_ad["duration_sec"] <= 0:
        active_ad["duration_sec"] = DEFAULT_AD_DURATION_SECONDS

    return {"active_ad": active_ad, "impressions": impressions, "completions": completions, "clicks": clicks}


def _save_ad_state(state: AdState) -> None:
    with _connect() as connection:
        connection.execute(
            f"INSERT OR REPLACE INTO {ADS_STATE_TABLE} (id, active_ad_json, impressions, completions, clicks) VALUES (1, ?, ?, ?, ?)",
            (
                _serialize_ad(state.get("active_ad") or _default_ad()),
                int(state.get("impressions", 0)) if isinstance(state.get("impressions", 0), int) else 0,
                int(state.get("completions", 0)) if isinstance(state.get("completions", 0), int) else 0,
                int(state.get("clicks", 0)) if isinstance(state.get("clicks", 0), int) else 0,
            ),
        )
        connection.commit()


def _load_sessions() -> dict[str, AdSession]:
    _ensure_seeded()
    sessions: dict[str, AdSession] = {}
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT session_token, user_id, ad_id, started_at, expires_at, required_seconds, completed, clicked FROM {AD_SESSIONS_TABLE}"
        ).fetchall()

    for row in rows:
        token = str(row[0])
        sessions[token] = {
            "user_id": int(row[1]),
            "ad_id": str(row[2]),
            "started_at": str(row[3]),
            "expires_at": str(row[4]),
            "required_seconds": int(row[5]) if isinstance(row[5], int) else DEFAULT_AD_DURATION_SECONDS,
            "completed": bool(row[6]),
            "clicked": bool(row[7]),
        }

    return sessions


def _save_sessions(sessions: dict[str, AdSession]) -> None:
    with _connect() as connection:
        connection.execute(f"DELETE FROM {AD_SESSIONS_TABLE}")
        for token, session in sessions.items():
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {AD_SESSIONS_TABLE}
                (session_token, user_id, ad_id, started_at, expires_at, required_seconds, completed, clicked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token,
                    int(session.get("user_id", 0)) if isinstance(session.get("user_id", 0), int) else 0,
                    str(session.get("ad_id") or ""),
                    str(session.get("started_at") or _now_utc().isoformat()),
                    str(session.get("expires_at") or _now_utc().isoformat()),
                    int(session.get("required_seconds", DEFAULT_AD_DURATION_SECONDS))
                    if isinstance(session.get("required_seconds", DEFAULT_AD_DURATION_SECONDS), int)
                    else DEFAULT_AD_DURATION_SECONDS,
                    1 if bool(session.get("completed", False)) else 0,
                    1 if bool(session.get("clicked", False)) else 0,
                ),
            )
        connection.commit()


def _session_ttl_seconds() -> int:
    raw = os.getenv("AD_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS)).strip()
    try:
        value = int(raw)
    except Exception:
        value = DEFAULT_SESSION_TTL_SECONDS
    return min(max(value, 60), 3600)


def get_active_ad() -> Ad | None:
    with _state_lock:
        state = _load_ad_state()
        ad = state["active_ad"]
        if not ad.get("active"):
            return None
        return ad


def start_ad_session(user_id: int) -> tuple[Ad | None, str | None]:
    with _state_lock:
        state = _load_ad_state()
        ad = state["active_ad"]
        # Free-access flow always requires an ad watch. Even when ad campaign is
        # toggled off for marketing, we still start a reward ad session.
        if not isinstance(ad, dict):
            ad = _default_ad()

        token = f"ad_{secrets.token_urlsafe(20)}"
        now = _now_utc()
        sessions = _load_sessions()
        sessions[token] = {
            "user_id": user_id,
            "ad_id": ad["ad_id"],
            "started_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=_session_ttl_seconds())).isoformat(),
            "required_seconds": int(ad.get("duration_sec", DEFAULT_AD_DURATION_SECONDS)),
            "completed": False,
            "clicked": False,
        }
        _save_sessions(sessions)

        state["impressions"] = state.get("impressions", 0) + 1
        _save_ad_state(state)

        return ad, token


def complete_ad_session(user_id: int, session_token: str, watched_seconds: int) -> tuple[bool, str]:
    if not session_token:
        return False, "Missing ad session token"

    with _state_lock:
        sessions = _load_sessions()
        session = sessions.get(session_token)
        if session is None:
            return False, "Ad session not found"

        if session["user_id"] != user_id:
            return False, "Ad session does not belong to this user"

        if session.get("completed"):
            return False, "Ad session already completed"

        now = _now_utc()
        try:
            if _parse_dt(session["expires_at"]) <= now:
                return False, "Ad session expired"
        except Exception:
            return False, "Invalid ad session"

        required = int(session.get("required_seconds", DEFAULT_AD_DURATION_SECONDS))
        required = min(max(required, 5), 300)

        elapsed_seconds = 0
        try:
            elapsed = now - _parse_dt(session["started_at"])
            elapsed_seconds = max(0, int(elapsed.total_seconds()))
        except Exception:
            elapsed_seconds = 0

        effective_watched = max(int(watched_seconds), elapsed_seconds)
        if effective_watched < required:
            return False, f"Insufficient watch time ({effective_watched}/{required})"

        session["completed"] = True
        sessions[session_token] = session
        _save_sessions(sessions)

        state = _load_ad_state()
        state["completions"] = state.get("completions", 0) + 1
        _save_ad_state(state)

        return True, "ok"


def get_ad_stats() -> dict[str, Any]:
    with _state_lock:
        state = _load_ad_state()
        return {
            "impressions": state.get("impressions", 0),
            "completions": state.get("completions", 0),
            "clicks": state.get("clicks", 0),
            "active_ad": state.get("active_ad"),
        }


def register_ad_click(user_id: int, session_token: str) -> tuple[bool, str]:
    if not session_token:
        return False, "Missing ad session token"

    with _state_lock:
        sessions = _load_sessions()
        session = sessions.get(session_token)
        if session is None:
            return False, "Ad session not found"
        if session["user_id"] != user_id:
            return False, "Ad session does not belong to this user"

        now = _now_utc()
        try:
            if _parse_dt(session["expires_at"]) <= now:
                return False, "Ad session expired"
        except Exception:
            return False, "Invalid ad session"

        if session.get("clicked"):
            return True, "already"

        session["clicked"] = True
        sessions[session_token] = session
        _save_sessions(sessions)

        state = _load_ad_state()
        state["clicks"] = int(state.get("clicks", 0)) + 1
        _save_ad_state(state)
        return True, "ok"


def set_ad_active(active: bool) -> Ad:
    with _state_lock:
        state = _load_ad_state()
        ad = state["active_ad"]
        ad["active"] = bool(active)
        state["active_ad"] = ad
        _save_ad_state(state)
        return ad


def set_active_ad(
    *,
    asset_url: str,
    click_url: str | None = None,
    title: str | None = None,
    duration_sec: int | None = None,
) -> Ad:
    cleaned_asset = asset_url.strip()
    if not cleaned_asset:
        raise ValueError("asset_url is required")

    if duration_sec is None:
        safe_duration = DEFAULT_AD_DURATION_SECONDS
    else:
        safe_duration = min(max(int(duration_sec), 5), 300)

    with _state_lock:
        state = _load_ad_state()
        ad = state["active_ad"]

        ad["asset_url"] = cleaned_asset
        ad["click_url"] = (click_url or cleaned_asset).strip() or cleaned_asset
        ad["title"] = (title or ad.get("title") or "Рекламное предложение").strip() or "Рекламное предложение"
        ad["duration_sec"] = safe_duration
        ad["active"] = True

        state["active_ad"] = ad
        _save_ad_state(state)
        return ad
