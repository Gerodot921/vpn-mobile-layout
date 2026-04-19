import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.ads import get_ad_stats, set_active_ad, set_ad_active
from app.crypto_payments import get_order_by_id, list_recent_orders
from app.json_storage import get_storage_diagnostics
from app.keyboards.inline import mini_app_only_keyboard
from app.keyboards.inline import subscription_inline_keyboard
from app.free_access import delete_free_access, get_total_free_claims, get_total_free_users, list_active_free_access_records
from app.personal_configs import assign_personal_config_to_user, create_personal_configs, delete_personal_config, list_active_personal_configs, list_personal_configs, revoke_expired_personal_configs
from app.referrals import get_known_username, get_user_id_by_username, list_known_user_ids, list_registered_users, upsert_username
from app.subscriptions import delete_subscription, ensure_subscription, get_remaining_text, get_subscription_plan_name
from app.subscriptions import list_active_subscriptions
from app.texts import (
    FREE_ACCESS_PANEL_TEXT,
    MINI_APP_ENTRY_TEXT,
    MINI_APP_NOT_CONFIGURED_TEXT,
    SUBSCRIPTION_REMINDER_TEXT_TEMPLATE,
)
from app.wireguard import add_peer_to_server, delete_wireguard_profile, ensure_wireguard_profile, get_wireguard_config_filename, get_wireguard_config_text, get_wireguard_profile, list_peer_endpoints, reset_wireguard_profile

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


def _format_registered_username(username: str | None) -> str:
    if not isinstance(username, str) or not username.strip():
        return "@unknown"
    clean = username.strip().lstrip("@")
    return f"@{clean}" if clean else "@unknown"


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
    lines.append(f"Всего персональных (активных): {len(active)}")
    lines.append(f"Авто-отозвано по сроку сейчас: {revoked}")
    lines.append("")

    if not active:
        lines.append("Нет созданных персональных конфигов")
        return lines

    for record in sorted(active, key=lambda item: item.get("expires_at", "")):
        status = "active"
        expires_at_raw = record.get("expires_at", "")
        try:
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
        "/allusers — username подключённых пользователей",
        "/sms <username> <text|config_id> — отправить сообщение или конфиг",
        "/smsall <text> — отправить текст всем пользователям",
        "/allstatb — статистика бесплатных VPN",
        "/allstatp — статистика платных VPN",
        "/allstatpers — статистика персональных конфигов",
        "/allstat — общая статистика по всем типам",
        "/create <n> <m> — создать n персональных конфигов на m дней",
        "/delete <config_id> — удалить персональный конфиг по ID",
        "/deletetarif <username> <free|blatnoy|paid> — удалить тариф и его конфиг",
        "/adset <asset_url> [seconds] [click_url] — установить рекламу",
        "/adon — включить рекламу",
        "/adoff — выключить рекламу",
        "/adstats — статистика рекламы",
        "/paystat [n] [status] — последние платежи, статус: paid|pending",
        "/payorder <order_id> — подробности конкретного платежа",
        "/diag — диагностика БД и хранилищ",
        "/profile_reset — сбросить личный VPN-профиль",
        "/clear_chat — очистить чат",
    ]


async def _resolve_user_id_by_username(message: Message, username: str) -> int | None:
    normalized = username.strip().lstrip("@")
    if not normalized:
        return None

    user_id = get_user_id_by_username(normalized)
    if user_id is not None:
        return user_id

    try:
        chat = await message.bot.get_chat(f"@{normalized}")
        resolved_id = getattr(chat, "id", None)
        if isinstance(resolved_id, int):
            chat_username = getattr(chat, "username", None)
            if isinstance(chat_username, str) and chat_username:
                upsert_username(resolved_id, chat_username)
            return resolved_id
    except Exception:
        return None

    return None


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


@router.message(Command(commands=["deletetarif"]), F.func(_is_owner))
async def delete_tarif_command(message: Message, command: CommandObject | None = None) -> None:
    args = (command.args or "").split() if command else []
    if len(args) != 2:
        await message.answer(
            "Формат: /deletetarif <username> <free|blatnoy|paid>\n"
            "Пример: /deletetarif testuser paid"
        )
        return

    username_arg = args[0].strip().lstrip("@")
    tier_arg = args[1].strip().lower()
    if not username_arg:
        await message.answer("Укажите username пользователя")
        return

    if tier_arg not in {"free", "blatnoy", "paid"}:
        await message.answer("Тариф должен быть одним из: free, blatnoy, paid")
        return

    target_user_id = await _resolve_user_id_by_username(message, username_arg)
    if target_user_id is None:
        await message.answer(f"Пользователь @{username_arg} не найден в базе")
        return

    removed_lines: list[str] = []
    if tier_arg == "free":
        free_record = delete_free_access(target_user_id)
        if free_record is None:
            await message.answer(f"У @{username_arg} нет активного free тарифа")
            return

        profile = delete_wireguard_profile(target_user_id)
        removed_lines.append(f"Удалён free тариф до {_fmt_dt(free_record.get('expires_at', '-'))}")
        removed_lines.append(f"Удалён конфиг: {free_record.get('vpn_config_name', '-')}")
        if profile is not None:
            removed_lines.append(f"Удалён WireGuard профиль: {profile.get('config_filename', '-')}")

    elif tier_arg == "blatnoy":
        active_configs = list_active_personal_configs()
        target_config = None
        for record in active_configs:
            if record.get("assigned_user_id") == target_user_id:
                target_config = record
                break

        if target_config is None:
            await message.answer(f"У @{username_arg} нет активного blatnoy тарифа")
            return

        deleted = delete_personal_config(target_config["config_id"])
        if deleted is None:
            await message.answer(f"Не удалось удалить blatnoy тариф для @{username_arg}")
            return

        removed_lines.append(f"Удалён blatnoy тариф: {deleted.get('config_id', '-')}")
        removed_lines.append(f"Конфиг: {deleted.get('config_filename', '-')}")

    elif tier_arg == "paid":
        paid_record = delete_subscription(target_user_id)
        if paid_record is None:
            await message.answer(f"У @{username_arg} нет активного paid тарифа")
            return

        profile = delete_wireguard_profile(target_user_id)
        removed_lines.append(f"Удалён paid тариф до {_fmt_dt(paid_record.get('expires_at', '-'))}")
        removed_lines.append(f"План: {paid_record.get('plan_name', 'Базовый')}")
        if profile is not None:
            removed_lines.append(f"Удалён WireGuard профиль: {profile.get('config_filename', '-')}")

    await message.answer("\n".join([f"Тариф @{username_arg} ({tier_arg}) удалён."] + removed_lines))


@router.message(Command(commands=["ahelp"]), F.func(_is_owner))
async def admin_help(message: Message) -> None:
    await _send_lines_report(message, _build_admin_help_lines())


@router.message(Command(commands=["allusers"]), F.func(_is_owner))
async def all_users(message: Message) -> None:
    registered_users = list_registered_users()

    if not registered_users:
        await message.answer("Пользователей, нажимавших START, пока нет")
        return

    rows: list[str] = ["👥 Пользователи бота", ""]
    for user_id, record in registered_users:
        username = record.get("username")
        started_at = record.get("started_at") or record.get("activated_at") or "-"
        label = _format_registered_username(username)
        rows.append(f"{label} | id={user_id} | start={_fmt_dt(started_at)}")

    await _send_lines_report(message, rows)


@router.message(Command(commands=["sms"]), F.func(_is_owner))
async def sms_command(message: Message, command: CommandObject | None = None) -> None:
    args_raw = (command.args or "").strip() if command else ""
    if not args_raw:
        await message.answer("Формат: /sms <username> <сообщение_или_config_id>\nПример: /sms A1KKK6 привет")
        return

    parts = args_raw.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Нужно указать username и текст/ID конфига")
        return

    username_arg, payload = parts[0], parts[1].strip()
    if not payload:
        await message.answer("Пустое сообщение")
        return

    target_user_id = await _resolve_user_id_by_username(message, username_arg)
    if target_user_id is None:
        await message.answer(f"Пользователь {username_arg} не найден")
        return

    all_personal = list_personal_configs()
    config_record = next((item for item in all_personal if item.get("config_id") == payload), None)

    try:
        if config_record is not None:
            await message.bot.send_document(
                target_user_id,
                BufferedInputFile(config_record["config_text"].encode("utf-8"), filename=config_record["config_filename"]),
                caption=f"Персональный конфиг {config_record['config_id']} | до {_fmt_dt(config_record['expires_at'])}",
            )
            assign_personal_config_to_user(config_record["config_id"], target_user_id, username_arg)
            await message.answer(f"Конфиг {config_record['config_id']} отправлен @{username_arg.lstrip('@')}")
        else:
            await message.bot.send_message(target_user_id, payload)
            await message.answer(f"Сообщение отправлено @{username_arg.lstrip('@')}")
    except Exception:
        logging.exception("Failed to send sms command payload to user_id=%s", target_user_id)
        await message.answer("Не удалось отправить сообщение/конфиг")


@router.message(Command(commands=["smsall"]), F.func(_is_owner))
async def sms_all_command(message: Message, command: CommandObject | None = None) -> None:
    text = (command.args or "").strip() if command else ""
    if not text:
        await message.answer("Формат: /smsall <текст_сообщения>")
        return

    user_ids = [user_id for user_id in list_known_user_ids() if user_id != OWNER_ID]
    if not user_ids:
        await message.answer("Нет пользователей для рассылки")
        return

    sent = 0
    failed = 0

    for user_id in user_ids:
        try:
            await message.bot.send_message(user_id, text)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.1)
            try:
                await message.bot.send_message(user_id, text)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

    await message.answer(
        f"Рассылка завершена. Отправлено: {sent}. Ошибок: {failed}. Всего адресатов: {len(user_ids)}"
    )


@router.message(Command(commands=["adset"]), F.func(_is_owner))
async def ad_set_command(message: Message, command: CommandObject | None = None) -> None:
    args = (command.args or "").split() if command else []
    if len(args) < 1:
        await message.answer(
            "Формат: /adset <asset_url> [seconds] [click_url]\n"
            "Пример: /adset https://cdn.example/ad.gif 30 https://example.com"
        )
        return

    asset_url = args[0].strip()
    duration_sec: int | None = None
    click_url: str | None = None

    if len(args) >= 2:
        second = args[1].strip()
        if second.isdigit():
            duration_sec = int(second)
            if len(args) >= 3:
                click_url = args[2].strip()
        else:
            click_url = second

    try:
        ad = set_active_ad(
            asset_url=asset_url,
            click_url=click_url,
            duration_sec=duration_sec,
        )
    except Exception:
        await message.answer("Не удалось обновить рекламу. Проверьте аргументы команды.")
        return

    await message.answer(
        "Реклама обновлена:\n"
        f"asset: {ad.get('asset_url')}\n"
        f"click: {ad.get('click_url')}\n"
        f"seconds: {ad.get('duration_sec')}\n"
        f"active: {ad.get('active')}"
    )


@router.message(Command(commands=["adon"]), F.func(_is_owner))
async def ad_on_command(message: Message) -> None:
    ad = set_ad_active(True)
    await message.answer(f"Реклама включена. Текущий asset: {ad.get('asset_url')}")


@router.message(Command(commands=["adoff"]), F.func(_is_owner))
async def ad_off_command(message: Message) -> None:
    ad = set_ad_active(False)
    await message.answer(f"Реклама выключена. Текущий asset: {ad.get('asset_url')}")


@router.message(Command(commands=["adstats"]), F.func(_is_owner))
async def ad_stats_command(message: Message) -> None:
    stats = get_ad_stats()
    impressions = int(stats.get("impressions", 0) or 0)
    completions = int(stats.get("completions", 0) or 0)
    conversion = (completions / impressions * 100.0) if impressions > 0 else 0.0
    ad = stats.get("active_ad") or {}

    lines = [
        "📣 Статистика рекламы",
        "",
        f"Показы (sessions): {impressions}",
        f"Досмотры: {completions}",
        f"Конверсия: {conversion:.1f}%",
        "",
        f"Активна: {bool(ad.get('active'))}",
        f"asset: {ad.get('asset_url', '-')}",
        f"click: {ad.get('click_url', '-')}",
        f"seconds: {ad.get('duration_sec', '-')}",
    ]
    await _send_lines_report(message, lines)


@router.message(Command(commands=["diag", "dbdiag", "healthdiag"]), F.func(_is_owner))
async def diagnostics_command(message: Message) -> None:
    payload = get_storage_diagnostics()
    db_exists = bool(payload.get("db_exists"))
    db_path = str(payload.get("db_path") or "-")
    db_size_bytes = int(payload.get("db_size_bytes") or 0)
    db_size_kb = db_size_bytes / 1024 if db_size_bytes > 0 else 0.0
    kv_rows = int(payload.get("kv_store_rows") or 0)
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []

    lines: list[str] = [
        "🧪 Диагностика хранилища",
        "",
        f"DB exists: {db_exists}",
        f"DB path: {db_path}",
        f"DB size: {db_size_kb:.1f} KB",
        f"kv_store rows: {kv_rows}",
        "",
        "Таблицы:",
    ]

    if not tables:
        lines.append("(пусто)")
    else:
        for table in tables:
            name = str(table.get("name") or "-")
            rows = int(table.get("rows") or 0)
            lines.append(f"- {name}: {rows}")

    await _send_lines_report(message, lines)


@router.message(Command(commands=["paystat", "paystats"]), F.func(_is_owner))
async def payment_stats_command(message: Message, command: CommandObject | None = None) -> None:
    args = (command.args or "").split() if command and command.args else []
    limit = 20
    status_filter: str | None = None

    if args:
        if args[0].isdigit():
            limit = int(args[0])
            if len(args) >= 2:
                status_filter = args[1].strip().lower()
        else:
            status_filter = args[0].strip().lower()

    if status_filter not in {None, "paid", "pending"}:
        await message.answer("Формат: /paystat [кол-во] [paid|pending]\nПример: /paystat 30 paid")
        return

    orders = list_recent_orders(limit, status=status_filter)
    if not orders:
        await message.answer("Платежей пока нет")
        return

    lines: list[str] = ["💳 Последние платежи", ""]
    for record in orders:
        status = str(record.get("status") or "-")
        order_id = str(record.get("order_id") or "-")
        provider = str(record.get("provider") or "-")
        user_id = int(record.get("user_id") or 0)
        plan_name = str(record.get("plan_name") or "-")
        amount = float(record.get("amount_rub") or 0)
        created_at = _fmt_dt(str(record.get("created_at") or "-"))
        paid_at_raw = record.get("paid_at")
        paid_at = _fmt_dt(str(paid_at_raw)) if isinstance(paid_at_raw, str) and paid_at_raw else "-"
        invoice_id = str(record.get("provider_invoice_id") or "-")

        lines.append(
            f"{order_id} | {status} | {provider} | {plan_name} | {amount:.2f} RUB | uid={user_id}"
        )
        lines.append(f"created={created_at} | paid={paid_at} | invoice={invoice_id}")
        lines.append("")

    await _send_lines_report(message, lines)


@router.message(Command(commands=["payorder"]), F.func(_is_owner))
async def payment_order_command(message: Message, command: CommandObject | None = None) -> None:
    order_id = (command.args or "").strip() if command else ""
    if not order_id:
        await message.answer("Формат: /payorder <order_id>")
        return

    record = get_order_by_id(order_id)
    if record is None:
        await message.answer("Платеж не найден")
        return

    lines = [
        "🧾 Платеж",
        "",
        f"order_id: {record.get('order_id', '-')}",
        f"status: {record.get('status', '-')}",
        f"provider: {record.get('provider', '-')}",
        f"user_id: {record.get('user_id', '-')}",
        f"plan: {record.get('plan_name', '-')} ({record.get('plan_code', '-')})",
        f"amount_rub: {float(record.get('amount_rub') or 0):.2f}",
        f"days: {record.get('days', '-')}",
        f"provider_invoice_id: {record.get('provider_invoice_id', '-')}",
        f"invoice_url: {record.get('invoice_url', '-')}",
        f"created_at: {_fmt_dt(str(record.get('created_at') or '-'))}",
        f"paid_at: {_fmt_dt(str(record.get('paid_at') or '-')) if record.get('paid_at') else '-'}",
    ]
    await _send_lines_report(message, lines)
