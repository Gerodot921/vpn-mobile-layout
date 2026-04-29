from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from app.json_storage import get_storage_connection, load_json_file
from app.wireguard import add_peer_to_server_by_values, list_wireguard_profiles, remove_peer_from_server

PERSONAL_CONFIGS_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "personal_configs.json"
WIREGUARD_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "wireguard_profiles.json"
PERSONAL_CONFIGS_TABLE = "personal_configs"

DEFAULT_ENDPOINT_PORT = 51820
DEFAULT_CLIENT_NETWORK_PREFIX = "10.66.66"
DEFAULT_CLIENT_START_OCTET = 2
DEFAULT_ALLOWED_IPS = "0.0.0.0/0"
DEFAULT_DNS = "1.1.1.1, 8.8.8.8"
DEFAULT_MTU = 1280

_state_lock = Lock()
_seed_checked = False


class PersonalConfigRecord(TypedDict):
    config_id: str
    config_filename: str
    config_text: str
    address: str
    public_key: str
    private_key: str
    preshared_key: str
    created_at: str
    expires_at: str
    added_to_server: bool
    revoked_at: str | None
    assigned_user_id: int | None
    assigned_username: str | None
    assigned_at: str | None
    owner_user_id: int | None


PersonalConfigsState = dict[str, PersonalConfigRecord]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _connect() -> sqlite3.Connection:
    connection = get_storage_connection()
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {PERSONAL_CONFIGS_TABLE} (
            config_id TEXT PRIMARY KEY,
            config_filename TEXT NOT NULL,
            config_text TEXT NOT NULL,
            address TEXT NOT NULL,
            public_key TEXT NOT NULL,
            private_key TEXT NOT NULL,
            preshared_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            added_to_server INTEGER NOT NULL,
            revoked_at TEXT,
            assigned_user_id INTEGER,
            assigned_username TEXT,
            assigned_at TEXT,
            owner_user_id INTEGER
        )
        """
    )
    existing_columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({PERSONAL_CONFIGS_TABLE})").fetchall()
    }
    if "owner_user_id" not in existing_columns:
        connection.execute(f"ALTER TABLE {PERSONAL_CONFIGS_TABLE} ADD COLUMN owner_user_id INTEGER")
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{PERSONAL_CONFIGS_TABLE}_assigned_user_id ON {PERSONAL_CONFIGS_TABLE}(assigned_user_id)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{PERSONAL_CONFIGS_TABLE}_expires_at ON {PERSONAL_CONFIGS_TABLE}(expires_at)"
    )
    return connection


def _row_to_record(row: tuple[Any, ...]) -> tuple[str, PersonalConfigRecord]:
    config_id = str(row[0])
    return config_id, {
        "config_id": config_id,
        "config_filename": str(row[1]),
        "config_text": str(row[2]),
        "address": str(row[3]),
        "public_key": str(row[4]),
        "private_key": str(row[5]),
        "preshared_key": str(row[6]),
        "created_at": str(row[7]),
        "expires_at": str(row[8]),
        "added_to_server": bool(row[9]),
        "revoked_at": str(row[10]) if row[10] is not None else None,
        "assigned_user_id": int(row[11]) if row[11] is not None else None,
        "assigned_username": str(row[12]) if isinstance(row[12], str) and row[12] else None,
        "assigned_at": str(row[13]) if row[13] is not None else None,
        "owner_user_id": int(row[14]) if len(row) > 14 and row[14] is not None else None,
    }


def _encode_state_value(record: PersonalConfigRecord) -> tuple[Any, ...]:
    return (
        record.get("config_filename") or "",
        record.get("config_text") or "",
        record.get("address") or "",
        record.get("public_key") or "",
        record.get("private_key") or "",
        record.get("preshared_key") or "",
        record.get("created_at") or _now_utc().isoformat(),
        record.get("expires_at") or _now_utc().isoformat(),
        1 if bool(record.get("added_to_server", False)) else 0,
        record.get("revoked_at"),
        record.get("assigned_user_id"),
        record.get("assigned_username"),
        record.get("assigned_at"),
        record.get("owner_user_id"),
    )


def _ensure_seeded() -> None:
    global _seed_checked
    if _seed_checked:
        return

    with _connect() as connection:
        existing = connection.execute(f"SELECT COUNT(*) FROM {PERSONAL_CONFIGS_TABLE}").fetchone()
        if existing and int(existing[0]) > 0:
            _seed_checked = True
            return

        raw_data = load_json_file(PERSONAL_CONFIGS_STORAGE_PATH, {})
        if not isinstance(raw_data, dict) or not raw_data:
            return

        for key, value in raw_data.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue

            config_id = value.get("config_id")
            config_filename = value.get("config_filename")
            config_text = value.get("config_text")
            address = value.get("address")
            public_key = value.get("public_key")
            private_key = value.get("private_key")
            preshared_key = value.get("preshared_key")
            created_at = value.get("created_at")
            expires_at = value.get("expires_at")

            if not all(isinstance(item, str) for item in [config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at]):
                continue

            connection.execute(
                f"""
                INSERT OR REPLACE INTO {PERSONAL_CONFIGS_TABLE}
                (config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config_id,
                    config_filename,
                    config_text,
                    address,
                    public_key,
                    private_key,
                    preshared_key,
                    created_at,
                    expires_at,
                    1 if bool(value.get("added_to_server", False)) else 0,
                    value.get("revoked_at") if isinstance(value.get("revoked_at"), str) else None,
                    value.get("assigned_user_id") if isinstance(value.get("assigned_user_id"), int) else None,
                    value.get("assigned_username") if isinstance(value.get("assigned_username"), str) and value.get("assigned_username") else None,
                    value.get("assigned_at") if isinstance(value.get("assigned_at"), str) and value.get("assigned_at") else None,
                    value.get("owner_user_id") if isinstance(value.get("owner_user_id"), int) else None,
                ),
            )

        connection.commit()
    _seed_checked = True


def _load_state() -> PersonalConfigsState:
    _ensure_seeded()
    state: PersonalConfigsState = {}
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id FROM {PERSONAL_CONFIGS_TABLE}"
        ).fetchall()

    for row in rows:
        config_id, record = _row_to_record(row)
        state[config_id] = record

    return state


def _save_state(state: PersonalConfigsState) -> None:
    with _connect() as connection:
        connection.execute(f"DELETE FROM {PERSONAL_CONFIGS_TABLE}")
        for config_id, record in state.items():
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {PERSONAL_CONFIGS_TABLE}
                (config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (config_id, *_encode_state_value(record)),
            )
        connection.commit()


def _configured_client_prefix() -> str:
    prefix = os.getenv("WIREGUARD_CLIENT_NETWORK_PREFIX", DEFAULT_CLIENT_NETWORK_PREFIX).strip()
    return prefix.rstrip(".") if prefix else DEFAULT_CLIENT_NETWORK_PREFIX


def _configured_start_octet() -> int:
    raw = os.getenv("WIREGUARD_CLIENT_START_OCTET", str(DEFAULT_CLIENT_START_OCTET)).strip()
    try:
        value = int(raw)
    except Exception:
        value = DEFAULT_CLIENT_START_OCTET
    return value if 2 <= value <= 254 else DEFAULT_CLIENT_START_OCTET


def _configured_dns() -> str:
    dns = os.getenv("WIREGUARD_DNS", DEFAULT_DNS).strip()
    return dns if dns else DEFAULT_DNS


def _configured_allowed_ips() -> str:
    allowed_ips = os.getenv("WIREGUARD_ALLOWED_IPS", DEFAULT_ALLOWED_IPS).strip()
    return allowed_ips if allowed_ips else DEFAULT_ALLOWED_IPS


def _configured_mtu() -> int:
    raw = os.getenv("WIREGUARD_MTU", str(DEFAULT_MTU)).strip()
    try:
        value = int(raw)
    except Exception:
        value = DEFAULT_MTU
    return value if value > 0 else DEFAULT_MTU


def _server_endpoint() -> str:
    endpoint_host = os.getenv("WIREGUARD_ENDPOINT_HOST", "").strip()
    endpoint_port_raw = os.getenv("WIREGUARD_ENDPOINT_PORT", str(DEFAULT_ENDPOINT_PORT)).strip()
    if not endpoint_host:
        return ""

    try:
        endpoint_port = int(endpoint_port_raw)
    except Exception:
        endpoint_port = DEFAULT_ENDPOINT_PORT

    return f"{endpoint_host}:{endpoint_port}"


def _server_public_key() -> str:
    return os.getenv("WIREGUARD_SERVER_PUBLIC_KEY", "").strip()


def _configured_awg_params() -> list[tuple[str, str]]:
    values = [
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
    return [(name, value) for name, value in values if value]


def _extract_client_octet(address: str) -> int | None:
    try:
        host = address.split("/", 1)[0]
        octet = int(host.rsplit(".", 1)[1])
    except Exception:
        return None
    return octet if 1 <= octet <= 254 else None


def _collect_used_octets(prefix: str) -> set[int]:
    used: set[int] = set()

    state = _load_state()
    for record in state.values():
        revoked_at = record.get("revoked_at")
        if isinstance(revoked_at, str) and revoked_at:
            continue
        address = record.get("address", "")
        if not isinstance(address, str) or not address.startswith(f"{prefix}."):
            continue
        octet = _extract_client_octet(address)
        if octet is not None:
            used.add(octet)

    for profile in list_wireguard_profiles():
        address = profile.get("address", "")
        if not isinstance(address, str) or not address.startswith(f"{prefix}."):
            continue
        octet = _extract_client_octet(address)
        if octet is not None:
            used.add(octet)

    return used


def _allocate_address(used: set[int] | None = None) -> str:
    prefix = _configured_client_prefix()
    start_octet = _configured_start_octet()
    used_octets = set(used) if isinstance(used, set) else _collect_used_octets(prefix)

    candidate = start_octet
    for _ in range(start_octet, 255):
        if candidate not in used_octets:
            used_octets.add(candidate)
            if isinstance(used, set):
                used.add(candidate)
            return f"{prefix}.{candidate}/32"
        candidate += 1
        if candidate > 254:
            candidate = start_octet

    # Last-resort fallback; still returns valid address format.
    return f"{prefix}.{start_octet}/32"


def _generate_private_key() -> str:
    private_key = x25519.X25519PrivateKey.generate()
    raw_private_key = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    return base64.b64encode(raw_private_key).decode("ascii")


def _derive_public_key(private_key_b64: str) -> str:
    private_key_bytes = base64.b64decode(private_key_b64.encode("ascii"))
    private_key = x25519.X25519PrivateKey.from_private_bytes(private_key_bytes)
    public_key_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(public_key_bytes).decode("ascii")


def _generate_preshared_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def _new_config_id() -> str:
    return f"PERS-{secrets.token_urlsafe(6).upper()}"


def _build_config_text(
    private_key: str,
    preshared_key: str,
    address: str,
) -> str:
    endpoint = _server_endpoint()
    server_public_key = _server_public_key()

    if not endpoint or not server_public_key:
        return (
            "# WireGuard / AmneziaWG profile is not configured yet\n"
            "# Set WIREGUARD_ENDPOINT_HOST, WIREGUARD_ENDPOINT_PORT and\n"
            "# WIREGUARD_SERVER_PUBLIC_KEY in .env, then restart the bot.\n"
        )

    lines = [
        "# Personal WireGuard / AmneziaWG profile",
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {address}",
        f"DNS = {_configured_dns()}",
        f"MTU = {_configured_mtu()}",
    ]

    for param_name, param_value in _configured_awg_params():
        lines.append(f"{param_name} = {param_value}")

    lines.extend(
        [
            "",
            "[Peer]",
            f"PublicKey = {server_public_key}",
            f"PresharedKey = {preshared_key}",
            f"AllowedIPs = {_configured_allowed_ips()}",
            f"Endpoint = {endpoint}",
            "PersistentKeepalive = 25",
        ]
    )

    return "\n".join(lines)


def revoke_expired_personal_configs() -> int:
    now = _now_utc()
    revoked = 0
    with _state_lock:
        state = _load_state()
        changed = False
        for key, record in state.items():
            try:
                if _parse_dt(record["expires_at"]) > now:
                    continue
            except Exception:
                continue

            if record.get("revoked_at"):
                continue

            if record.get("added_to_server"):
                if remove_peer_from_server(record.get("public_key", ""), user_id=0):
                    revoked += 1
            record["revoked_at"] = now.isoformat()
            state[key] = record
            changed = True

        if changed:
            _save_state(state)

    return revoked


def delete_personal_config(config_id: str) -> PersonalConfigRecord | None:
    config_id = config_id.strip()
    if not config_id:
        return None

    with _state_lock:
        state = _load_state()
        record = state.get(config_id)
        if record is None:
            return None

        if record.get("added_to_server"):
            remove_peer_from_server(record.get("public_key", ""), user_id=0)

        record["revoked_at"] = _now_utc().isoformat()
        record["added_to_server"] = False
        state[config_id] = record
        _save_state(state)
        return record


def assign_personal_config_to_user(config_id: str, user_id: int, username: str | None = None) -> bool:
    config_id = config_id.strip()
    if not config_id:
        return False

    with _state_lock:
        state = _load_state()
        record = state.get(config_id)
        if record is None:
            return False

        record["assigned_user_id"] = user_id
        record["assigned_username"] = username.strip().lstrip("@") if isinstance(username, str) and username.strip() else None
        record["assigned_at"] = _now_utc().isoformat()
        state[config_id] = record
        _save_state(state)

    return True


def list_pending_personal_configs_for_user(user_id: int) -> list[PersonalConfigRecord]:
    now = _now_utc()
    pending: list[PersonalConfigRecord] = []
    for record in list_personal_configs():
        if record.get("owner_user_id") != user_id:
            continue
        if record.get("assigned_user_id") is not None:
            continue
        if record.get("revoked_at"):
            continue
        try:
            if _parse_dt(record["expires_at"]) <= now:
                continue
        except Exception:
            continue
        pending.append(record)

    pending.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return pending


def activate_pending_personal_configs_for_user(user_id: int, username: str | None = None) -> list[PersonalConfigRecord]:
    activated: list[PersonalConfigRecord] = []
    for record in list_pending_personal_configs_for_user(user_id):
        if assign_personal_config_to_user(record["config_id"], user_id, username):
            activated.append(record)
    return activated


def get_active_personal_config_for_user(user_id: int) -> PersonalConfigRecord | None:
    now = _now_utc()
    with _state_lock:
        state = _load_state()

    candidates: list[PersonalConfigRecord] = []
    for record in state.values():
        if record.get("assigned_user_id") != user_id:
            continue
        if record.get("revoked_at"):
            continue
        try:
            if _parse_dt(record["expires_at"]) <= now:
                continue
        except Exception:
            continue
        candidates.append(record)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item.get("expires_at", ""), reverse=True)
    return candidates[0]


def create_personal_configs(count: int, days: int, owner_user_id: int | None = None) -> list[PersonalConfigRecord]:
    count = max(1, min(count, 100))
    days = max(1, min(days, 3650))
    revoke_expired_personal_configs()

    created: list[PersonalConfigRecord] = []
    with _state_lock:
        state = _load_state()
        used_octets = _collect_used_octets(_configured_client_prefix())

        for _ in range(count):
            private_key = _generate_private_key()
            public_key = _derive_public_key(private_key)
            preshared_key = _generate_preshared_key()
            address = _allocate_address(used_octets)

            now = _now_utc()
            expires_at = (now + timedelta(days=days)).isoformat()
            config_id = _new_config_id()
            config_filename = f"skull-vpn-{config_id}.conf"
            config_text = _build_config_text(private_key, preshared_key, address)

            added_to_server = add_peer_to_server_by_values(
                public_key=public_key,
                client_address=address,
                client_preshared_key=preshared_key,
                user_id=0,
            )

            record: PersonalConfigRecord = {
                "config_id": config_id,
                "config_filename": config_filename,
                "config_text": config_text,
                "address": address,
                "public_key": public_key,
                "private_key": private_key,
                "preshared_key": preshared_key,
                "created_at": now.isoformat(),
                "expires_at": expires_at,
                "added_to_server": bool(added_to_server),
                "revoked_at": None,
                "assigned_user_id": None,
                "assigned_username": None,
                "assigned_at": None,
                "owner_user_id": owner_user_id,
            }
            state[config_id] = record
            created.append(record)

        _save_state(state)

    return created


def list_personal_configs() -> list[PersonalConfigRecord]:
    with _state_lock:
        state = _load_state()
        return list(state.values())


def list_active_personal_configs() -> list[PersonalConfigRecord]:
    now = _now_utc()
    active: list[PersonalConfigRecord] = []
    for record in list_personal_configs():
        if record.get("revoked_at"):
            continue
        try:
            if _parse_dt(record["expires_at"]) <= now:
                continue
        except Exception:
            continue
        active.append(record)
    return active


def list_active_personal_configs_for_user(user_id: int) -> list[PersonalConfigRecord]:
    active: list[PersonalConfigRecord] = []
    for record in list_active_personal_configs():
        if record.get("assigned_user_id") != user_id:
            continue
        active.append(record)
    active.sort(key=lambda item: item.get("expires_at", ""), reverse=True)
    return active


def wipe_all_personal_configs(*, remove_server_peers: bool = False) -> dict:
    """Delete all personal configs from SQLite and optionally remove their peers from the server."""
    with _state_lock:
        state = _load_state()
        records = list(state.values())
        removed_server_peers = 0

        if remove_server_peers:
            for record in records:
                public_key = str(record.get("public_key") or "").strip()
                if public_key and remove_peer_from_server(public_key, user_id=0):
                    removed_server_peers += 1

        _save_state({})

    return {
        "ok": True,
        "removed_server_peers": removed_server_peers,
        "deleted_configs": len(records),
    }
