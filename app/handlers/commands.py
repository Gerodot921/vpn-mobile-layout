import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.keyboards.inline import mini_app_only_keyboard
from app.keyboards.inline import subscription_inline_keyboard
from app.free_access import get_total_free_claims, get_total_free_users, list_active_free_access_records
from app.personal_configs import create_personal_configs, delete_personal_config, list_active_personal_configs, list_personal_configs, revoke_expired_personal_configs
from app.subscriptions import ensure_subscription, get_remaining_text, get_subscription_plan_name
from app.subscriptions import list_active_subscriptions
from app.texts import (
    FREE_ACCESS_PANEL_TEXT,
    MINI_APP_ENTRY_TEXT,
    MINI_APP_NOT_CONFIGURED_TEXT,
    SUBSCRIPTION_REMINDER_TEXT_TEMPLATE,
)
from app.wireguard import add_peer_to_server, ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_config_text, get_wireguard_profile, list_peer_endpoints, reset_wireguard_profile

# Owner ID for admin commands
OWNER_ID = int(os.getenv("OWNER_ID", "1041865849"))

router = Router()


def _is_owner(message: Message) -> bool:
    """Check if the user is the owner."""
    return message.from_user and message.from_user.id == OWNER_ID


def _fmt_dt(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return value


async def _resolve_user_label(message: Message, user_id: int) -> str:
    try:
        chat = await message.bot.get_chat(user_id)
        username = getattr(chat, "username", None)
        if isinstance(username, str) and username:
            return f"@{username}"
    except Exception:
        pass
    return "@unknown"


def _endpoint_to_ip(endpoint: str | None) -> str:
    if not isinstance(endpoint, str) or not endpoint or endpoint == "(none)":
        return "-"

    endpoint = endpoint.strip()
    if endpoint.startswith("[") and "]:" in endpoint:
        return endpoint[1:].split("]:", 1)[0]

    if endpoint.count(":") == 1:
        return endpoint.rsplit(":", 1)[0]

    # Fallback for unexpected formats.
    return endpoint


async def _build_free_stats_lines(message: Message) -> list[str]:
    active_free = list_active_free_access_records()
    peer_endpoints = list_peer_endpoints()

    lines: list[str] = []
    lines.append("🟢 Статистика бесплатных VPN")
    lines.append("")
    lines.append(f"Бесплатный конфиг получали (раз): {get_total_free_claims()}")
    lines.append(f"Пользовались бесплатным конфигом (уникальных): {get_total_free_users()}")
    lines.append(f"Активных бесплатных: {len(active_free)}")
    lines.append("")

    if not active_free:
        lines.append("Нет активных")
        return lines

    for user_id, record in sorted(active_free.items(), key=lambda item: item[1].get("expires_at", "")):
        user_label = await _resolve_user_label(message, user_id)
        config_name = record.get("vpn_config_name") or "-"
        expires_at = _fmt_dt(record.get("expires_at", "-"))
        profile = get_wireguard_profile(user_id)
        public_key = profile.get("public_key", "") if profile else ""
        endpoint_ip = _endpoint_to_ip(peer_endpoints.get(public_key))
        lines.append(f"{user_label} | id={user_id} | ip={endpoint_ip} | config={config_name} | до={expires_at}")

    return lines


async def _build_paid_stats_lines(message: Message) -> list[str]:
    active_paid = list_active_subscriptions()
    peer_endpoints = list_peer_endpoints()

    lines: list[str] = []
    lines.append("💎 Статистика платных VPN")
    lines.append("")
    lines.append(f"Активных платных: {len(active_paid)}")
    lines.append("")

    if not active_paid:
        lines.append("Нет активных")
        return lines

    for user_id, record in sorted(active_paid.items(), key=lambda item: item[1].get("expires_at", "")):
        user_label = await _resolve_user_label(message, user_id)
        profile = get_wireguard_profile(user_id)
        config_name = profile.get("config_filename", "-") if profile else "-"
        public_key = profile.get("public_key", "") if profile else ""
        endpoint_ip = _endpoint_to_ip(peer_endpoints.get(public_key))
        expires_at = _fmt_dt(record.get("expires_at", "-"))
        lines.append(f"{user_label} | id={user_id} | ip={endpoint_ip} | config={config_name} | до={expires_at}")

    return lines


def _build_personal_stats_lines() -> list[str]:
    revoked = revoke_expired_personal_configs()
    all_configs = list_personal_configs()
    active = list_active_personal_configs()
    peer_endpoints = list_peer_endpoints()

    lines: list[str] = []
    lines.append("🧩 Статистика персональных конфигов")
    lines.append("")
    lines.append(f"Всего персональных: {len(all_configs)}")
    lines.append(f"Активных персональных: {len(active)}")
    lines.append(f"Авто-отозвано по сроку сейчас: {revoked}")
    lines.append("")

    if not all_configs:
        lines.append("Нет созданных персональных конфигов")
        return lines

    for record in sorted(all_configs, key=lambda item: item.get("expires_at", "")):
        status = "active"
        revoked_at = record.get("revoked_at")
        expires_at_raw = record.get("expires_at", "")
        try:
            if revoked_at:
                status = "revoked"
            else:
                expires_dt = datetime.fromisoformat(expires_at_raw)
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                else:
                    expires_dt = expires_dt.astimezone(timezone.utc)
                if expires_dt <= datetime.now(timezone.utc):
                    status = "expired"
        except Exception:
            pass

        endpoint_ip = _endpoint_to_ip(peer_endpoints.get(record.get("public_key", "")))
        lines.append(
            "{cfg} | ip={ip} | status={status} | до={exp}".format(
                cfg=record.get("config_filename", "-"),
                ip=endpoint_ip,
                status=status,
                exp=_fmt_dt(record.get("expires_at", "-")),
            )
        )

    return lines


async def _send_lines_report(message: Message, lines: list[str]) -> None:
    report = "\n".join(lines)
    if len(report) <= 3900:
        await message.answer(report)
        return

    for start in range(0, len(lines), 45):
        chunk = "\n".join(lines[start:start + 45])
        await message.answer(chunk)


def _build_admin_help_lines() -> list[str]:
    return [
        "🛠 Админ-команды",
        "",
        "/allstatb — статистика бесплатных VPN",
        "/allstatp — статистика платных VPN",
        "/allstatpers — статистика персональных конфигов",
        "/allstat — общая статистика по всем типам",
        "/create <n> <m> — создать n персональных конфигов на m дней",
        "/delete <config_id> — удалить персональный конфиг по ID",
        "/profile_reset — сбросить личный VPN-профиль",
        "/clear_chat — очистить чат",
    ]


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


@router.message(Command(commands=["allstat"]), F.func(_is_owner))
async def all_stat(message: Message) -> None:
    free_total_claims = get_total_free_claims()
    free_total_users = get_total_free_users()
    active_free = list_active_free_access_records()
    active_paid = list_active_subscriptions()
    peer_endpoints = list_peer_endpoints()

    lines: list[str] = []
    lines.append("📊 Общая статистика")
    lines.append("")
    lines.append(f"Бесплатный конфиг получали (раз): {free_total_claims}")
    lines.append(f"Пользовались бесплатным конфигом (уникальных): {free_total_users}")
    lines.append(f"Активных бесплатных: {len(active_free)}")
    lines.append(f"Активных платных: {len(active_paid)}")
    lines.append("")
    lines.append("🟢 Бесплатные подписки")

    if not active_free:
        lines.append("Нет активных")
    else:
        for user_id, record in sorted(active_free.items(), key=lambda item: item[1].get("expires_at", "")):
            user_label = await _resolve_user_label(message, user_id)
            config_name = record.get("vpn_config_name") or "-"
            expires_at = _fmt_dt(record.get("expires_at", "-"))
            profile = get_wireguard_profile(user_id)
            public_key = profile.get("public_key", "") if profile else ""
            endpoint_ip = _endpoint_to_ip(peer_endpoints.get(public_key))
            lines.append(f"{user_label} | id={user_id} | ip={endpoint_ip} | config={config_name} | до={expires_at}")

    lines.append("")
    lines.append("💎 Платные подписки")
    if not active_paid:
        lines.append("Нет активных")
    else:
        for user_id, record in sorted(active_paid.items(), key=lambda item: item[1].get("expires_at", "")):
            user_label = await _resolve_user_label(message, user_id)
            profile = get_wireguard_profile(user_id)
            config_name = profile.get("config_filename", "-") if profile else "-"
            expires_at = _fmt_dt(record.get("expires_at", "-"))
            public_key = profile.get("public_key", "") if profile else ""
            endpoint_ip = _endpoint_to_ip(peer_endpoints.get(public_key))
            lines.append(f"{user_label} | id={user_id} | ip={endpoint_ip} | config={config_name} | до={expires_at}")

    report = "\n".join(lines)
    if len(report) <= 3900:
        await message.answer(report)
        return

    for start in range(0, len(lines), 45):
        chunk = "\n".join(lines[start:start + 45])
        await message.answer(chunk)


@router.message(Command(commands=["allstatb"]), F.func(_is_owner))
async def all_stat_free(message: Message) -> None:
    await _send_lines_report(message, await _build_free_stats_lines(message))


@router.message(Command(commands=["allstatp"]), F.func(_is_owner))
async def all_stat_paid(message: Message) -> None:
    await _send_lines_report(message, await _build_paid_stats_lines(message))


@router.message(Command(commands=["allstatpers"]), F.func(_is_owner))
async def all_stat_personal(message: Message) -> None:
    await _send_lines_report(message, _build_personal_stats_lines())


@router.message(Command(commands=["create"]), F.func(_is_owner))
async def create_personal_configs_command(message: Message, command: CommandObject | None = None) -> None:
    args = (command.args or "").split() if command else []
    if len(args) != 2:
        await message.answer("Формат: /create <кол-во_конфигов> <кол-во_дней>\nПример: /create 3 30")
        return

    try:
        count = int(args[0])
        days = int(args[1])
    except Exception:
        await message.answer("n и m должны быть числами. Пример: /create 3 30")
        return

    if count <= 0 or days <= 0:
        await message.answer("n и m должны быть больше 0")
        return

    records = create_personal_configs(count=count, days=days)
    await message.answer(f"Создано персональных конфигов: {len(records)} (срок: {days} дн.)")

    for record in records:
        try:
            await message.answer_document(
                BufferedInputFile(record["config_text"].encode("utf-8"), filename=record["config_filename"]),
                caption=f"{record['config_id']} | до {_fmt_dt(record['expires_at'])}",
            )
        except Exception:
            logging.exception("Failed to send personal config %s", record.get("config_id", "-"))


@router.message(Command(commands=["delete"]), F.func(_is_owner))
async def delete_personal_config_command(message: Message, command: CommandObject | None = None) -> None:
    config_id = (command.args or "").strip() if command else ""
    if not config_id:
        await message.answer("Формат: /delete <config_id>\nПример: /delete PERS-ABC123")
        return

    deleted = delete_personal_config(config_id)
    if deleted is None:
        await message.answer(f"Конфиг {config_id} не найден")
        return

    await message.answer(
        f"Конфиг {config_id} удален.\nФайл: {deleted['config_filename']}\nДо: {_fmt_dt(deleted['expires_at'])}"
    )


@router.message(Command(commands=["ahelp"]), F.func(_is_owner))
async def admin_help(message: Message) -> None:
    await _send_lines_report(message, _build_admin_help_lines())
