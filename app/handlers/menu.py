import os

from aiogram import F, Router
from aiogram.types import Message

from app.keyboards.inline import (
    issue_fix_step_one_keyboard,
    mini_app_only_keyboard,
    quick_connect_button_keyboard,
    referral_share_keyboard,
    subscription_inline_keyboard,
    support_inline_keyboard,
)
from app.referrals import ensure_user
from app.texts import (
    FREE_ACCESS_PANEL_TEXT,
    HELP_TEXT,
    ISSUE_STEP_ONE_TEXT,
    MENU_CONNECT_TEXT,
    MINI_APP_ENTRY_TEXT,
    REFERRAL_TEXT_TEMPLATE,
    SUBSCRIPTION_TEXT,
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


async def _open_mini_app(message: Message) -> None:
    await message.answer(
        f"{FREE_ACCESS_PANEL_TEXT}\n\n{_mini_app_text_with_fallback()}",
        reply_markup=mini_app_only_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text == "🚀 Подключиться")
async def connect_menu(message: Message) -> None:
    await message.answer(MENU_CONNECT_TEXT, reply_markup=quick_connect_button_keyboard())


@router.message(F.text == "❌ Не работает")
async def issue_menu(message: Message) -> None:
    await message.answer(ISSUE_STEP_ONE_TEXT, reply_markup=issue_fix_step_one_keyboard())


@router.message(F.text == "💎 Подписка")
async def subscription_menu(message: Message) -> None:
    await message.answer(SUBSCRIPTION_TEXT, reply_markup=subscription_inline_keyboard())


@router.message(F.text == "🎁 Пригласить друга")
async def referral_menu(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    user_data = ensure_user(user_id, message.from_user.username)
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username or "your_bot"

    await message.answer(
        REFERRAL_TEXT_TEMPLATE.format(
            bot_username=bot_username,
            user_id=user_id,
            invited_count=user_data["invited_count"],
            bonus_days=user_data["bonus_days"],
        ),
        reply_markup=referral_share_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text == "ℹ️ Помощь")
async def help_menu(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=support_inline_keyboard())


@router.message(F.text == "📱 Mini App")
async def mini_app_menu(message: Message) -> None:
    await _open_mini_app(message)


@router.message(F.text == "🎬 Бесплатный VPN")
async def free_vpn_menu(message: Message) -> None:
    await _open_mini_app(message)
