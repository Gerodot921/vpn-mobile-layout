from __future__ import annotations

import base64
import logging
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TypedDict

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from app.json_storage import load_json_file, save_json_file

WIREGUARD_STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "wireguard_profiles.json"

DEFAULT_ALLOWED_IPS = "0.0.0.0/0, ::/0"
DEFAULT_DNS = "1.1.1.1, 8.8.8.8"
DEFAULT_ENDPOINT_PORT = 51820
DEFAULT_CLIENT_NETWORK_PREFIX = "10.66.66"
DEFAULT_CLIENT_START_OCTET = 2
DEFAULT_MTU = 1280

_state_lock = Lock()


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


def _state_default() -> WireGuardState:
    return {
        "next_client_octet": DEFAULT_CLIENT_START_OCTET,
        "profiles": {},
    }


def _load_state() -> WireGuardState:
    raw_data = load_json_file(WIREGUARD_STORAGE_PATH, _state_default())
    if not isinstance(raw_data, dict):
        return _state_default()

    state = _state_default()
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


def _save_state(state: WireGuardState) -> None:
    save_json_file(WIREGUARD_STORAGE_PATH, state)


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
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def _build_address(client_octet: int) -> str:
    return f"{_configured_client_prefix()}.{client_octet}/32"


def _next_client_octet(state: WireGuardState) -> int:
    next_octet = state.get("next_client_octet", DEFAULT_CLIENT_START_OCTET)
    if not isinstance(next_octet, int) or next_octet < DEFAULT_CLIENT_START_OCTET:
        next_octet = _configured_start_octet()
    if next_octet > 254:
        next_octet = _configured_start_octet()
    state["next_client_octet"] = next_octet + 1
    return next_octet


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
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
    ]

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
    address = _build_address(_next_client_octet(state))
    profile_id = _profile_id()
    created_at = _now_utc().isoformat()

    profile: WireGuardProfile = {
        "profile_id": profile_id,
        "user_id": user_id,
        "private_key": private_key,
        "public_key": public_key,
        "preshared_key": "",
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
    user_key = _user_key(user_id)
    with _state_lock:
        state = _load_state()
        profile = state["profiles"].get(user_key)
        if profile is None:
            profile = _build_profile(user_id, state)
            state["profiles"][user_key] = profile
            _save_state(state)
            return profile

        profile["endpoint"] = _server_endpoint()
        profile["dns"] = _configured_dns()
        profile["allowed_ips"] = _configured_allowed_ips()
        profile["mtu"] = _configured_mtu()
        profile["preshared_key"] = ""
        profile["configured"] = is_wireguard_configured()
        profile["updated_at"] = _now_utc().isoformat()
        profile["config_text"] = _build_config_text(profile)
        state["profiles"][user_key] = profile
        _save_state(state)
        return profile


def get_wireguard_profile(user_id: int) -> WireGuardProfile | None:
    with _state_lock:
        state = _load_state()
        return state["profiles"].get(_user_key(user_id))


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


def add_peer_to_server(user_id: int) -> bool:
    """Add a WireGuard peer to the server via docker exec when profile is granted."""
    profile = get_wireguard_profile(user_id)
    if profile is None:
        logging.warning("No WireGuard profile found for user_id=%s", user_id)
        return False

    docker_container = os.getenv("WIREGUARD_DOCKER_CONTAINER", "").strip()
    interface_name = os.getenv("WIREGUARD_INTERFACE_NAME", "wg0").strip()

    if not docker_container:
        logging.warning("WireGuard Docker container is not configured for user_id=%s", user_id)
        return False

    client_public_key = profile["public_key"]
    client_address = profile["address"]

    cmd = [
        "docker",
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

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
        if result.returncode == 0:
            logging.info("Added peer for user_id=%s to %s in %s", user_id, interface_name, docker_container)
            return True

        logging.error("Failed to add peer for user_id=%s: %s", user_id, result.stderr)
        return False
    except FileNotFoundError:
        logging.error("Docker command not found")
        return False
    except subprocess.TimeoutExpired:
        logging.error("Docker exec timeout for user_id=%s", user_id)
        return False
    except Exception as exc:
        logging.error("Docker exec error for user_id=%s: %s", user_id, exc)
        return False
