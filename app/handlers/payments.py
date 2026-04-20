import logging
import os

from aiogram import F, Router
from aiogram.types import BufferedInputFile, Message, PreCheckoutQuery

from app.subscriptions import extend_subscription
from app.wireguard import add_peer_to_server, ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_config_text, get_wireguard_profile
from app.date_format import format_human_datetime

router = Router()

OWNER_ID = int(os.getenv("OWNER_ID", "1041865849"))


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
        "standard": "Стандарт",
        "family": "Семейный",
        "premium": "Премиум",
    }
    plan_name = plan_name_by_code.get(plan_code, "Базовый")
    record = extend_subscription(user.id, days, plan_name=plan_name)
    expires_at = format_human_datetime(record.get("expires_at"))
    profile = ensure_wireguard_profile(user.id)
    profile_id = profile.get("profile_id", "-")
    config_filename = get_wireguard_config_filename(user.id)
    config_text = get_wireguard_config_text(user.id)

    if profile is not None:
        add_peer_to_server(user.id)

    username = f"@{user.username}" if user.username else f"user_{user.id}"
    amount_text = f"{payment.total_amount} {payment.currency}"
    admin_message = (
        "✅ Успешная покупка подписки\n\n"
        f"Тариф: {plan_name}\n"
        f"Сумма: {amount_text}\n"
        f"Покупатель: {username}\n"
        f"Telegram ID: {user.id}\n"
        f"ID конфигуратора: {profile_id}\n"
        f"Файл конфига: {config_filename}\n"
        f"Действует до: {expires_at}"
    )

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

    if config_text:
        try:
            await message.bot.send_document(
                user.id,
                BufferedInputFile(config_text.encode("utf-8"), filename=config_filename),
                caption="Профиль WireGuard / AmneziaWG",
            )
        except Exception:
            logging.exception("Failed to send paid subscription config to user_id=%s", user.id)
