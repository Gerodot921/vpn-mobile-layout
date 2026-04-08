from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Подключиться"), KeyboardButton(text="❌ Не работает")],
            [KeyboardButton(text="💎 Подписка"), KeyboardButton(text="🎁 Пригласить друга")],
            [KeyboardButton(text="📱 Mini App"), KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
        persistent=True,
        input_field_placeholder="Выбери действие",
    )
