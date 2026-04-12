from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any
from urllib.parse import parse_qsl

from aiohttp import web

from aiogram import Bot

from app.free_access import (
    format_free_access_remaining_text,
    grant_free_access,
    get_free_access_record,
    is_free_access_active,
)
from app.referrals import ensure_user
from app.subscriptions import get_remaining_text, get_subscription_plan_name
from app.texts import FREE_ACCESS_ACTIVE_TEXT_TEMPLATE, FREE_ACCESS_GRANTED_TEXT_TEMPLATE


def _bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise web.HTTPInternalServerError(text="TELEGRAM_BOT_TOKEN is not configured")
    return token


def _parse_init_data(raw_init_data: str) -> dict[str, str]:
    parsed = dict(parse_qsl(raw_init_data, keep_blank_values=True))
    provided_hash = parsed.pop("hash", None)
    if not provided_hash:
        raise web.HTTPUnauthorized(text="Missing Telegram initData hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", _bot_token().encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, provided_hash):
        raise web.HTTPUnauthorized(text="Invalid Telegram initData")

    return parsed


def _extract_user(init_data: str) -> dict[str, Any]:
    parsed = _parse_init_data(init_data)
    raw_user = parsed.get("user")
    if not raw_user:
        raise web.HTTPUnauthorized(text="Telegram user payload is missing")

    try:
        user_data = json.loads(raw_user)
    except Exception as exc:
        raise web.HTTPUnauthorized(text="Telegram user payload is invalid") from exc

    if not isinstance(user_data, dict) or not isinstance(user_data.get("id"), int):
        raise web.HTTPUnauthorized(text="Telegram user payload is invalid")

    return user_data


async def _read_request_json(request: web.Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if isinstance(payload, dict):
        return payload
    return {}


def _init_data_from_payload(payload: dict[str, Any]) -> str:
    init_data = payload.get("initData") or payload.get("init_data") or payload.get("init_data_raw")
    if isinstance(init_data, str) and init_data.strip():
        return init_data.strip()
    raise web.HTTPBadRequest(text="initData is required")


def _build_state_payload(user_data: dict[str, Any]) -> dict[str, Any]:
    user_id = int(user_data["id"])
    referral = ensure_user(user_id)
    free_record = get_free_access_record(user_id)
    paid_remaining = get_remaining_text(user_id)
    paid_plan_name = get_subscription_plan_name(user_id)

    free_active = is_free_access_active(user_id)
    free_remaining = format_free_access_remaining_text(user_id) if free_active else "0"

    return {
        "ok": True,
        "user": {
            "id": user_id,
            "username": user_data.get("username"),
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
        },
        "referral": {
            "referrer_id": referral["referrer_id"],
            "invited_count": referral["invited_count"],
            "bonus_days": referral["bonus_days"],
            "activated": referral["activated"],
        },
        "free_access": {
            "active": free_active,
            "access_key": free_record["access_key"] if free_record else None,
            "expires_at": free_record["expires_at"] if free_record else None,
            "remaining_text": free_remaining,
            "source": free_record["source"] if free_record else None,
        },
        "paid_subscription": {
            "plan_name": paid_plan_name,
            "remaining_text": paid_remaining,
        },
    }


async def user_state(request: web.Request) -> web.Response:
    payload = await _read_request_json(request)
    init_data = _init_data_from_payload(payload)
    user_data = _extract_user(init_data)
    return web.json_response(_build_state_payload(user_data))


async def claim_free_access(request: web.Request) -> web.Response:
    payload = await _read_request_json(request)
    init_data = _init_data_from_payload(payload)
    user_data = _extract_user(init_data)
    user_id = int(user_data["id"])

    referral = ensure_user(user_id)

    if is_free_access_active(user_id):
        record = get_free_access_record(user_id)
        if record is None:
            record, _ = grant_free_access(user_id, 2, source="mini_app_ad", force_extend=False)
        created = False
        action_label = record["source"] if record else "mini_app_ad"
    else:
        record, created = grant_free_access(user_id, 2, source="mini_app_ad", force_extend=False)
        action_label = "mini_app_ad"

    response_payload = _build_state_payload(user_data)
    response_payload["claim"] = {
        "created": created,
        "action": action_label,
        "access_key": record["access_key"],
        "expires_at": record["expires_at"],
        "remaining_text": format_free_access_remaining_text(user_id),
    }

    bot: Bot | None = request.app.get("bot")
    if bot is not None:
        message_text = (
            FREE_ACCESS_GRANTED_TEXT_TEMPLATE
            if created
            else FREE_ACCESS_ACTIVE_TEXT_TEMPLATE
        ).format(
            access_key=record["access_key"],
            expires_at=record["expires_at"],
            remaining=format_free_access_remaining_text(user_id),
        )
        try:
            await bot.send_message(user_id, message_text, disable_web_page_preview=True)
        except Exception:
            pass

    return web.json_response(response_payload)


def create_api_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/api/user-state", user_state)
    app.router.add_post("/api/claim-free-access", claim_free_access)
    app.router.add_get("/healthz", lambda _request: web.json_response({"ok": True}))
    return app