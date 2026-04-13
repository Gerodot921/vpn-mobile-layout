from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from app.keyboards.inline import get_vpn_inline_keyboard
from app.referrals import bind_referrer_for_new_user, parse_referrer_id, register_user
from app.subscriptions import ensure_subscription
from app.texts import WELCOME_TEXT

router = Router()


@router.message(CommandStart())
async def start(message: Message, command: CommandObject | None = None) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    is_new_user = register_user(user_id, message.from_user.username)
    ensure_subscription(user_id)

    referrer_id = parse_referrer_id(command.args if command else None)
    if is_new_user and referrer_id is not None:
        bind_referrer_for_new_user(user_id, referrer_id)

    await message.answer(
        WELCOME_TEXT,
        reply_markup=get_vpn_inline_keyboard(),
    )
