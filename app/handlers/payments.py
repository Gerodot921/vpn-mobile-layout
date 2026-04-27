import logging
import os

from aiogram import F, Router
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery

from app.subscriptions import extend_subscription
from app.personal_configs import create_personal_configs, assign_personal_config_to_user, list_active_personal_configs_for_user
from app.wireguard import add_peer_to_server, ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_config_text
from app.date_format import format_human_datetime

router = Router()

OWNER_ID = int(os.getenv("OWNER_ID", "1041865849"))

TARIFF_MAX_CONFIGS = {
    "basic": 1,
    "double": 2,
    "trio": 3,
    "together": 4,
    "family": 5,
}


def _parse_stars_payload(payload: str) -> tuple[str, int, int] | None:
    # Format: stars:<plan_code>:<user_id>:<days>
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "stars":
        return None

    plan_code = parts[1].strip().lower()
    try:
        user_id = int(parts[2])
        days = int(parts[3])
    except Exception:
        return None

    if user_id <= 0 or days <= 0:
        return None
    return plan_code, user_id, days


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    if payment is None or not isinstance(payment.invoice_payload, str):
        return

    parsed = _parse_stars_payload(payment.invoice_payload)
    if parsed is None:
        return

    plan_code, user_id_from_payload, days = parsed
    user = message.from_user
    if user is None:
        return

    # Reject mismatched payloads to avoid extending someone else's subscription.
    if user.id != user_id_from_payload:
        logging.warning(
            "Ignoring successful payment with mismatched user_id: from_user=%s payload_user=%s",
            user.id,
            user_id_from_payload,
        )
        return

    plan_name_by_code = {
        "basic": "Базовый",
        "double": "Двойня",
        "trio": "Трио",
        "together": "Вместе",
        "family": "Семейный",
        # Legacy aliases for old paid plans.
        "standard": "Двойня",
        "premium": "Семейный",
    }
    plan_name = plan_name_by_code.get(plan_code, "Базовый")
    record = extend_subscription(user.id, days, plan_name=plan_name)
    expires_at = format_human_datetime(record.get("expires_at"))
    
    # For double+ tiers, create and assign personal configs
    max_configs = TARIFF_MAX_CONFIGS.get(plan_code, 1)
    first_config = None
    remaining_count = 0
    profile_id = "-"
    config_text = ""
    config_filename = ""
    
    if max_configs > 1:
        # Create multiple configs
        configs = create_personal_configs(count=max_configs, days=days, owner_user_id=user.id)
        
        # Assign first config to user
        if configs:
            first_config = configs[0]
            assign_personal_config_to_user(first_config["config_id"], user.id, user.username)
            remaining_count = len(configs) - 1
            
            # Log other configs for admin to activate them later
            if remaining_count > 0:
                logging.info(
                    "Created %d additional configs for user_id=%s after %s purchase. "
                    "User needs to click 'Активировать' button to unlock them.",
                    remaining_count,
                    user.id,
                    plan_name,
                )

    # Send initial message
    payment_message = (
        f"✅ Тариф '{plan_name}' успешно активирован!\n\n"
        f"Действует до: {expires_at}"
    )
    
    if max_configs > 1 and remaining_count > 0:
        payment_message += f"\n\n🔓 У вас есть {remaining_count} ещё заблокирован{'ных' if remaining_count > 1 else 'ный'} конфиг{'уратор' if remaining_count > 1 else ''}.\n"
        payment_message += "Нажмите 'Активировать' ниже, чтобы получить доступ к ним."
    
    keyboard = None
    if max_configs > 1 and remaining_count > 0:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔓 Активировать остальные конфиги", callback_data=f"activate_configs_{user.id}")],
            ]
        )
    
    try:
        await message.answer(payment_message, reply_markup=keyboard)
    except Exception:
        logging.exception("Failed to send payment confirmation message")
    
    # Send first config if created
    if first_config and max_configs > 1:
        profile_id = str(first_config.get("config_id") or "-")
        config_text = str(first_config.get("config_text") or "")
        config_filename = str(first_config.get("config_filename") or "skull-vpn-config.conf")

        if config_text:
            try:
                await message.answer_document(
                    BufferedInputFile(config_text.encode("utf-8"), filename=config_filename),
                    caption=f"Конфигуратор 1 из {max_configs}",
                )
            except Exception:
                logging.exception("Failed to send first personal config file")
    elif not first_config and max_configs == 1:
        # For basic tier, send WireGuard profile
        profile = ensure_wireguard_profile(user.id)
        profile_id = profile.get("profile_id", "-") if profile else "-"
        config_filename = get_wireguard_config_filename(user.id)
        config_text = get_wireguard_config_text(user.id)

        if profile is not None:
            add_peer_to_server(user.id)

        if config_text:
            try:
                await message.answer_document(
                    BufferedInputFile(config_text.encode("utf-8"), filename=config_filename),
                    caption="Ваш конфигуратор во вложении",
                )
            except Exception:
                logging.exception("Failed to send WireGuard config file")

    username = f"@{user.username}" if user.username else f"user_{user.id}"
    amount_text = f"{payment.total_amount} {payment.currency}"
    admin_message = (
        "✅ Успешная покупка подписки\n\n"
        f"Тариф: {plan_name}\n"
        f"Сумма: {amount_text}\n"
        f"Покупатель: {username}\n"
        f"Telegram ID: {user.id}\n"
        f"Действует до: {expires_at}"
    )
    
    if max_configs > 1 and remaining_count > 0:
        admin_message += f"\n🔓 Выдано конфигов: 1 из {max_configs}"

    try:
        await message.bot.send_message(OWNER_ID, admin_message)
    except Exception:
        logging.exception("Failed to notify owner about successful subscription purchase")

    await message.answer(
        "✅ Оплата получена\n\n"
        f"Тариф: {plan_name}\n"
        f"Сумма: {amount_text}\n"
        f"Доступ продлён на {days} дней\n"
        f"ID конфигуратора: {profile_id}\n"
        f"Действует до: {expires_at}"
    )

    if max_configs == 1 and config_text:
        try:
            await message.bot.send_document(
                user.id,
                BufferedInputFile(config_text.encode("utf-8"), filename=config_filename),
                caption="Ваш конфигуратор во вложении",
            )
        except Exception:
            logging.exception("Failed to send paid subscription config file to user_id=%s", user.id)
