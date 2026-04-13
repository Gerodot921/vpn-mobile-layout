import asyncio
import logging
import os

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.keyboards.inline import mini_app_only_keyboard
from app.keyboards.inline import subscription_inline_keyboard
from app.subscriptions import ensure_subscription, get_remaining_text, get_subscription_plan_name
from app.texts import (
    FREE_ACCESS_PANEL_TEXT,
    MINI_APP_ENTRY_TEXT,
    MINI_APP_NOT_CONFIGURED_TEXT,
    SUBSCRIPTION_REMINDER_TEXT_TEMPLATE,
)
from app.wireguard import add_peer_to_server, ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_config_text, reset_wireguard_profile

# Owner ID for admin commands
OWNER_ID = int(os.getenv("OWNER_ID", "1041865849"))

router = Router()


def _is_owner(message: Message) -> bool:
    """Check if the user is the owner."""
    return message.from_user and message.from_user.id == OWNER_ID


def _mini_app_text_with_fallback() -> str:
    url = os.getenv("TELEGRAM_MINI_APP_URL", "").strip()
    if url.startswith("https://"):
        return (
            f"{MINI_APP_ENTRY_TEXT}\n\n"
            f"Если кнопка не сработала, откройте ссылку вручную:\n{url}"
        )
    return MINI_APP_ENTRY_TEXT


@router.message(Command(commands=["clear_chat", "ckear_chat"]), F.func(_is_owner))
async def clear_chat(message: Message) -> None:
    chat = message.chat
    last_message_id = message.message_id
    first_message_id = 1
    failed_streak = 0

    for msg_id in range(last_message_id, first_message_id - 1, -1):
        try:
            await message.bot.delete_message(chat_id=chat.id, message_id=msg_id)
            failed_streak = 0
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.1)
            try:
                await message.bot.delete_message(chat_id=chat.id, message_id=msg_id)
                failed_streak = 0
            except Exception:
                failed_streak += 1
        except Exception:
            failed_streak += 1

        # Stop when too many sequential messages cannot be deleted.
        if failed_streak >= 300:
            break


@router.message(Command(commands=["miniapp"]), F.func(_is_owner))
async def open_mini_app(message: Message) -> None:
    await message.answer(
        f"{FREE_ACCESS_PANEL_TEXT}\n\n{_mini_app_text_with_fallback()}",
        reply_markup=mini_app_only_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(Command(commands=["freevpn"]), F.func(_is_owner))
async def open_free_vpn(message: Message) -> None:
    await message.answer(
        f"{FREE_ACCESS_PANEL_TEXT}\n\n{_mini_app_text_with_fallback()}",
        reply_markup=mini_app_only_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(Command(commands=["getsms"]), F.func(_is_owner))
async def get_sms(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    ensure_subscription(user_id)
    remaining_text = get_remaining_text(user_id)
    plan_name = get_subscription_plan_name(user_id)

    await message.answer(
        SUBSCRIPTION_REMINDER_TEXT_TEMPLATE.format(
            remaining=remaining_text,
            plan_name=plan_name,
        ),
        reply_markup=subscription_inline_keyboard(),
        disable_web_page_preview=True,
    )


@router.callback_query(lambda c: c.data == "mini_app_not_configured")
async def mini_app_not_configured(callback: CallbackQuery) -> None:
    await callback.answer(MINI_APP_NOT_CONFIGURED_TEXT, show_alert=True)


@router.message(Command(commands=["profile", "wg", "conf"]), F.func(_is_owner))
async def send_wireguard_profile(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    ensure_wireguard_profile(user_id)
    config_text = get_wireguard_config_text(user_id)

    if not config_text:
        await message.answer("Не удалось собрать профиль. Попробуйте еще раз через 10 секунд.")
        return

    peer_added = add_peer_to_server(user_id)
    if not peer_added:
        logging.warning("Peer was not added before sending profile for user_id=%s", user_id)

    filename = get_wireguard_config_filename(user_id)

    try:
        await message.answer_document(
            BufferedInputFile(config_text.encode("utf-8"), filename=filename),
            caption="Ваш профиль WireGuard / AmneziaWG (.conf)",
        )
    except Exception:
        logging.exception("Failed to send .conf document for user_id=%s", user_id)
        await message.answer(
            "Не удалось отправить файл как документ. Ниже отправляю конфиг текстом:"
        )
        await message.answer(f"{filename}\n\n{config_text}")


@router.message(F.text.in_({"profile", "Profile", "профиль", "конфиг", "config"}), F.func(_is_owner))
async def send_wireguard_profile_text_alias(message: Message) -> None:
    await send_wireguard_profile(message)


@router.message(Command(commands=["profile_reset", "wg_reset"]), F.func(_is_owner))
async def reset_and_send_wireguard_profile(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    reset_wireguard_profile(user_id)
    await message.answer("Профиль сброшен. Отправляю новый .conf")
    await send_wireguard_profile(message)
