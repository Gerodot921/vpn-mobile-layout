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
from app.date_format import format_human_datetime

router = Router()


def _chunk_text(value: str, chunk_size: int = 3500) -> list[str]:
    if not value:
        return []
    return [value[i : i + chunk_size] for i in range(0, len(value), chunk_size)]


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
    extend_requested = bool(payload.get("extend", False))
    try:
        hours = int(hours_value)
    except Exception:
        hours = DEFAULT_FREE_ACCESS_HOURS

    record, created = grant_free_access(user_id, hours=hours, extend_from_current=extend_requested)
    remaining_text = format_free_access_remaining_text(user_id)
    ensure_wireguard_profile(user_id)

    intro_text = (
        "✅ Реклама просмотрена, доступ продлён на 1 час.\n"
        "Конфиг и сообщение с данными отправляю ниже в этот чат."
        if extend_requested
        else "✅ Реклама просмотрена, доступ выдан на 1 час.\n"
        "Конфиг и сообщение с данными отправляю ниже в этот чат."
    )

    await message.answer(
        intro_text,
        disable_web_page_preview=True,
    )

    if created:
        await message.answer(
            FREE_ACCESS_GRANTED_TEXT_TEMPLATE.format(
                access_key=record["access_key"],
                expires_at=format_human_datetime(record["expires_at"]),
                remaining=remaining_text,
            ),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(
            FREE_ACCESS_ACTIVE_TEXT_TEMPLATE.format(
                access_key=record["access_key"],
                expires_at=format_human_datetime(record["expires_at"]),
                remaining=remaining_text,
            ),
            disable_web_page_preview=True,
        )

    config_text = get_wireguard_config_text(user_id)
    if not config_text:
        # Force regenerate once if profile exists but config text is missing.
        ensure_wireguard_profile(user_id)
        config_text = get_wireguard_config_text(user_id)

    if not config_text:
        logging.warning("WireGuard config text is empty in webapp flow for user_id=%s", user_id)
        await message.answer(
            "Не удалось сформировать .conf профиль автоматически. Напишите /getconf и мы отправим его вручную.",
            disable_web_page_preview=True,
        )
        return

    filename = get_wireguard_config_filename(user_id)
    add_peer_to_server(user_id)

    try:
        await message.answer_document(
            BufferedInputFile(config_text.encode("utf-8"), filename=filename),
            caption="Профиль WireGuard / AmneziaWG",
        )
        return
    except Exception:
        logging.exception("Failed to send WebApp .conf document in chat for user_id=%s", user_id)

    # Fallback 1: send file directly to user dialog.
    try:
        await message.bot.send_document(
            user_id,
            BufferedInputFile(config_text.encode("utf-8"), filename=filename),
            caption="Профиль WireGuard / AmneziaWG",
        )
        await message.answer(
            "Файл не отправился в этот чат, но мы отправили .conf в личные сообщения бота.",
            disable_web_page_preview=True,
        )
        return
    except Exception:
        logging.exception("Failed to send WebApp .conf document in DM for user_id=%s", user_id)

    # Fallback 2: send config as plain text chunks.
    await message.answer(
        "Не удалось отправить файл документом. Отправляю конфиг текстом ниже:",
        disable_web_page_preview=True,
    )
    header = f"Имя файла: {filename}\n"
    for idx, part in enumerate(_chunk_text(config_text), start=1):
        prefix = header if idx == 1 else ""
        await message.answer(prefix + part, disable_web_page_preview=True)