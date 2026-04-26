from __future__ import annotations

import os
from typing import Any, Mapping

from app.wireguard import get_wireguard_profile


def _parse_endpoint(endpoint: str) -> tuple[str, str]:
    if not endpoint:
        return "", ""

    value = endpoint.strip()
    if value.startswith("[") and "]:" in value:
        host, port = value[1:].split("]:", 1)
        return host.strip(), port.strip()

    if ":" in value:
        host, port = value.rsplit(":", 1)
        return host.strip(), port.strip()

    return value, ""


def _awg_param_lines() -> list[str]:
    raw_params = [
        ("Jc", os.getenv("WIREGUARD_AWG_JC", "").strip()),
        ("Jmin", os.getenv("WIREGUARD_AWG_JMIN", "").strip()),
        ("Jmax", os.getenv("WIREGUARD_AWG_JMAX", "").strip()),
        ("S1", os.getenv("WIREGUARD_AWG_S1", "").strip()),
        ("S2", os.getenv("WIREGUARD_AWG_S2", "").strip()),
        ("S3", os.getenv("WIREGUARD_AWG_S3", "").strip()),
        ("S4", os.getenv("WIREGUARD_AWG_S4", "").strip()),
        ("H1", os.getenv("WIREGUARD_AWG_H1", "").strip()),
        ("H2", os.getenv("WIREGUARD_AWG_H2", "").strip()),
        ("H3", os.getenv("WIREGUARD_AWG_H3", "").strip()),
        ("H4", os.getenv("WIREGUARD_AWG_H4", "").strip()),
    ]
    lines: list[str] = []
    for key, value in raw_params:
        if value:
            lines.append(f"{key}: {value}")
    return lines


def build_native_access_text(profile: Mapping[str, Any], *, title: str = "Данные подключения AmneziaWG") -> str:
    endpoint = str(profile.get("endpoint") or "")
    host, port = _parse_endpoint(endpoint)
    server_public_key = os.getenv("WIREGUARD_SERVER_PUBLIC_KEY", "").strip()

    lines = [
        f"🔐 {title}",
        "",
        "Тип подключения: AmneziaWG",
        f"Сервер: {host or '-'}",
        f"Порт: {port or '-'}",
        f"Публичный ключ сервера: {server_public_key or '-'}",
        f"Публичный ключ клиента: {str(profile.get('public_key') or '-')}",
        f"Приватный ключ клиента: {str(profile.get('private_key') or '-')}",
        f"Preshared key: {str(profile.get('preshared_key') or '-')}",
        f"Адрес клиента: {str(profile.get('address') or '-')}",
        f"DNS: {str(profile.get('dns') or '-')}",
        f"Allowed IPs: {str(profile.get('allowed_ips') or '-')}",
        f"MTU: {str(profile.get('mtu') or '-')}",
    ]

    awg_lines = _awg_param_lines()
    if awg_lines:
        lines.append("")
        lines.append("Параметры AmneziaWG:")
        lines.extend(awg_lines)

    lines.append("")
    lines.append("Добавьте подключение в AmneziaVPN вручную как AmneziaWG и вставьте эти значения.")
    return "\n".join(lines)


def build_native_access_text_for_user(user_id: int, *, title: str = "Данные подключения AmneziaWG") -> str | None:
    profile = get_wireguard_profile(user_id)
    if profile is None:
        return None
    return build_native_access_text(profile, title=title)
