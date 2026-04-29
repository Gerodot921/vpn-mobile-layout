from __future__ import annotations

import base64
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from app.json_storage import get_storage_connection
from app.wireguard import add_peer_to_server_by_values, remove_peer_from_server, reserve_client_address

PERSONAL_CONFIGS_TABLE = "personal_configs"
DEFAULT_ALLOWED_IPS = "0.0.0.0/0"
DEFAULT_DNS = "1.1.1.1, 8.8.8.8"
DEFAULT_MTU = 1280


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
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{PERSONAL_CONFIGS_TABLE}_assigned_user_id ON {PERSONAL_CONFIGS_TABLE}(assigned_user_id)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{PERSONAL_CONFIGS_TABLE}_expires_at ON {PERSONAL_CONFIGS_TABLE}(expires_at)"
    )
    connection.commit()
    return connection


def _row_to_record(row: tuple[Any, ...]) -> PersonalConfigRecord:
    return {
        "config_id": str(row[0]),
        "config_filename": str(row[1]),
        "config_text": str(row[2]),
        "address": str(row[3]),
        "public_key": str(row[4]),
        "private_key": str(row[5]),
        "preshared_key": str(row[6]),
        "created_at": str(row[7]),
        "expires_at": str(row[8]),
        "added_to_server": bool(row[9]),
        "revoked_at": str(row[10]) if row[10] else None,
        "assigned_user_id": int(row[11]) if row[11] is not None else None,
        "assigned_username": str(row[12]) if row[12] else None,
        "assigned_at": str(row[13]) if row[13] else None,
        "owner_user_id": int(row[14]) if row[14] is not None else None,
    }


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


def _server_endpoint() -> str:
    host = os.getenv("WIREGUARD_ENDPOINT_HOST", "").strip()
    port = os.getenv("WIREGUARD_ENDPOINT_PORT", "48360").strip()
    if not host:
        return ""
    return f"{host}:{port}"


def _server_public_key() -> str:
    return os.getenv("WIREGUARD_SERVER_PUBLIC_KEY", "").strip()


def _build_config_text(private_key: str, preshared_key: str, address: str) -> str:
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
        f"DNS = {os.getenv('WIREGUARD_DNS', DEFAULT_DNS).strip() or DEFAULT_DNS}",
        f"MTU = {int(os.getenv('WIREGUARD_MTU', str(DEFAULT_MTU)).strip() or DEFAULT_MTU)}",
    ]

    awg_env_map = (
        ("Jc", "WIREGUARD_AWG_JC"),
        ("Jmin", "WIREGUARD_AWG_JMIN"),
        ("Jmax", "WIREGUARD_AWG_JMAX"),
        ("S1", "WIREGUARD_AWG_S1"),
        ("S2", "WIREGUARD_AWG_S2"),
        ("S3", "WIREGUARD_AWG_S3"),
        ("S4", "WIREGUARD_AWG_S4"),
        ("H1", "WIREGUARD_AWG_H1"),
        ("H2", "WIREGUARD_AWG_H2"),
        ("H3", "WIREGUARD_AWG_H3"),
        ("H4", "WIREGUARD_AWG_H4"),
    )
    for param_name, env_key in awg_env_map:
        value = os.getenv(env_key, "").strip()
        if value:
            lines.append(f"{param_name} = {value}")

    lines.extend([
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
    ])
    if preshared_key:
        lines.append(f"PresharedKey = {preshared_key}")

    lines.extend([
        f"AllowedIPs = {os.getenv('WIREGUARD_ALLOWED_IPS', DEFAULT_ALLOWED_IPS).strip() or DEFAULT_ALLOWED_IPS}",
        f"Endpoint = {endpoint}",
        "PersistentKeepalive = 25",
    ])

    return "\n".join(lines)


def revoke_expired_personal_configs() -> list[PersonalConfigRecord]:
    now = _now_utc()
    revoked: list[PersonalConfigRecord] = []

    with _connect() as connection:
        rows = connection.execute(
            f"SELECT config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id FROM {PERSONAL_CONFIGS_TABLE}"
        ).fetchall()

        for row in rows:
            record = _row_to_record(row)
            if record.get("revoked_at"):
                continue
            try:
                if _parse_dt(record["expires_at"]) > now:
                    continue
            except Exception:
                continue

            if record.get("added_to_server") and record.get("public_key"):
                remove_peer_from_server(record["public_key"], user_id=record.get("assigned_user_id") or 0)

            revoked_at = now.isoformat()
            connection.execute(
                f"UPDATE {PERSONAL_CONFIGS_TABLE} SET revoked_at = ?, assigned_user_id = NULL, assigned_username = NULL, assigned_at = NULL WHERE config_id = ?",
                (revoked_at, record["config_id"]),
            )
            record["revoked_at"] = revoked_at
            record["assigned_user_id"] = None
            record["assigned_username"] = None
            record["assigned_at"] = None
            revoked.append(record)

        connection.commit()

    return revoked


def create_personal_configs(count: int, days: int, owner_user_id: int | None = None) -> list[PersonalConfigRecord]:
    count = max(1, min(count, 100))
    days = max(1, min(days, 3650))
    revoke_expired_personal_configs()

    created: list[PersonalConfigRecord] = []
    now = _now_utc()

    with _connect() as connection:
        for _ in range(count):
            private_key = _generate_private_key()
            public_key = _derive_public_key(private_key)
            preshared_key = _generate_preshared_key()
            address = reserve_client_address()

            expires_at = (now + timedelta(days=days)).isoformat()
            config_id = _new_config_id()
            config_filename = f"skull-vpn-{config_id}.conf"
            config_text = _build_config_text(private_key, preshared_key, address)

            added = add_peer_to_server_by_values(
                public_key=public_key,
                client_address=address,
                client_preshared_key=preshared_key,
                user_id=0,
            )
            if not added:
                logging.error("Failed to add personal config peer to server: address=%s, public_key=%s", address, public_key)
                continue

            connection.execute(
                f"""
                INSERT INTO {PERSONAL_CONFIGS_TABLE}
                (config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, NULL, NULL, NULL, ?)
                """,
                (
                    config_id,
                    config_filename,
                    config_text,
                    address,
                    public_key,
                    private_key,
                    preshared_key,
                    now.isoformat(),
                    expires_at,
                    owner_user_id,
                ),
            )

            created.append(
                {
                    "config_id": config_id,
                    "config_filename": config_filename,
                    "config_text": config_text,
                    "address": address,
                    "public_key": public_key,
                    "private_key": private_key,
                    "preshared_key": preshared_key,
                    "created_at": now.isoformat(),
                    "expires_at": expires_at,
                    "added_to_server": True,
                    "revoked_at": None,
                    "assigned_user_id": None,
                    "assigned_username": None,
                    "assigned_at": None,
                    "owner_user_id": owner_user_id,
                }
            )

        connection.commit()

    return created


def list_personal_configs() -> list[PersonalConfigRecord]:
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id FROM {PERSONAL_CONFIGS_TABLE}"
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def list_active_personal_configs() -> list[PersonalConfigRecord]:
    now = _now_utc()
    active: list[PersonalConfigRecord] = []
    for record in list_personal_configs():
        if not record.get("added_to_server"):
            continue
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
    records = [rec for rec in list_active_personal_configs() if rec.get("assigned_user_id") == user_id]
    records.sort(key=lambda item: item.get("expires_at", ""), reverse=True)
    return records


def list_pending_personal_configs_for_user(user_id: int) -> list[PersonalConfigRecord]:
    now = _now_utc()
    pending: list[PersonalConfigRecord] = []
    for record in list_personal_configs():
        if record.get("assigned_user_id") != user_id:
            continue
        if record.get("revoked_at"):
            continue
        if record.get("added_to_server"):
            continue
        try:
            if _parse_dt(record["expires_at"]) <= now:
                continue
        except Exception:
            continue
        pending.append(record)

    pending.sort(key=lambda item: item.get("expires_at", ""), reverse=True)
    return pending


def get_active_personal_config_for_user(user_id: int) -> PersonalConfigRecord | None:
    records = list_active_personal_configs_for_user(user_id)
    if not records:
        return None
    return records[0]


def assign_personal_config_to_user(config_id: str, user_id: int, username: str | None = None) -> PersonalConfigRecord | None:
    config_id = (config_id or "").strip()
    if not config_id:
        return None

    now = _now_utc().isoformat()
    with _connect() as connection:
        row = connection.execute(
            f"SELECT config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id FROM {PERSONAL_CONFIGS_TABLE} WHERE config_id = ?",
            (config_id,),
        ).fetchone()
        if row is None:
            return None

        record = _row_to_record(row)
        if record.get("revoked_at"):
            return None
        if not record.get("added_to_server"):
            return None

        connection.execute(
            f"UPDATE {PERSONAL_CONFIGS_TABLE} SET assigned_user_id = ?, assigned_username = ?, assigned_at = ? WHERE config_id = ?",
            (user_id, (username or "").strip() or None, now, config_id),
        )
        connection.commit()

    record["assigned_user_id"] = user_id
    record["assigned_username"] = (username or "").strip() or None
    record["assigned_at"] = now
    return record


def activate_pending_personal_configs_for_user(user_id: int) -> list[PersonalConfigRecord]:
    activated: list[PersonalConfigRecord] = []
    now = _now_utc().isoformat()

    with _connect() as connection:
        rows = connection.execute(
            f"SELECT config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id FROM {PERSONAL_CONFIGS_TABLE} WHERE assigned_user_id = ?",
            (user_id,),
        ).fetchall()

        for row in rows:
            record = _row_to_record(row)
            if record.get("revoked_at") or record.get("added_to_server"):
                continue

            ok = add_peer_to_server_by_values(
                public_key=record["public_key"],
                client_address=record["address"],
                client_preshared_key=record.get("preshared_key", ""),
                user_id=user_id,
            )
            if not ok:
                logging.error("Failed to activate personal config: config_id=%s", record["config_id"])
                continue

            connection.execute(
                f"UPDATE {PERSONAL_CONFIGS_TABLE} SET added_to_server = 1, assigned_at = COALESCE(assigned_at, ?) WHERE config_id = ?",
                (now, record["config_id"]),
            )
            record["added_to_server"] = True
            if not record.get("assigned_at"):
                record["assigned_at"] = now
            activated.append(record)

        connection.commit()

    return activated


def delete_personal_config(config_id: str) -> PersonalConfigRecord | None:
    config_id = (config_id or "").strip()
    if not config_id:
        return None

    with _connect() as connection:
        row = connection.execute(
            f"SELECT config_id, config_filename, config_text, address, public_key, private_key, preshared_key, created_at, expires_at, added_to_server, revoked_at, assigned_user_id, assigned_username, assigned_at, owner_user_id FROM {PERSONAL_CONFIGS_TABLE} WHERE config_id = ?",
            (config_id,),
        ).fetchone()
        if row is None:
            return None

        record = _row_to_record(row)
        if record.get("public_key"):
            remove_peer_from_server(record["public_key"], user_id=record.get("assigned_user_id") or 0)

        connection.execute(f"DELETE FROM {PERSONAL_CONFIGS_TABLE} WHERE config_id = ?", (config_id,))
        connection.commit()

    return record


def wipe_all_personal_configs(*, remove_server_peers: bool = True) -> dict[str, int]:
    removed_db = 0
    removed_server = 0

    with _connect() as connection:
        rows = connection.execute(f"SELECT public_key FROM {PERSONAL_CONFIGS_TABLE}").fetchall()
        public_keys = [str(row[0] or "") for row in rows if str(row[0] or "")]
        removed_db = len(public_keys)

        connection.execute(f"DELETE FROM {PERSONAL_CONFIGS_TABLE}")
        connection.commit()

    if remove_server_peers:
        for key in public_keys:
            if remove_peer_from_server(key, user_id=0):
                removed_server += 1

    return {"removed_db_configs": removed_db, "removed_server_peers": removed_server}
