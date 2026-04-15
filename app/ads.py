from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from app.json_storage import load_json_file, save_json_file

ADS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "ads.json"
AD_SESSIONS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "ad_sessions.json"

DEFAULT_AD_ASSET_URL = "https://media.tenor.com/zPU3mLwPo0IAAAAM/laughing-you-got-the-whole-squad-laughing.gif"
DEFAULT_AD_DURATION_SECONDS = 30
DEFAULT_SESSION_TTL_SECONDS = 600

_state_lock = Lock()


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
    completed: bool


class AdState(TypedDict):
    active_ad: Ad
    impressions: int
    completions: int


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
    raw_data = load_json_file(ADS_STORAGE_PATH, {})
    if not isinstance(raw_data, dict):
        return {"active_ad": _default_ad(), "impressions": 0, "completions": 0}

    active_ad = raw_data.get("active_ad")
    impressions = raw_data.get("impressions", 0)
    completions = raw_data.get("completions", 0)

    if not isinstance(active_ad, dict):
        active_ad = _default_ad()

    normalized_ad: Ad = {
        "ad_id": str(active_ad.get("ad_id", "ad-default")),
        "title": str(active_ad.get("title", "Рекламное предложение")),
        "asset_url": str(active_ad.get("asset_url", _default_ad()["asset_url"])),
        "click_url": str(active_ad.get("click_url", _default_ad()["click_url"])),
        "duration_sec": int(active_ad.get("duration_sec", _default_ad()["duration_sec"])),
        "active": bool(active_ad.get("active", True)),
    }

    if normalized_ad["duration_sec"] <= 0:
        normalized_ad["duration_sec"] = DEFAULT_AD_DURATION_SECONDS

    return {
        "active_ad": normalized_ad,
        "impressions": impressions if isinstance(impressions, int) and impressions >= 0 else 0,
        "completions": completions if isinstance(completions, int) and completions >= 0 else 0,
    }


def _save_ad_state(state: AdState) -> None:
    save_json_file(ADS_STORAGE_PATH, state)


def _load_sessions() -> dict[str, AdSession]:
    raw_data = load_json_file(AD_SESSIONS_STORAGE_PATH, {})
    if not isinstance(raw_data, dict):
        return {}

    sessions: dict[str, AdSession] = {}
    for key, value in raw_data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue

        user_id = value.get("user_id")
        ad_id = value.get("ad_id")
        started_at = value.get("started_at")
        expires_at = value.get("expires_at")
        completed = value.get("completed", False)

        if not isinstance(user_id, int):
            continue
        if not all(isinstance(item, str) for item in [ad_id, started_at, expires_at]):
            continue

        sessions[key] = {
            "user_id": user_id,
            "ad_id": ad_id,
            "started_at": started_at,
            "expires_at": expires_at,
            "completed": bool(completed),
        }

    return sessions


def _save_sessions(sessions: dict[str, AdSession]) -> None:
    save_json_file(AD_SESSIONS_STORAGE_PATH, sessions)


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
        if not ad.get("active"):
            return None, None

        token = f"ad_{secrets.token_urlsafe(20)}"
        now = _now_utc()
        sessions = _load_sessions()
        sessions[token] = {
            "user_id": user_id,
            "ad_id": ad["ad_id"],
            "started_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=_session_ttl_seconds())).isoformat(),
            "completed": False,
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

        state = _load_ad_state()
        ad = state["active_ad"]
        required = int(ad.get("duration_sec", DEFAULT_AD_DURATION_SECONDS))
        if watched_seconds < required:
            return False, "Insufficient watch time"

        session["completed"] = True
        sessions[session_token] = session
        _save_sessions(sessions)

        state["completions"] = state.get("completions", 0) + 1
        _save_ad_state(state)

        return True, "ok"


def get_ad_stats() -> dict[str, Any]:
    with _state_lock:
        state = _load_ad_state()
        return {
            "impressions": state.get("impressions", 0),
            "completions": state.get("completions", 0),
            "active_ad": state.get("active_ad"),
        }


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
