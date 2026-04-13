from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any
from urllib.parse import parse_qsl

from aiohttp import web

from aiogram import Bot
from aiogram.types import BufferedInputFile

from app.free_access import (
    DEFAULT_FREE_ACCESS_HOURS,
    format_free_access_remaining_text,
    grant_free_access,
    get_free_access_record,
    is_free_access_active,
    mark_free_access_peer_added,
)
from app.referrals import ensure_user
from app.wireguard import add_peer_to_server, get_wireguard_config_filename, get_wireguard_config_text
from app.wireguard import ensure_wireguard_profile
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
            "vpn_protocol": free_record["vpn_protocol"] if free_record else None,
            "vpn_profile_name": free_record["vpn_profile_name"] if free_record else None,
            "vpn_config_name": free_record["vpn_config_name"] if free_record else None,
            "vpn_configured": free_record["vpn_configured"] if free_record else False,
        },
        "paid_subscription": {
            "plan_name": paid_plan_name,
            "remaining_text": paid_remaining,
        },
    }


async def user_state(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        return web.json_response(_build_state_payload(user_data))
    except web.HTTPException as exc:
        logging.warning("/api/user-state failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/user-state unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


async def claim_free_access(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        user_id = int(user_data["id"])

        ensure_user(user_id)
        ensure_wireguard_profile(user_id)

        if is_free_access_active(user_id):
            record = get_free_access_record(user_id)
            if record is None:
                record, _ = grant_free_access(user_id, DEFAULT_FREE_ACCESS_HOURS, source="mini_app_ad", force_extend=False)
            created = False
            action_label = record["source"] if record else "mini_app_ad"
        else:
            record, created = grant_free_access(user_id, DEFAULT_FREE_ACCESS_HOURS, source="mini_app_ad", force_extend=False)
            action_label = "mini_app_ad"

        # Ensure peer is added to server only once per free access slot
        peer_added = record.get("peer_added_to_server", False) if record else False
        if not peer_added and record:
            add_peer_to_server(user_id)
            mark_free_access_peer_added(user_id)

        response_payload = _build_state_payload(user_data)
        response_payload["claim"] = {
            "created": created,
            "action": action_label,
            "access_key": record["access_key"],
            "expires_at": record["expires_at"],
            "remaining_text": format_free_access_remaining_text(user_id),
            "vpn_protocol": record["vpn_protocol"],
            "vpn_profile_name": record["vpn_profile_name"],
            "vpn_config_name": record["vpn_config_name"],
            "vpn_configured": record["vpn_configured"],
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
                config_text = get_wireguard_config_text(user_id)
                if config_text:
                    config_name = get_wireguard_config_filename(user_id)
                    await bot.send_document(
                        user_id,
                        BufferedInputFile(config_text.encode("utf-8"), filename=config_name),
                        caption="Профиль WireGuard / AmneziaWG",
                    )
                else:
                    logging.warning("WireGuard config text is empty for user_id=%s", user_id)
            except Exception:
                logging.exception("Telegram notify step failed for user_id=%s", user_id)

        return web.json_response(response_payload)
    except web.HTTPException as exc:
        logging.warning("/api/claim-free-access failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/claim-free-access unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


def create_api_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/api/user-state", user_state)
    app.router.add_post("/api/claim-free-access", claim_free_access)
    app.router.add_get("/healthz", lambda _request: web.json_response({"ok": True}))
    return app