from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlsplit

from aiohttp import ClientSession, ClientTimeout, web

from aiogram import Bot
from aiogram.types import BufferedInputFile, LabeledPrice

from app.ads import complete_ad_session, register_ad_click, start_ad_session
from app.crypto_payments import (
    create_crypto_order,
    get_order_by_id,
    get_order_by_provider_invoice_id,
    mark_order_paid,
)
from app.free_access import (
    DEFAULT_FREE_ACCESS_HOURS,
    format_free_access_remaining_text,
    grant_free_access,
    get_free_access_record,
    is_free_access_active,
    mark_free_access_peer_added,
)
from app.referrals import ensure_user, get_referral_invites, upsert_username
from app.personal_configs import list_active_personal_configs_for_user
from app.payment_webhooks import log_payment_webhook_event
from app.wireguard import add_peer_to_server, get_wireguard_config_filename, get_wireguard_config_text
from app.wireguard import ensure_wireguard_profile
from app.subscriptions import get_remaining_text, get_subscription_plan_name, get_subscription_record, is_subscription_active
from app.subscriptions import extend_subscription
from app.texts import FREE_ACCESS_ACTIVE_TEXT_TEMPLATE, FREE_ACCESS_GRANTED_TEXT_TEMPLATE
from app.date_format import format_human_datetime


PAYMENT_PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "basic": {
        "code": "basic",
        "name": "Базовый",
        "price_rub": 90,
        "price_rub_before_discount": 120,
        "discount_percent": 25,
        "days": 30,
        "stars": 158,
        "crypto_ton": 0.1,
    },
    "double": {
        "code": "double",
        "name": "Двойня",
        "price_rub": 184,
        "price_rub_before_discount": 230,
        "discount_percent": 20,
        "days": 30,
        "stars": 322,
        "crypto_ton": 0.26,
    },
    "trio": {
        "code": "trio",
        "name": "Трио",
        "price_rub": 289,
        "price_rub_before_discount": 340,
        "discount_percent": 15,
        "days": 30,
        "stars": 506,
        "crypto_ton": 0.4,
    },
    "together": {
        "code": "together",
        "name": "Вместе",
        "price_rub": 423,
        "price_rub_before_discount": 470,
        "discount_percent": 10,
        "days": 30,
        "stars": 740,
        "crypto_ton": 0.58,
    },
    "family": {
        "code": "family",
        "name": "Семейный",
        "price_rub": 531,
        "price_rub_before_discount": 590,
        "discount_percent": 10,
        "days": 30,
        "stars": 929,
        "crypto_ton": 0.73,
    },
}

DEFAULT_CRYPTO_TON_WALLET = "UQDNgjWaGw6Jau70YILv_MkiyiIkY24AVDrnfyAz9Pc4chca"
OWNER_ID = int(os.getenv("OWNER_ID", "1041865849"))


def _resolve_payment_plan(plan_code: str) -> dict[str, Any] | None:
    return PAYMENT_PLAN_CATALOG.get(plan_code)


def _build_template_payment_url(template: str, user_id: int, plan: dict[str, Any], method: str) -> str:
    order_id = f"{method}-{uuid.uuid4().hex[:10]}"
    return template.format(
        order_id=order_id,
        user_id=user_id,
        plan_code=plan["code"],
        plan_name=plan["name"],
        amount_rub=plan["price_rub"],
        days=plan["days"],
    )


def _ton_to_nanotons(value_ton: float) -> int:
    try:
        return max(0, int(round(float(value_ton) * 1_000_000_000)))
    except Exception:
        return 0


def _build_tonkeeper_payment_url(wallet_address: str, amount_ton: float, memo_text: str) -> str:
    amount_nano = _ton_to_nanotons(amount_ton)
    encoded_text = quote_plus(memo_text)
    return f"https://app.tonkeeper.com/transfer/{wallet_address}?amount={amount_nano}&text={encoded_text}"


def _cryptocloud_base_url() -> str:
    return os.getenv("CRYPTOCLOUD_API_BASE_URL", "https://api.cryptocloud.plus/v2").strip().rstrip("/")


def _cryptocloud_credentials() -> tuple[str, str]:
    api_token = os.getenv("CRYPTOCLOUD_API_TOKEN", "").strip()
    shop_id = os.getenv("CRYPTOCLOUD_SHOP_ID", "").strip()
    return api_token, shop_id


def _default_cryptocloud_webhook_url() -> str:
    configured = os.getenv("CRYPTOCLOUD_WEBHOOK_URL", "").strip()
    if configured:
        return configured

    mini_app_url = os.getenv("TELEGRAM_MINI_APP_URL", "").strip()
    if not mini_app_url:
        return ""

    try:
        parsed = urlsplit(mini_app_url)
    except Exception:
        return ""

    if parsed.scheme != "https" or not parsed.netloc:
        return ""

    return f"{parsed.scheme}://{parsed.netloc}/api/payment/cryptocloud/webhook"


async def _create_cryptocloud_invoice(
    *,
    user_id: int,
    plan: dict[str, Any],
    order_id: str,
) -> tuple[str, str | None]:
    api_token, shop_id = _cryptocloud_credentials()
    if not api_token or not shop_id:
        raise RuntimeError("CryptoCloud is not configured")

    callback_url = _default_cryptocloud_webhook_url()
    payload: dict[str, Any] = {
        "shop_id": shop_id,
        "amount": str(plan["price_rub"]),
        "currency": "RUB",
        "order_id": order_id,
        "desc": f"SkullVPN {plan['name']} ({plan['days']} дней) uid:{user_id}",
    }
    if callback_url:
        payload["callback_url"] = callback_url

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    timeout = ClientTimeout(total=20)
    endpoint = f"{_cryptocloud_base_url()}/invoice/create"
    async with ClientSession(timeout=timeout) as session:
        async with session.post(endpoint, json=payload, headers=headers) as response:
            body = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f"CryptoCloud HTTP {response.status}: {body}")

    result = body.get("result") if isinstance(body, dict) else None
    invoice_url = None
    provider_invoice_id = None
    if isinstance(result, dict):
        invoice_url = (
            result.get("link")
            or result.get("invoice_url")
            or result.get("url")
            or result.get("pay_url")
        )
        provider_invoice_id = (
            result.get("uuid")
            or result.get("invoice_id")
            or result.get("id")
        )

    if not isinstance(invoice_url, str) or not invoice_url:
        raise RuntimeError(f"CryptoCloud response missing payment url: {body}")

    if provider_invoice_id is not None and not isinstance(provider_invoice_id, str):
        provider_invoice_id = str(provider_invoice_id)

    return invoice_url, provider_invoice_id


def _extract_cryptocloud_order_id(payload: dict[str, Any]) -> str | None:
    candidates = [
        payload.get("order_id"),
        payload.get("merchant_order_id"),
    ]
    invoice_data = payload.get("invoice")
    if isinstance(invoice_data, dict):
        candidates.append(invoice_data.get("order_id"))
        candidates.append(invoice_data.get("merchant_order_id"))

    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _extract_cryptocloud_invoice_id(payload: dict[str, Any]) -> str | None:
    candidates = [
        payload.get("invoice_id"),
        payload.get("uuid"),
        payload.get("id"),
    ]
    invoice_data = payload.get("invoice")
    if isinstance(invoice_data, dict):
        candidates.extend([
            invoice_data.get("invoice_id"),
            invoice_data.get("uuid"),
            invoice_data.get("id"),
        ])

    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, int):
            return str(item)
    return None


def _is_cryptocloud_paid_status(payload: dict[str, Any]) -> bool:
    candidates: list[str] = []
    for key in ("status", "invoice_status", "payment_status"):
        value = payload.get(key)
        if isinstance(value, str):
            candidates.append(value.strip().lower())

    invoice_data = payload.get("invoice")
    if isinstance(invoice_data, dict):
        for key in ("status", "invoice_status", "payment_status"):
            value = invoice_data.get(key)
            if isinstance(value, str):
                candidates.append(value.strip().lower())

    paid_statuses = {"paid", "success", "completed", "succeeded", "overpaid", "partial_paid"}
    return any(item in paid_statuses for item in candidates)


def _verify_cryptocloud_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = os.getenv("CRYPTOCLOUD_WEBHOOK_SECRET", "").strip()
    if not secret:
        return True
    if not signature:
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


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


def _build_available_configs(
    user_id: int,
    free_record: dict[str, Any] | None,
    paid_record: dict[str, Any] | None,
    paid_plan_name: str,
) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []

    for personal_record in list_active_personal_configs_for_user(user_id):
        configs.append(
            {
                "tier": "blatnoy",
                "title": "Блатной",
                "tariffName": "Блатной",
                "keyValue": personal_record.get("config_id"),
                "configName": personal_record.get("config_filename"),
                "expiresAt": personal_record.get("expires_at"),
                "accessSource": "personal",
            }
        )

    if isinstance(free_record, dict):
        configs.append(
            {
                "tier": "free",
                "title": "Бесплатный",
                "tariffName": "Бесплатный доступ",
                "keyValue": free_record.get("access_key"),
                "configName": free_record.get("vpn_config_name"),
                "expiresAt": free_record.get("expires_at"),
                "accessSource": "free",
            }
        )

    if isinstance(paid_record, dict):
        configs.append(
            {
                "tier": "paid",
                "title": "Платный",
                "tariffName": paid_record.get("plan_name", paid_plan_name),
                "keyValue": paid_record.get("plan_name", paid_plan_name),
                "configName": paid_record.get("plan_name", paid_plan_name),
                "expiresAt": paid_record.get("expires_at"),
                "accessSource": "subscription",
            }
        )

    return configs


def _resolve_access_info(available_configs: list[dict[str, Any]]) -> dict[str, Any]:
    if not available_configs:
        return {
            "tier": "none",
            "key_title": "Нет доступа",
            "key_value": None,
            "config_name": None,
            "expires_at": None,
        }

    active_tiers = {str(item.get("tier") or "") for item in available_configs if isinstance(item, dict)}
    active_tiers.discard("")

    if len(active_tiers) >= 2:
        primary = available_configs[0]
        latest_expires_at = max(
            (str(item.get("expiresAt")) for item in available_configs if isinstance(item.get("expiresAt"), str) and item.get("expiresAt")),
            default=None,
        )
        return {
            "tier": "universal",
            "key_title": "Универсальный",
            "key_value": None,
            "config_name": f"{len(available_configs)} конфигов",
            "expires_at": latest_expires_at or primary.get("expiresAt"),
        }

    primary = available_configs[0]
    return {
        "tier": primary.get("tier") or "none",
        "key_title": primary.get("title") or "Нет доступа",
        "key_value": primary.get("keyValue"),
        "config_name": primary.get("configName"),
        "expires_at": primary.get("expiresAt"),
    }


def _build_state_payload(user_data: dict[str, Any]) -> dict[str, Any]:
    user_id = int(user_data["id"])
    referral = ensure_user(user_id, user_data.get("username"))
    referral_invites = get_referral_invites(user_id)
    free_record = get_free_access_record(user_id)
    paid_remaining = get_remaining_text(user_id)
    paid_plan_name = get_subscription_plan_name(user_id)
    paid_record = get_subscription_record(user_id)
    paid_active = is_subscription_active(user_id)
    free_active = is_free_access_active(user_id)
    free_remaining = format_free_access_remaining_text(user_id) if free_active else "0"
    available_configs = _build_available_configs(
        user_id,
        free_record if free_active else None,
        paid_record if paid_active else None,
        paid_plan_name,
    )
    access_info = _resolve_access_info(available_configs)

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
            "invites": referral_invites,
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
            "expires_at": paid_record["expires_at"] if paid_record else None,
            "active": paid_active,
        },
        "access_info": access_info,
        "available_configs": available_configs,
    }


async def _enrich_referral_invites_with_usernames(payload: dict[str, Any], bot: Bot | None) -> None:
    if bot is None:
        return

    referral = payload.get("referral") if isinstance(payload, dict) else None
    if not isinstance(referral, dict):
        return

    invites = referral.get("invites")
    if not isinstance(invites, list):
        return

    for invite in invites:
        if not isinstance(invite, dict):
            continue

        user_id = invite.get("user_id")
        username = invite.get("username")
        if not isinstance(user_id, int):
            continue

        needs_resolve = not isinstance(username, str) or not username or username.startswith("user_")
        if not needs_resolve:
            continue

        try:
            chat = await bot.get_chat(user_id)
            chat_username = getattr(chat, "username", None)
            if isinstance(chat_username, str) and chat_username:
                invite["username"] = chat_username
                upsert_username(user_id, chat_username)
        except Exception:
            continue


async def user_state(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        response_payload = _build_state_payload(user_data)
        await _enrich_referral_invites_with_usernames(response_payload, request.app.get("bot"))
        return web.json_response(response_payload)
    except web.HTTPException as exc:
        logging.warning("/api/user-state failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/user-state unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


def _chunk_text(value: str, chunk_size: int = 3500) -> list[str]:
    if not value:
        return []
    return [value[i : i + chunk_size] for i in range(0, len(value), chunk_size)]


async def claim_free_access(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        user_id = int(user_data["id"])

        ensure_user(user_id, user_data.get("username"))
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

        if record is None:
            logging.error("/api/claim-free-access produced empty record for user_id=%s", user_id)
            return web.json_response({"ok": False, "error": "Unable to provision free access"}, status=500)

        available_configs = _build_available_configs(
            user_id,
            record,
            None,
            "Базовый",
        )

        # Ensure peer is added to server only once per free access slot
        peer_added = record.get("peer_added_to_server", False) if record else False
        if not peer_added and record:
            peer_add_ok = add_peer_to_server(user_id)
            if peer_add_ok:
                mark_free_access_peer_added(user_id)
            else:
                logging.warning("Peer attach was skipped/failed for user_id=%s", user_id)

        response_payload: dict[str, Any]
        try:
            response_payload = _build_state_payload(user_data)
            await _enrich_referral_invites_with_usernames(response_payload, request.app.get("bot"))
        except Exception:
            logging.exception("Failed to build full state payload in /api/claim-free-access for user_id=%s", user_id)
            response_payload = {
                "ok": True,
                "user": {
                    "id": user_id,
                    "username": user_data.get("username"),
                    "first_name": user_data.get("first_name"),
                    "last_name": user_data.get("last_name"),
                },
                "referral": {
                    "referrer_id": None,
                    "invited_count": 0,
                    "bonus_days": 0,
                    "activated": False,
                    "invites": [],
                },
                "free_access": {
                    "active": True,
                    "access_key": record.get("access_key"),
                    "expires_at": record.get("expires_at"),
                    "remaining_text": format_free_access_remaining_text(user_id),
                    "source": record.get("source"),
                    "vpn_protocol": record.get("vpn_protocol"),
                    "vpn_profile_name": record.get("vpn_profile_name"),
                    "vpn_config_name": record.get("vpn_config_name"),
                    "vpn_configured": bool(record.get("vpn_configured", False)),
                },
                "paid_subscription": {
                    "plan_name": "none",
                    "remaining_text": "0",
                    "expires_at": None,
                    "active": False,
                },
                "access_info": _resolve_access_info(available_configs),
                "available_configs": available_configs,
            }

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
                expires_at=format_human_datetime(record["expires_at"]),
                remaining=format_free_access_remaining_text(user_id),
            )
            try:
                await bot.send_message(user_id, message_text, disable_web_page_preview=True)
                config_text = get_wireguard_config_text(user_id)
                if not config_text:
                    ensure_wireguard_profile(user_id)
                    config_text = get_wireguard_config_text(user_id)

                if config_text:
                    config_name = get_wireguard_config_filename(user_id)
                    try:
                        await bot.send_document(
                            user_id,
                            BufferedInputFile(config_text.encode("utf-8"), filename=config_name),
                            caption="Профиль WireGuard / AmneziaWG",
                        )
                    except Exception:
                        logging.exception("Failed to send .conf as document in /api/claim-free-access for user_id=%s", user_id)
                        await bot.send_message(
                            user_id,
                            "Не удалось отправить .conf файлом, отправляю конфиг текстом.",
                            disable_web_page_preview=True,
                        )
                        header = f"Имя файла: {config_name}\n"
                        for idx, part in enumerate(_chunk_text(config_text), start=1):
                            prefix = header if idx == 1 else ""
                            await bot.send_message(user_id, prefix + part, disable_web_page_preview=True)
                else:
                    logging.warning("WireGuard config text is empty for user_id=%s", user_id)
                    await bot.send_message(
                        user_id,
                        "Не удалось сформировать .conf автоматически. Напишите /getconf, отправим вручную.",
                        disable_web_page_preview=True,
                    )
            except Exception:
                logging.exception("Telegram notify step failed for user_id=%s", user_id)

        return web.json_response(response_payload)
    except web.HTTPException as exc:
        logging.warning("/api/claim-free-access failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/claim-free-access unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


async def ad_start(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        user_id = int(user_data["id"])

        ad, session_token = start_ad_session(user_id)
        if ad is None or not session_token:
            return web.json_response({"ok": False, "error": "No active ad"}, status=404)

        return web.json_response(
            {
                "ok": True,
                "session_token": session_token,
                "ad": {
                    "ad_id": ad.get("ad_id"),
                    "title": ad.get("title"),
                    "asset_url": ad.get("asset_url"),
                    "click_url": ad.get("click_url"),
                    "duration_sec": ad.get("duration_sec"),
                },
            }
        )
    except web.HTTPException as exc:
        logging.warning("/api/ad/start failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/ad/start unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


async def ad_complete(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        user_id = int(user_data["id"])

        session_token = str(payload.get("sessionToken", "")).strip()
        watched_raw = payload.get("watchedSeconds", 0)
        try:
            watched_seconds = int(watched_raw)
        except Exception:
            watched_seconds = 0

        ok, reason = complete_ad_session(user_id, session_token, watched_seconds)
        if not ok:
            return web.json_response({"ok": False, "error": reason}, status=400)

        return web.json_response({"ok": True})
    except web.HTTPException as exc:
        logging.warning("/api/ad/complete failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/ad/complete unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


async def ad_click(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        user_id = int(user_data["id"])

        session_token = str(payload.get("sessionToken", "")).strip()
        ok, reason = register_ad_click(user_id, session_token)
        if not ok:
            return web.json_response({"ok": False, "error": reason}, status=400)

        return web.json_response({"ok": True, "status": reason})
    except web.HTTPException as exc:
        logging.warning("/api/ad/click failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/ad/click unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


async def payment_create(request: web.Request) -> web.Response:
    try:
        payload = await _read_request_json(request)
        init_data = _init_data_from_payload(payload)
        user_data = _extract_user(init_data)
        user_id = int(user_data["id"])

        method = str(payload.get("method", "")).strip().lower()
        plan_code = str(payload.get("planCode", "")).strip().lower()
        plan = _resolve_payment_plan(plan_code)
        if plan is None:
            return web.json_response({"ok": False, "error": "Unknown tariff plan"}, status=400)

        if method == "telegram_stars":
            bot: Bot | None = request.app.get("bot")
            if bot is None:
                return web.json_response({"ok": False, "error": "Bot is not available"}, status=500)

            payload_token = f"stars:{plan['code']}:{user_id}:{plan['days']}"
            invoice_link = await bot.create_invoice_link(
                title=f"SkullVPN: {plan['name']}",
                description=f"Доступ к VPN на {plan['days']} дней",
                payload=payload_token,
                currency="XTR",
                prices=[LabeledPrice(label=plan["name"], amount=int(plan["stars"]))],
            )

            return web.json_response(
                {
                    "ok": True,
                    "method": method,
                    "plan": plan,
                    "invoice_url": invoice_link,
                }
            )

        if method == "sbp":
            template = os.getenv("PAYMENT_SBP_URL_TEMPLATE", "").strip()
            static_url = os.getenv("PAYMENT_SBP_URL", "").strip()
            if template:
                payment_url = _build_template_payment_url(template, user_id, plan, method)
            elif static_url:
                payment_url = static_url
            else:
                return web.json_response(
                    {
                        "ok": False,
                        "error": "SBP payment URL is not configured",
                    },
                    status=503,
                )

            return web.json_response(
                {
                    "ok": True,
                    "method": method,
                    "plan": plan,
                    "payment_url": payment_url,
                }
            )

        if method == "crypto":
            return web.json_response(
                {
                    "ok": False,
                    "error": "Crypto payment method is disabled",
                },
                status=400,
            )

        return web.json_response({"ok": False, "error": "Unsupported payment method"}, status=400)
    except web.HTTPException as exc:
        logging.warning("/api/payment/create failed: %s", exc.text)
        return web.json_response({"ok": False, "error": exc.text}, status=exc.status)
    except Exception:
        logging.exception("/api/payment/create unexpected error")
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


async def payment_cryptocloud_webhook(request: web.Request) -> web.Response:
    provider = "cryptocloud"
    event_type = "invoice_webhook"
    try:
        raw_body = await request.read()
        signature = (
            request.headers.get("X-Signature")
            or request.headers.get("X-CC-Signature")
            or request.headers.get("Signature")
        )
        if not _verify_cryptocloud_webhook_signature(raw_body, signature):
            log_payment_webhook_event(
                provider=provider,
                event_type=event_type,
                status="rejected",
                http_status=401,
                message="Invalid webhook signature",
            )
            return web.json_response({"ok": False, "error": "Invalid webhook signature"}, status=401)

        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            payload = {}

        if not isinstance(payload, dict):
            payload = {}

        order_id = _extract_cryptocloud_order_id(payload)
        provider_invoice_id = _extract_cryptocloud_invoice_id(payload)

        if not _is_cryptocloud_paid_status(payload):
            log_payment_webhook_event(
                provider=provider,
                event_type=event_type,
                status="ignored",
                http_status=200,
                message="Payment is not in paid status",
                order_id=order_id,
                provider_invoice_id=provider_invoice_id,
                payload=payload,
            )
            return web.json_response({"ok": True, "ignored": True, "reason": "Payment is not in paid status"})

        order = get_order_by_id(order_id) if order_id else None
        if order is None:
            if provider_invoice_id:
                order = get_order_by_provider_invoice_id(provider_invoice_id)

        if order is None:
            log_payment_webhook_event(
                provider=provider,
                event_type=event_type,
                status="rejected",
                http_status=404,
                message="Order not found",
                order_id=order_id,
                provider_invoice_id=provider_invoice_id,
                payload=payload,
            )
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)

        paid_record, is_first_paid = mark_order_paid(order["order_id"], payload)
        if paid_record is None:
            log_payment_webhook_event(
                provider=provider,
                event_type=event_type,
                status="rejected",
                http_status=404,
                message="Order not found during mark_paid",
                order_id=order.get("order_id") if isinstance(order, dict) else order_id,
                provider_invoice_id=provider_invoice_id,
                payload=payload,
            )
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)

        if not is_first_paid:
            log_payment_webhook_event(
                provider=provider,
                event_type=event_type,
                status="duplicate",
                http_status=200,
                message="Duplicate webhook for already paid order",
                order_id=str(paid_record.get("order_id") or order_id or ""),
                provider_invoice_id=provider_invoice_id,
                payload=payload,
            )
            return web.json_response({"ok": True, "duplicate": True})

        user_id = int(paid_record["user_id"])
        plan_name = str(paid_record["plan_name"])
        days = int(paid_record["days"])
        amount_rub = float(paid_record["amount_rub"])

        sub_record = extend_subscription(user_id, days, plan_name=plan_name)
        expires_at = sub_record.get("expires_at", "-")
        profile = ensure_wireguard_profile(user_id)
        profile_id = profile.get("profile_id", "-") if isinstance(profile, dict) else "-"
        config_name = get_wireguard_config_filename(user_id)
        config_text = get_wireguard_config_text(user_id)
        add_peer_to_server(user_id)

        bot: Bot | None = request.app.get("bot")
        if bot is not None:
            try:
                user_chat = await bot.get_chat(user_id)
                username = getattr(user_chat, "username", None)
            except Exception:
                username = None

            buyer_name = f"@{username}" if isinstance(username, str) and username else f"user_{user_id}"

            try:
                await bot.send_message(
                    OWNER_ID,
                    "✅ Успешная покупка подписки (CryptoCloud)\n\n"
                    f"Тариф: {plan_name}\n"
                    f"Сумма: {amount_rub:.2f} RUB\n"
                    f"Покупатель: {buyer_name}\n"
                    f"Telegram ID: {user_id}\n"
                    f"ID конфигуратора: {profile_id}\n"
                    f"Файл конфига: {config_name}\n"
                    f"Действует до: {expires_at}",
                )
            except Exception:
                logging.exception("Failed to notify owner about CryptoCloud purchase")

            try:
                await bot.send_message(
                    user_id,
                    "✅ Оплата получена\n\n"
                    f"Тариф: {plan_name}\n"
                    f"Сумма: {amount_rub:.2f} RUB\n"
                    f"Доступ продлён на {days} дней\n"
                    f"ID конфигуратора: {profile_id}\n"
                    f"Действует до: {expires_at}",
                )
            except Exception:
                logging.exception("Failed to notify user about CryptoCloud purchase user_id=%s", user_id)

            if config_text:
                try:
                    await bot.send_document(
                        user_id,
                        BufferedInputFile(config_text.encode("utf-8"), filename=config_name),
                        caption="Профиль WireGuard / AmneziaWG",
                    )
                except Exception:
                    logging.exception("Failed to send config after CryptoCloud purchase user_id=%s", user_id)

        log_payment_webhook_event(
            provider=provider,
            event_type=event_type,
            status="processed",
            http_status=200,
            message="Payment processed successfully",
            order_id=str(paid_record.get("order_id") or order_id or ""),
            provider_invoice_id=provider_invoice_id,
            payload=payload,
        )
        return web.json_response({"ok": True, "order_id": paid_record["order_id"]})
    except Exception:
        logging.exception("/api/payment/cryptocloud/webhook unexpected error")
        log_payment_webhook_event(
            provider=provider,
            event_type=event_type,
            status="error",
            http_status=500,
            message="Unexpected webhook exception",
        )
        return web.json_response({"ok": False, "error": "Internal server error"}, status=500)


def create_api_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/api/user-state", user_state)
    app.router.add_post("/api/claim-free-access", claim_free_access)
    app.router.add_post("/api/ad/start", ad_start)
    app.router.add_post("/api/ad/complete", ad_complete)
    app.router.add_post("/api/ad/click", ad_click)
    app.router.add_post("/api/payment/create", payment_create)
    app.router.add_post("/api/payment/cryptocloud/webhook", payment_cryptocloud_webhook)
    app.router.add_get("/healthz", lambda _request: web.json_response({"ok": True}))
    return app