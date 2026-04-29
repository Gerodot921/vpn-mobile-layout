from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import subprocess
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from app.json_storage import get_storage_connection

WIREGUARD_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "wireguard_profiles.json"
WIREGUARD_STATE_TABLE = "wireguard_state"
WIREGUARD_PROFILES_TABLE = "wireguard_profiles"

DEFAULT_ALLOWED_IPS = "0.0.0.0/0"
DEFAULT_DNS = "1.1.1.1, 8.8.8.8"
DEFAULT_ENDPOINT_PORT = 48360
DEFAULT_CLIENT_NETWORK_PREFIX = "10.66.66"
DEFAULT_CLIENT_START_OCTET = 2
DEFAULT_MTU = 1280

_state_lock = Lock()
_seed_checked = False


class WireGuardProfile(TypedDict):
    profile_id: str
    user_id: int
    private_key: str
    public_key: str
    preshared_key: str
    address: str
    endpoint: str
    dns: str
    allowed_ips: str
    mtu: int
    configured: bool
    created_at: str
    updated_at: str
    config_text: str
    config_filename: str


class WireGuardState(TypedDict):
    next_client_octet: int
    profiles: dict[str, WireGuardProfile]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _connect() -> sqlite3.Connection:
    connection = get_storage_connection()
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WIREGUARD_STATE_TABLE} (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            next_client_octet INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WIREGUARD_PROFILES_TABLE} (
            user_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            private_key TEXT NOT NULL,
            public_key TEXT NOT NULL,
            preshared_key TEXT NOT NULL,
            address TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            dns TEXT NOT NULL,
            allowed_ips TEXT NOT NULL,
            mtu INTEGER NOT NULL,
            configured INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            config_text TEXT NOT NULL,
            config_filename TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{WIREGUARD_PROFILES_TABLE}_public_key ON {WIREGUARD_PROFILES_TABLE}(public_key)"
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{WIREGUARD_PROFILES_TABLE}_address ON {WIREGUARD_PROFILES_TABLE}(address)"
    )
    return connection


def _profile_row_to_record(row: tuple[Any, ...]) -> WireGuardProfile | None:
    try:
        user_id = int(row[0])
        mtu = int(row[9])
    except Exception:
        return None

    return {
        "user_id": user_id,
        "profile_id": str(row[1]),
        "private_key": str(row[2]),
        "public_key": str(row[3]),
        "preshared_key": str(row[4]),
        "address": str(row[5]),
        "endpoint": str(row[6]),
        "dns": str(row[7]),
        "allowed_ips": str(row[8]),
        "mtu": mtu,
        "configured": bool(row[10]),
        "created_at": str(row[11]),
        "updated_at": str(row[12]),
        "config_text": str(row[13]),
        "config_filename": str(row[14]),
    }


def _fetch_profile(connection: sqlite3.Connection, user_id: int) -> WireGuardProfile | None:
    row = connection.execute(
        f"SELECT user_id, profile_id, private_key, public_key, preshared_key, address, endpoint, dns, allowed_ips, mtu, configured, created_at, updated_at, config_text, config_filename FROM {WIREGUARD_PROFILES_TABLE} WHERE user_id = ?",
        (str(user_id),),
    ).fetchone()
    if row is None:
        return None

    profile = _profile_row_to_record(row)
    if profile is not None:
        return profile

    # Cleanup malformed row to avoid repeated crashes and allow regeneration.
    connection.execute(
        f"DELETE FROM {WIREGUARD_PROFILES_TABLE} WHERE user_id = ?",
        (str(user_id),),
    )
    connection.commit()
    return None


def _state_to_json(state: WireGuardState) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True)


def _state_from_json(raw_data: Any) -> WireGuardState:
    state = _state_default()
    if not isinstance(raw_data, dict):
        return state

    next_client_octet = raw_data.get("next_client_octet", DEFAULT_CLIENT_START_OCTET)
    if isinstance(next_client_octet, int) and next_client_octet >= DEFAULT_CLIENT_START_OCTET:
        state["next_client_octet"] = next_client_octet

    raw_profiles = raw_data.get("profiles", {})
    if isinstance(raw_profiles, dict):
        for key, value in raw_profiles.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue

            profile_id = value.get("profile_id")
            user_id = value.get("user_id")
            private_key = value.get("private_key")
            public_key = value.get("public_key")
            preshared_key = value.get("preshared_key")
            address = value.get("address")
            endpoint = value.get("endpoint")
            dns = value.get("dns")
            allowed_ips = value.get("allowed_ips")
            mtu = value.get("mtu", DEFAULT_MTU)
            configured = value.get("configured", False)
            created_at = value.get("created_at")
            updated_at = value.get("updated_at")
            config_text = value.get("config_text")
            config_filename = value.get("config_filename")

            if not isinstance(profile_id, str) or not isinstance(user_id, int):
                continue
            if not isinstance(private_key, str) or not isinstance(public_key, str):
                continue
            if not isinstance(preshared_key, str) or not isinstance(address, str):
                continue
            if not isinstance(endpoint, str) or not isinstance(dns, str) or not isinstance(allowed_ips, str):
                continue
            if not isinstance(mtu, int):
                mtu = DEFAULT_MTU
            if not isinstance(created_at, str) or not isinstance(updated_at, str):
                continue
            if not isinstance(config_text, str) or not isinstance(config_filename, str):
                continue

            state["profiles"][key] = {
                "profile_id": profile_id,
                "user_id": user_id,
                "private_key": private_key,
                "public_key": public_key,
                "preshared_key": preshared_key,
                "address": address,
                "endpoint": endpoint,
                "dns": dns,
                "allowed_ips": allowed_ips,
                "mtu": mtu,
                "configured": bool(configured),
                "created_at": created_at,
                "updated_at": updated_at,
                "config_text": config_text,
                "config_filename": config_filename,
            }

    return state


def _ensure_seeded() -> None:
    global _seed_checked
    if _seed_checked:
        return

    with _connect() as connection:
        state_exists = connection.execute(f"SELECT COUNT(*) FROM {WIREGUARD_STATE_TABLE}").fetchone()
        profiles_exist = connection.execute(f"SELECT COUNT(*) FROM {WIREGUARD_PROFILES_TABLE}").fetchone()
        if state_exists and int(state_exists[0]) > 0 and profiles_exist and int(profiles_exist[0]) > 0:
            _seed_checked = True
            return
        connection.execute(
            f"INSERT OR REPLACE INTO {WIREGUARD_STATE_TABLE} (id, next_client_octet) VALUES (1, ?)",
            (DEFAULT_CLIENT_START_OCTET,),
        )

        connection.commit()
    _seed_checked = True


def _state_default() -> WireGuardState:
    return {
        "next_client_octet": DEFAULT_CLIENT_START_OCTET,
        "profiles": {},
    }


def _load_state() -> WireGuardState:
    _ensure_seeded()
    state = _state_default()

    with _connect() as connection:
        state_row = connection.execute(
            f"SELECT next_client_octet FROM {WIREGUARD_STATE_TABLE} WHERE id = 1"
        ).fetchone()
        if state_row is not None and isinstance(state_row[0], int) and state_row[0] >= DEFAULT_CLIENT_START_OCTET:
            state["next_client_octet"] = state_row[0]

        rows = connection.execute(
            f"SELECT user_id, profile_id, private_key, public_key, preshared_key, address, endpoint, dns, allowed_ips, mtu, configured, created_at, updated_at, config_text, config_filename FROM {WIREGUARD_PROFILES_TABLE}"
        ).fetchall()

    for row in rows:
        profile = _profile_row_to_record(row)
        if profile is None:
            continue
        state["profiles"][str(profile["user_id"])] = profile

    return state


def _save_state(state: WireGuardState) -> None:
    with _connect() as connection:
        connection.execute(
            f"INSERT OR REPLACE INTO {WIREGUARD_STATE_TABLE} (id, next_client_octet) VALUES (1, ?)",
            (int(state.get("next_client_octet", DEFAULT_CLIENT_START_OCTET)),),
        )
        connection.execute(f"DELETE FROM {WIREGUARD_PROFILES_TABLE}")
        for user_key, profile in state.get("profiles", {}).items():
            if not isinstance(profile, dict):
                continue
            connection.execute(
                f"""
                INSERT OR REPLACE INTO {WIREGUARD_PROFILES_TABLE}
                (user_id, profile_id, private_key, public_key, preshared_key, address, endpoint, dns, allowed_ips, mtu, configured, created_at, updated_at, config_text, config_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_key,
                    str(profile.get("profile_id") or ""),
                    str(profile.get("private_key") or ""),
                    str(profile.get("public_key") or ""),
                    str(profile.get("preshared_key") or ""),
                    str(profile.get("address") or ""),
                    str(profile.get("endpoint") or ""),
                    str(profile.get("dns") or ""),
                    str(profile.get("allowed_ips") or ""),
                    int(profile.get("mtu", DEFAULT_MTU)) if isinstance(profile.get("mtu", DEFAULT_MTU), int) else DEFAULT_MTU,
                    1 if bool(profile.get("configured", False)) else 0,
                    str(profile.get("created_at") or _now_utc().isoformat()),
                    str(profile.get("updated_at") or _now_utc().isoformat()),
                    str(profile.get("config_text") or ""),
                    str(profile.get("config_filename") or _build_profile_filename(str(profile.get("profile_id") or "WG"))),
                ),
            )
        connection.commit()


def _user_key(user_id: int) -> str:
    return str(user_id)


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


def _configured_dns() -> str:
    dns = os.getenv("WIREGUARD_DNS", DEFAULT_DNS).strip()
    return dns if dns else DEFAULT_DNS


def _configured_allowed_ips() -> str:
    allowed_ips = os.getenv("WIREGUARD_ALLOWED_IPS", DEFAULT_ALLOWED_IPS).strip()
    return allowed_ips if allowed_ips else DEFAULT_ALLOWED_IPS


def _configured_mtu() -> int:
    mtu_raw = os.getenv("WIREGUARD_MTU", str(DEFAULT_MTU)).strip()
    try:
        mtu = int(mtu_raw)
    except Exception:
        mtu = DEFAULT_MTU
    return mtu if mtu > 0 else DEFAULT_MTU


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


def _configured_client_prefix() -> str:
    prefix = os.getenv("WIREGUARD_CLIENT_NETWORK_PREFIX", DEFAULT_CLIENT_NETWORK_PREFIX).strip()
    if not prefix:
        return DEFAULT_CLIENT_NETWORK_PREFIX
    return prefix.rstrip(".")


def _configured_start_octet() -> int:
    start_raw = os.getenv("WIREGUARD_CLIENT_START_OCTET", str(DEFAULT_CLIENT_START_OCTET)).strip()
    try:
        start = int(start_raw)
    except Exception:
        start = DEFAULT_CLIENT_START_OCTET
    return start if 2 <= start <= 254 else DEFAULT_CLIENT_START_OCTET


def is_wireguard_configured() -> bool:
    return bool(_server_endpoint() and _server_public_key())


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
    global_psk = os.getenv("WIREGUARD_GLOBAL_PRESHARED_KEY", "").strip()
    if global_psk:
        return global_psk
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def _build_address(client_octet: int) -> str:
    return f"{_configured_client_prefix()}.{client_octet}/32"


def _extract_client_octet(address: str) -> int | None:
    try:
        host = address.split("/", 1)[0]
        octet = int(host.rsplit(".", 1)[1])
    except Exception:
        return None

    return octet if 1 <= octet <= 254 else None


def _used_octets(state: WireGuardState, prefix: str) -> set[int]:
    used: set[int] = set()
    for profile in state.get("profiles", {}).values():
        if not isinstance(profile, dict):
            continue
        address = profile.get("address")
        if not isinstance(address, str):
            continue
        if not address.startswith(f"{prefix}."):
            continue
        octet = _extract_client_octet(address)
        if octet is not None:
            used.add(octet)
    return used


def _next_client_octet(state: WireGuardState) -> int:
    start_octet = _configured_start_octet()
    prefix = _configured_client_prefix()
    used_octets = _used_octets(state, prefix)

    next_octet = state.get("next_client_octet", DEFAULT_CLIENT_START_OCTET)
    if not isinstance(next_octet, int) or next_octet < start_octet:
        next_octet = start_octet
    if next_octet > 254:
        next_octet = start_octet

    candidate = next_octet
    for _ in range(start_octet, 255):
        if candidate not in used_octets:
            state["next_client_octet"] = candidate + 1
            return candidate
        candidate += 1
        if candidate > 254:
            candidate = start_octet

    # Fallback if range is exhausted.
    state["next_client_octet"] = start_octet
    return start_octet


def _profile_id() -> str:
    return f"WG-{secrets.token_urlsafe(6).upper()}"


def _build_config_text(profile: WireGuardProfile) -> str:
    endpoint = profile["endpoint"]
    server_public_key = _server_public_key()
    if not endpoint or not server_public_key:
        return (
            "# WireGuard / AmneziaWG profile is not configured yet\n"
            "# Set WIREGUARD_ENDPOINT_HOST, WIREGUARD_ENDPOINT_PORT and\n"
            "# WIREGUARD_SERVER_PUBLIC_KEY in .env, then restart the bot.\n"
            f"# Profile ID: {profile['profile_id']}\n"
            f"# Address: {profile['address']}\n"
        )

    lines = [
        "# Compatible with Amnezia and WireGuard",
        "[Interface]",
        f"PrivateKey = {profile['private_key']}",
        f"Address = {profile['address']}",
        f"DNS = {profile['dns']}",
        f"MTU = {profile['mtu']}",
    ]

    for param_name, param_value in _configured_awg_params():
        lines.append(f"{param_name} = {param_value}")

    lines.extend(
        [
            "",
            "[Peer]",
            f"PublicKey = {server_public_key}",
        ]
    )

    if profile["preshared_key"]:
        lines.append(f"PresharedKey = {profile['preshared_key']}")

    lines.extend(
        [
            f"AllowedIPs = {profile['allowed_ips']}",
            f"Endpoint = {endpoint}",
            "PersistentKeepalive = 25",
        ]
    )

    return "\n".join(lines)


def _build_profile_filename(profile_id: str) -> str:
    safe_profile_id = profile_id.replace("/", "-").replace("\\", "-")
    return f"skull-vpn-{safe_profile_id}.conf"


def _build_profile(user_id: int, state: WireGuardState) -> WireGuardProfile:
    private_key = _generate_private_key()
    public_key = _derive_public_key(private_key)
    # Use global preshared-key if configured, otherwise generate random
    global_psk = os.getenv("WIREGUARD_GLOBAL_PRESHARED_KEY", "").strip()
    preshared_key = global_psk if global_psk else _generate_preshared_key()
    address = _build_address(_next_client_octet(state))
    profile_id = _profile_id()
    created_at = _now_utc().isoformat()

    profile: WireGuardProfile = {
        "profile_id": profile_id,
        "user_id": user_id,
        "private_key": private_key,
        "public_key": public_key,
        "preshared_key": preshared_key,
        "address": address,
        "endpoint": _server_endpoint(),
        "dns": _configured_dns(),
        "allowed_ips": _configured_allowed_ips(),
        "mtu": _configured_mtu(),
        "configured": is_wireguard_configured(),
        "created_at": created_at,
        "updated_at": created_at,
        "config_text": "",
        "config_filename": _build_profile_filename(profile_id),
    }
    profile["config_text"] = _build_config_text(profile)
    return profile


def ensure_wireguard_profile(user_id: int) -> WireGuardProfile:
    """Ensure profile exists in DB. If new, create and add peer to server immediately."""
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        profile = state["profiles"].get(user_key)
        is_new = profile is None
        
        if is_new:
            # Create new profile
            profile = _build_profile(user_id, state)
            
            # Add peer to server ATOMICALLY
            peer_added = add_peer_to_server_by_values(
                public_key=profile["public_key"],
                client_address=profile["address"],
                client_preshared_key=profile.get("preshared_key", ""),
                user_id=user_id,
            )
            if not peer_added:
                logging.error("Failed to add peer to server for new profile user_id=%s", user_id)
                return profile

            state["profiles"][user_key] = profile
            _save_state(state)
            return profile

        # Update existing profile (migrate old octets, refresh endpoint/params)
        current_octet = _extract_client_octet(profile.get("address", ""))
        start_octet = _configured_start_octet()
        if current_octet is None or current_octet < start_octet:
            profile["address"] = _build_address(_next_client_octet(state))

        profile["endpoint"] = _server_endpoint()
        profile["dns"] = _configured_dns()
        profile["allowed_ips"] = _configured_allowed_ips()
        profile["mtu"] = _configured_mtu()
        
        # Always use global preshared-key if configured, otherwise keep existing
        global_psk = os.getenv("WIREGUARD_GLOBAL_PRESHARED_KEY", "").strip()
        if global_psk:
            profile["preshared_key"] = global_psk
        elif not profile.get("preshared_key"):
            profile["preshared_key"] = _generate_preshared_key()
        
        profile["configured"] = is_wireguard_configured()
        profile["updated_at"] = _now_utc().isoformat()
        profile["config_text"] = _build_config_text(profile)
        state["profiles"][user_key] = profile
        _save_state(state)
        return profile


def issue_wireguard_profile(user_id: int) -> WireGuardProfile | None:
    """Create a fresh WireGuard profile for an existing user and replace the old one.

    This is the safe path for config issuance: it always rotates keys and filename,
    then adds the new peer first and persists it only after the server accepts it.
    """
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        old_profile = state["profiles"].get(user_key)
        old_public_key = str(old_profile.get("public_key") or "") if isinstance(old_profile, dict) else ""

        new_profile = _build_profile(user_id, state)
        added = add_peer_to_server_by_values(
            public_key=new_profile["public_key"],
            client_address=new_profile["address"],
            client_preshared_key=new_profile.get("preshared_key", ""),
            user_id=user_id,
        )
        if not added:
            logging.error("Failed to issue fresh WireGuard profile for user_id=%s", user_id)
            return None

        state["profiles"][user_key] = new_profile
        _save_state(state)

    if old_public_key and old_public_key != new_profile["public_key"]:
        remove_peer_from_server(old_public_key, user_id)

    return new_profile


def get_wireguard_profile(user_id: int) -> WireGuardProfile | None:
    with _state_lock:
        _ensure_seeded()
        with _connect() as connection:
            return _fetch_profile(connection, user_id)


def get_wireguard_config_text(user_id: int) -> str | None:
    profile = get_wireguard_profile(user_id)
    if profile is None:
        return None
    return profile["config_text"]


def get_wireguard_config_filename(user_id: int) -> str:
    profile = get_wireguard_profile(user_id)
    if profile is None:
        return "skull-vpn-wireguard.conf"
    return profile["config_filename"]


def get_wireguard_config_payload(user_id: int) -> tuple[str, bytes] | None:
    profile = get_wireguard_profile(user_id)
    if profile is None:
        return None

    config_text = profile.get("config_text", "")
    if not config_text:
        return None

    filename = profile.get("config_filename") or "skull-vpn-wireguard.conf"
    return filename, config_text.encode("utf-8")


def _docker_executable() -> str | None:
    configured = os.getenv("WIREGUARD_DOCKER_BIN", "").strip()
    if configured:
        if Path(configured).exists():
            return configured
        logging.error("Configured WIREGUARD_DOCKER_BIN not found: %s", configured)

    for candidate in ("docker", "/usr/bin/docker", "/usr/local/bin/docker", "/bin/docker"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    return None


def _docker_container_and_iface() -> tuple[str | None, str | None, str | None]:
    docker_container = os.getenv("WIREGUARD_DOCKER_CONTAINER", "").strip() or None
    interface_name = os.getenv("WIREGUARD_INTERFACE_NAME", "wg0").strip() or None
    docker_bin = _docker_executable()
    return docker_bin, docker_container, interface_name


def _run_docker_cmd(cmd: list[str], *, user_id: int, action: str) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
        if result.returncode == 0:
            return True
        logging.error("Failed to %s for user_id=%s: %s", action, user_id, result.stderr)
        return False
    except FileNotFoundError:
        logging.error("Docker command not found")
        return False
    except subprocess.TimeoutExpired:
        logging.error("Docker exec timeout while trying to %s for user_id=%s", action, user_id)
        return False
    except Exception as exc:
        logging.error("Docker exec error while trying to %s for user_id=%s: %s", action, user_id, exc)
        return False


def add_peer_to_server(user_id: int) -> bool:
    """Add a WireGuard peer to the server via docker exec when profile is granted."""
    profile = get_wireguard_profile(user_id)
    if profile is None:
        logging.warning("No WireGuard profile found for user_id=%s", user_id)
        return False

    return add_peer_to_server_by_values(
        public_key=profile["public_key"],
        client_address=profile["address"],
        client_preshared_key=profile.get("preshared_key", ""),
        user_id=user_id,
    )


def add_peer_to_server_by_values(
    public_key: str,
    client_address: str,
    client_preshared_key: str,
    user_id: int = 0,
) -> bool:
    """Add a WireGuard peer to server using explicit peer values."""
    if not public_key or not client_address:
        return False

    docker_bin, docker_container, interface_name = _docker_container_and_iface()

    if not docker_container:
        logging.warning("WireGuard Docker container is not configured for user_id=%s", user_id)
        return False

    if not docker_bin:
        logging.error("Docker executable was not found. Set WIREGUARD_DOCKER_BIN=/usr/bin/docker")
        return False

    client_public_key = public_key

    if client_preshared_key:
        cmd = [
            docker_bin,
            "exec",
            "-e",
            f"WG_PUBLIC_KEY={client_public_key}",
            "-e",
            f"WG_PRESHARED_KEY={client_preshared_key}",
            "-e",
            f"WG_ALLOWED_IPS={client_address}",
            docker_container,
            "sh",
            "-lc",
            (
                "tmp=$(mktemp); "
                "printf '%s' \"$WG_PRESHARED_KEY\" > \"$tmp\"; "
                f"wg set {interface_name} peer \"$WG_PUBLIC_KEY\" preshared-key \"$tmp\" allowed-ips \"$WG_ALLOWED_IPS\"; "
                "status=$?; rm -f \"$tmp\"; exit $status"
            ),
        ]
    else:
        cmd = [
            docker_bin,
            "exec",
            docker_container,
            "wg",
            "set",
            interface_name,
            "peer",
            client_public_key,
            "allowed-ips",
            client_address,
        ]

    ok = _run_docker_cmd(cmd, user_id=user_id, action="add peer")
    if ok:
        logging.info("Added peer for user_id=%s to %s in %s", user_id, interface_name, docker_container)
    return ok


def remove_peer_from_server(public_key: str, user_id: int) -> bool:
    if not public_key:
        return False

    docker_bin, docker_container, interface_name = _docker_container_and_iface()
    if not docker_container:
        return False
    if not docker_bin:
        return False

    cmd = [
        docker_bin,
        "exec",
        docker_container,
        "wg",
        "set",
        interface_name,
        "peer",
        public_key,
        "remove",
    ]

    ok = _run_docker_cmd(cmd, user_id=user_id, action="remove peer")
    if ok:
        logging.info("Removed peer for user_id=%s from %s in %s", user_id, interface_name, docker_container)
    return ok


def reset_wireguard_profile(user_id: int) -> WireGuardProfile:
    """Delete old profile (and remove peer from server), then create new one."""
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        old_profile = state["profiles"].get(user_key)
        
        if old_profile is not None:
            # Remove old peer from server FIRST
            old_pub = old_profile.get("public_key", "")
            if old_pub:
                remove_peer_from_server(old_pub, user_id)
        
        # Create new profile
        profile = _build_profile(user_id, state)
        state["profiles"][user_key] = profile
        _save_state(state)
        
        # Add new peer to server ATOMICALLY
        peer_added = add_peer_to_server_by_values(
            public_key=profile["public_key"],
            client_address=profile["address"],
            client_preshared_key=profile.get("preshared_key", ""),
            user_id=user_id,
        )
        if not peer_added:
            logging.error("Failed to add peer to server for reset profile user_id=%s", user_id)
        
        return profile


def delete_wireguard_profile(user_id: int) -> WireGuardProfile | None:
    """Remove profile from DB and remove peer from server atomically."""
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        profile = state["profiles"].pop(user_key, None)
        if profile is None:
            return None
        _save_state(state)

    # Remove peer from server AFTER DB update
    old_public_key = profile.get("public_key", "")
    if old_public_key:
        remove_peer_from_server(old_public_key, user_id)

    return profile


def list_peer_endpoints() -> dict[str, str]:
    """Return current peer endpoint mapping {public_key: endpoint} from WireGuard."""
    docker_bin, docker_container, interface_name = _docker_container_and_iface()
    if not docker_container or not docker_bin or not interface_name:
        return {}

    cmd = [
        docker_bin,
        "exec",
        docker_container,
        "wg",
        "show",
        interface_name,
        "endpoints",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
    except Exception:
        logging.exception("Failed to read WireGuard peer endpoints")
        return {}

    if result.returncode != 0:
        logging.error("Failed to get peer endpoints: %s", result.stderr)
        return {}

    endpoints: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        public_key = parts[0].strip()
        endpoint = parts[1].strip()
        if public_key:
            endpoints[public_key] = endpoint

    return endpoints


def _run_docker_cmd_output(cmd: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception as exc:
        logging.error("Docker exec error: %s", exc)
        return 1, "", str(exc)


def _get_server_peers_dump() -> str | None:
    """Return raw output of `wg show <iface> dump` from the docker container, or None on error."""
    docker_bin, docker_container, interface_name = _docker_container_and_iface()
    if not docker_bin or not docker_container or not interface_name:
        logging.warning("Docker or interface not configured for getting peers dump")
        return None

    cmd = [docker_bin, "exec", docker_container, "wg", "show", interface_name, "dump"]
    rc, out, err = _run_docker_cmd_output(cmd)
    if rc != 0:
        logging.error("Failed to get peers dump: %s", err.strip())
        return None
    return out


def reconcile_user_peer(user_id: int, *, fix: bool = False) -> dict:
    """Ensure server has a peer matching DB profile for `user_id`.

    Returns a dict with keys: ok(bool), action(str), details(str).
    If `fix` is True, will remove mismatching peer and add correct one.
    """
    profile = get_wireguard_profile(user_id)
    if profile is None:
        return {"ok": False, "action": "no_profile", "details": f"No DB profile for user {user_id}"}

    expected_pub = profile.get("public_key") or _derive_public_key(profile["private_key"])
    address = profile.get("address")
    dump = _get_server_peers_dump()
    if dump is None:
        return {"ok": False, "action": "no_dump", "details": "Cannot read server peers"}

    # parse dump lines: public_key preshared_key endpoint allowedips latest_handshake rx tx
    found_line = None
    found_pub = None
    for line in dump.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        pub = parts[0].strip()
        allowed = parts[3].strip()
        if allowed == address:
            found_line = line
            found_pub = pub
            break

    if found_line is None:
        # peer with address not present
        if fix:
            ok = add_peer_to_server_by_values(public_key=expected_pub, client_address=address, client_preshared_key=profile.get("preshared_key", ""), user_id=user_id)
            return {"ok": ok, "action": "added", "details": f"Added peer {expected_pub} for {address}" if ok else "add_failed"}
        return {"ok": False, "action": "missing", "details": f"Peer for {address} not found on server"}

    # found peer with same address
    if found_pub == expected_pub:
        return {"ok": True, "action": "ok", "details": "Peer present and matches DB"}

    # mismatch: server has different public key for this address
    if fix:
        docker_bin, docker_container, interface_name = _docker_container_and_iface()
        if not docker_bin or not docker_container:
            return {"ok": False, "action": "no_docker", "details": "Docker not configured"}

        # remove wrong pub
        cmd_rm = [docker_bin, "exec", docker_container, "wg", "set", interface_name, "peer", found_pub, "remove"]
        rc_rm, _, err_rm = _run_docker_cmd_output(cmd_rm)
        if rc_rm != 0:
            return {"ok": False, "action": "remove_failed", "details": err_rm}

        # add correct
        ok_add = add_peer_to_server_by_values(public_key=expected_pub, client_address=address, client_preshared_key=profile.get("preshared_key", ""), user_id=user_id)
        return {"ok": ok_add, "action": "replaced", "details": "replaced_peer" if ok_add else "add_failed"}

    return {"ok": False, "action": "mismatch", "details": f"Server pub {found_pub} != expected {expected_pub}"}


def sync_all_peers_on_startup() -> dict:
    """Reconcile ALL DB profiles with server peers. Call once at bot startup.
    
    Returns dict with keys: ok(bool), synced(int), fixed(int), removed(int), errors(list).
    """
    state = _load_state()
    synced, fixed, removed = 0, 0, 0
    errors = []
    
    # Fix all DB profiles to match server
    for user_key, profile in state.get("profiles", {}).items():
        try:
            uid = int(user_key)
            res = reconcile_user_peer(uid, fix=True)
            if res["ok"]:
                if res["action"] == "ok":
                    synced += 1
                elif res["action"] in ("added", "replaced"):
                    fixed += 1
            else:
                errors.append(f"user {uid}: {res['action']}")
        except Exception as e:
            errors.append(f"user {user_key}: {str(e)}")
    
    # Find and remove orphaned peers on server (those not in DB)
    dump = _get_server_peers_dump()
    if dump:
        db_addresses = set()
        for profile in state.get("profiles", {}).values():
            addr = profile.get("address")
            if addr:
                db_addresses.add(addr)
        
        for line in dump.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            pub_key = parts[0].strip()
            address = parts[3].strip()
            if address not in db_addresses and address != "(none)":
                # Remove orphaned peer
                if remove_peer_from_server(pub_key, user_id=0):
                    removed += 1
                else:
                    errors.append(f"failed to remove orphaned peer {address} ({pub_key})")
    
    return {"ok": len(errors) == 0, "synced": synced, "fixed": fixed, "removed": removed, "errors": errors}
