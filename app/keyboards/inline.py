import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def _mini_app_url() -> str | None:
    url = os.getenv("TELEGRAM_MINI_APP_URL", "").strip()
    if url.startswith("https://"):
        return url
    return None


def mini_app_only_keyboard() -> InlineKeyboardMarkup:
    url = _mini_app_url()
    if not url:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ℹ️ Mini App URL не настроен",
                        callback_data="mini_app_not_configured",
                    )
                ]
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Открыть Mini App",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


def get_vpn_inline_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🚀 Получить VPN", callback_data="get_vpn")]]

    url = _mini_app_url()
    if url:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="📱 Открыть Mini App",
                    web_app=WebAppInfo(url=url),
                )
            ],
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def connect_inline_keyboard() -> InlineKeyboardMarkup:
    rows = []

    url = _mini_app_url()
    if url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 Открыть подключение в Mini App",
                    web_app=WebAppInfo(url=url),
                )
            ]
        )

    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="📲 Установить и подключиться",
                    callback_data="install_and_connect",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_welcome")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quick_connect_button_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="⚡ Подключиться", callback_data="quick_connect")]]

    url = _mini_app_url()
    if url:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="📱 Открыть Mini App",
                    web_app=WebAppInfo(url=url),
                )
            ],
        )

    rows.append([InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_welcome")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_connect_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Продлить доступ", callback_data="open_subscription")],
            [InlineKeyboardButton(text="❌ Не работает", callback_data="issue_step_one")],
            [
                InlineKeyboardButton(
                    text="🎁 Реферальная программа",
                    callback_data="open_referral_program",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_get_vpn")],
        ]
    )


def issue_fix_step_one_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить подключение",
                    callback_data="issue_step_two",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_connected")],
        ]
    )


def issue_fix_step_two_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Подключиться заново",
                    callback_data="reconnect_after_fix",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_issue_step_one")],
        ]
    )


def subscription_inline_keyboard(include_ad_renewal: bool = False) -> InlineKeyboardMarkup:
    url = _mini_app_url()

    if url:
        primary_text = "🎬 Продлить за рекламу в Mini App" if include_ad_renewal else "💳 Купить или продлить в Mini App"
        primary_button = InlineKeyboardButton(
            text=primary_text,
            web_app=WebAppInfo(url=url),
        )
    else:
        fallback_text = "ℹ️ Mini App URL не настроен"
        primary_button = InlineKeyboardButton(text=fallback_text, callback_data="mini_app_not_configured")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [primary_button],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_connected")],
        ]
    )


def support_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Написать в поддержку (заглушка)",
                    callback_data="support_stub",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_welcome")],
        ]
    )


def referral_share_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_referral")],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_welcome")],
        ]
    )


def referral_program_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_referral")],
            [InlineKeyboardButton(text="⬅️ Вернуться назад", callback_data="back_to_connected")],
        ]
    )
