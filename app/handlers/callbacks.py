import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from app.free_access import format_free_access_remaining_text, get_free_access_record
from app.personal_configs import activate_pending_personal_configs_for_user, list_pending_personal_configs_for_user
from app.keyboards.inline import (
    connect_inline_keyboard,
    get_vpn_inline_keyboard,
    issue_fix_step_one_keyboard,
    issue_fix_step_two_keyboard,
    post_connect_inline_keyboard,
    referral_program_keyboard,
    subscription_inline_keyboard,
    support_inline_keyboard,
)
from app.referrals import activate_user_and_apply_bonus, ensure_user
from app.wireguard import add_peer_to_server, ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_config_text
from app.texts import (
    CONNECTED_TEXT,
    DEMO_LINK_TEXT,
    FREE_ACCESS_ACTIVE_TEXT_TEMPLATE,
    FREE_ACCESS_GRANTED_TEXT_TEMPLATE,
    GET_VPN_STEPS_TEXT,
    INVITED_BONUS_TEXT,
    INVITER_BONUS_TEXT_TEMPLATE,
    ISSUE_STEP_ONE_TEXT,
    ISSUE_STEP_TWO_TEXT,
    PAYMENT_STUB_TEXT,
    REFERRAL_PROGRAM_TEXT_TEMPLATE,
    REFERRAL_TEXT_TEMPLATE,
    SUBSCRIPTION_TEXT,
    SUPPORT_STUB_TEXT,
    WELCOME_TEXT,
)
from app.date_format import format_human_datetime

router = Router()


async def _apply_referral_bonus_if_needed(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    user_id = callback.from_user.id
    referrer_id = activate_user_and_apply_bonus(user_id, callback.from_user.username)
    if referrer_id is None:
        return

    invited_user = callback.from_user
    if invited_user.username:
        invited_label = f"@{invited_user.username}"
    else:
        full_name = invited_user.full_name.strip()
        invited_label = full_name if full_name else f"user_{user_id}"

    logging.info(
        "Referral activation: referrer_id=%s invited_id=%s invited_username=%s",
        referrer_id,
        user_id,
        invited_user.username,
    )

    invitee_record = get_free_access_record(user_id)
    referrer_record = get_free_access_record(referrer_id)

    if callback.message:
        try:
            await callback.message.answer(INVITED_BONUS_TEXT)
            if invitee_record is not None:
                await callback.message.answer(
                    FREE_ACCESS_GRANTED_TEXT_TEMPLATE.format(
                        access_key=invitee_record["access_key"],
                        expires_at=format_human_datetime(invitee_record["expires_at"]),
                        remaining=format_free_access_remaining_text(user_id),
                    ),
                    disable_web_page_preview=True,
                )
        except Exception:
            pass

    try:
        await callback.bot.send_message(
            referrer_id,
            INVITER_BONUS_TEXT_TEMPLATE.format(
                invited_user=invited_label,
                invited_id=user_id,
            ),
        )
        if referrer_record is not None:
            await callback.bot.send_message(
                referrer_id,
                FREE_ACCESS_ACTIVE_TEXT_TEMPLATE.format(
                    access_key=referrer_record["access_key"],
                    expires_at=format_human_datetime(referrer_record["expires_at"]),
                    remaining=format_free_access_remaining_text(referrer_id),
                ),
                disable_web_page_preview=True,
            )
            ensure_wireguard_profile(referrer_id)
            referrer_config_text = get_wireguard_config_text(referrer_id)
            referrer_config_filename = get_wireguard_config_filename(referrer_id)
            if referrer_config_text:
                await callback.bot.send_document(
                    referrer_id,
                    BufferedInputFile(referrer_config_text.encode("utf-8"), filename=referrer_config_filename),
                    caption="Ваш конфигуратор во вложении",
                )
                add_peer_to_server(referrer_id)
    except Exception:
        pass

    if invitee_record is not None:
        ensure_wireguard_profile(user_id)
        invitee_config_text = get_wireguard_config_text(user_id)
        invitee_config_filename = get_wireguard_config_filename(user_id)
        if invitee_config_text:
            try:
                await callback.bot.send_document(
                    user_id,
                    BufferedInputFile(invitee_config_text.encode("utf-8"), filename=invitee_config_filename),
                    caption="Ваш конфигуратор во вложении",
                )
                add_peer_to_server(user_id)
            except Exception:
                pass


def _connected_demo_text() -> str:
    return f"{DEMO_LINK_TEXT}\n\n{CONNECTED_TEXT}"


async def _edit_callback_message(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
) -> None:
    if not callback.message:
        return

    await callback.message.edit_text(
        text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def _show_welcome(callback: CallbackQuery) -> None:
    await _edit_callback_message(
        callback,
        WELCOME_TEXT,
        reply_markup=get_vpn_inline_keyboard(),
    )


async def _show_get_vpn(callback: CallbackQuery) -> None:
    await _edit_callback_message(
        callback,
        GET_VPN_STEPS_TEXT,
        reply_markup=connect_inline_keyboard(),
    )


async def _show_connected(callback: CallbackQuery) -> None:
    await _edit_callback_message(
        callback,
        _connected_demo_text(),
        reply_markup=post_connect_inline_keyboard(),
    )


async def _show_issue_step_one(callback: CallbackQuery) -> None:
    await _edit_callback_message(
        callback,
        ISSUE_STEP_ONE_TEXT,
        reply_markup=issue_fix_step_one_keyboard(),
    )


async def _show_referral_program(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    user_id = callback.from_user.id
    user_data = ensure_user(user_id, callback.from_user.username)
    bot_info = await callback.bot.get_me()
    bot_username = bot_info.username or "your_bot"

    await _edit_callback_message(
        callback,
        REFERRAL_PROGRAM_TEXT_TEMPLATE.format(
            bot_username=bot_username,
            user_id=user_id,
            invited_count=user_data["invited_count"],
            bonus_days=user_data["bonus_days"],
        ),
        reply_markup=referral_program_keyboard(),
    )


@router.callback_query(F.data == "get_vpn")
async def get_vpn_flow(callback: CallbackQuery) -> None:
    await _apply_referral_bonus_if_needed(callback)
    await callback.answer()
    await _show_get_vpn(callback)


@router.callback_query(F.data == "install_and_connect")
async def install_and_connect(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_connected(callback)


@router.callback_query(F.data == "quick_connect")
async def quick_connect(callback: CallbackQuery) -> None:
    await _apply_referral_bonus_if_needed(callback)
    await callback.answer()
    await _show_connected(callback)


@router.callback_query(F.data == "issue_step_one")
async def issue_step_one(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_issue_step_one(callback)


@router.callback_query(F.data == "issue_step_two")
async def issue_step_two(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit_callback_message(
        callback,
        ISSUE_STEP_TWO_TEXT,
        reply_markup=issue_fix_step_two_keyboard(),
    )


@router.callback_query(F.data == "reconnect_after_fix")
async def reconnect_after_fix(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_connected(callback)


@router.callback_query(F.data == "open_subscription")
async def open_subscription(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit_callback_message(
        callback,
        SUBSCRIPTION_TEXT,
        reply_markup=subscription_inline_keyboard(),
    )


@router.callback_query(F.data == "open_referral_program")
async def open_referral_program(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_referral_program(callback)


@router.callback_query(F.data == "pay_stub")
async def pay_stub(callback: CallbackQuery) -> None:
    await callback.answer(PAYMENT_STUB_TEXT, show_alert=True)


@router.callback_query(F.data.startswith("activate_configs_"))
async def activate_configs(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    raw_target = callback.data.rsplit("_", 1)[-1] if callback.data else ""
    try:
        target_user_id = int(raw_target)
    except Exception:
        target_user_id = 0

    if target_user_id != callback.from_user.id:
        await callback.answer("Эта кнопка не для вас", show_alert=True)
        return

    pending_before = list_pending_personal_configs_for_user(target_user_id)
    if not pending_before:
        await callback.answer("Нет оставшихся конфигов для активации", show_alert=True)
        return

    activated = activate_pending_personal_configs_for_user(target_user_id, callback.from_user.username)
    if callback.message:
        config_lines = [f"• {record.get('config_filename', '-') }" for record in activated]
        summary = (
            f"✅ Активировано конфигов: {len(activated)}\n\n"
            + "\n".join(config_lines)
            + "\n\nОткрой Mini App заново, чтобы увидеть активированный ключ."
        )
        await callback.message.answer(summary, disable_web_page_preview=True)

    await callback.answer("Конфигураторы активированы")


@router.callback_query(F.data == "support_stub")
async def support_stub(callback: CallbackQuery) -> None:
    await callback.answer(SUPPORT_STUB_TEXT, show_alert=True)


@router.callback_query(F.data == "back_to_welcome")
async def back_to_welcome(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_welcome(callback)


@router.callback_query(F.data == "back_to_get_vpn")
async def back_to_get_vpn(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_get_vpn(callback)


@router.callback_query(F.data == "back_to_connected")
async def back_to_connected(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_connected(callback)


@router.callback_query(F.data == "back_to_issue_step_one")
async def back_to_issue_step_one(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_issue_step_one(callback)


@router.callback_query(F.data == "share_referral")
async def share_referral(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    user_id = callback.from_user.id
    user_data = ensure_user(user_id, callback.from_user.username)
    bot_info = await callback.bot.get_me()
    bot_username = bot_info.username or "your_bot"

    if callback.message:
        await callback.message.answer(
            REFERRAL_TEXT_TEMPLATE.format(
                bot_username=bot_username,
                user_id=user_id,
                invited_count=user_data["invited_count"],
                bonus_days=user_data["bonus_days"],
            ),
            disable_web_page_preview=True,
        )

    await callback.answer("Ссылка готова для отправки")
