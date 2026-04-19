from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, Message

from app.free_access import (
    DEFAULT_FREE_ACCESS_HOURS,
    format_free_access_remaining_text,
    grant_free_access,
)
from app.referrals import ensure_user
from app.subscriptions import ensure_subscription
from app.wireguard import add_peer_to_server, ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_config_text
from app.texts import FREE_ACCESS_ACTIVE_TEXT_TEMPLATE, FREE_ACCESS_GRANTED_TEXT_TEMPLATE

router = Router()


def _format_payload(data: str | None) -> dict[str, object]:
    if not data:
        return {}

    try:
        payload = json.loads(data)
    except Exception:
        return {"action": data}

    if isinstance(payload, dict):
        return payload
    return {}


@router.message(F.web_app_data)
async def webapp_data(message: Message) -> None:
    if not message.from_user or not message.web_app_data:
        return

    user_id = message.from_user.id
    ensure_user(user_id, message.from_user.username)
    ensure_subscription(user_id)

    payload = _format_payload(message.web_app_data.data)
    action = str(payload.get("action", "")).strip()

    if action != "claim_free_access":
        logging.info("Ignored web app action %s for user_id=%s", action or "<empty>", user_id)
        return

    hours_value = payload.get("hours", DEFAULT_FREE_ACCESS_HOURS)
    try:
        hours = int(hours_value)
    except Exception:
        hours = DEFAULT_FREE_ACCESS_HOURS

    record, created = grant_free_access(user_id, hours=hours)
    remaining_text = format_free_access_remaining_text(user_id)
    ensure_wireguard_profile(user_id)

    await message.answer(
        "✅ Реклама просмотрена, доступ выдан на 1 час.\n"
        "Конфиг и сообщение с данными отправляю ниже в этот чат.",
        disable_web_page_preview=True,
    )

    if created:
        await message.answer(
            FREE_ACCESS_GRANTED_TEXT_TEMPLATE.format(
                access_key=record["access_key"],
                expires_at=record["expires_at"],
                remaining=remaining_text,
            ),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(
            FREE_ACCESS_ACTIVE_TEXT_TEMPLATE.format(
                access_key=record["access_key"],
                expires_at=record["expires_at"],
                remaining=remaining_text,
            ),
            disable_web_page_preview=True,
        )

    config_text = get_wireguard_config_text(user_id)
    if config_text:
        filename = get_wireguard_config_filename(user_id)
        try:
            add_peer_to_server(user_id)
            await message.answer_document(
                BufferedInputFile(config_text.encode("utf-8"), filename=filename),
                caption="Профиль WireGuard / AmneziaWG",
            )
        except Exception:
            logging.exception("Failed to send WebApp .conf document for user_id=%s", user_id)
            await message.answer(f"Не удалось отправить файл документом. Конфиг:\n{filename}\n\n{config_text}")
    else:
        logging.warning("WireGuard config text is empty in webapp flow for user_id=%s", user_id)