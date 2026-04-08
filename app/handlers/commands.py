import asyncio
import os

from aiogram import Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards.inline import mini_app_only_keyboard
from app.keyboards.inline import subscription_inline_keyboard
from app.subscriptions import ensure_subscription, get_remaining_text, get_subscription_plan_name
from app.texts import (
    MINI_APP_ENTRY_TEXT,
    MINI_APP_NOT_CONFIGURED_TEXT,
    SUBSCRIPTION_REMINDER_TEXT_TEMPLATE,
)

router = Router()


def _mini_app_text_with_fallback() -> str:
    url = os.getenv("TELEGRAM_MINI_APP_URL", "").strip()
    if url.startswith("https://"):
        return (
            f"{MINI_APP_ENTRY_TEXT}\n\n"
            f"Если кнопка не сработала, откройте ссылку вручную:\n{url}"
        )
    return MINI_APP_ENTRY_TEXT


@router.message(Command(commands=["clear_chat", "ckear_chat"]))
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


@router.message(Command(commands=["miniapp"]))
async def open_mini_app(message: Message) -> None:
    await message.answer(
        _mini_app_text_with_fallback(),
        reply_markup=mini_app_only_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(Command(commands=["getsms"]))
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
