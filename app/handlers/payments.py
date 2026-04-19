import logging

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from app.subscriptions import extend_subscription

router = Router()


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
    expires_at = record.get("expires_at", "-")

    await message.answer(
        "✅ Оплата получена\n\n"
        f"Тариф: {plan_name}\n"
        f"Доступ продлён на {days} дней\n"
        f"Действует до: {expires_at}"
    )
