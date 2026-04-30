#!/usr/bin/env python3
"""
Small CLI to reconcile WireGuard peers from DB to server.
Usage:
  python scripts/reconcile_peers.py --user 12345 --fix
  python scripts/reconcile_peers.py --all --dry-run
    python scripts/reconcile_peers.py --all --fix --purge-extras
    python scripts/reconcile_peers.py --all-sources --fix --purge-extras
"""
import os
import sys
import argparse
from datetime import datetime, timezone

# Ensure project root is on sys.path so `from app import wireguard` works
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_dotenv(path: str) -> None:
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k.startswith("WIREGUARD_") and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_dotenv(os.path.join(ROOT, ".env"))

from app import wireguard
from app.personal_configs import delete_personal_config, list_active_personal_configs
from app.volume_sync import export_config_text, reload_wireguard_container, write_volume_manifest


def _parse_iso_dt(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _expected_peers_all_sources(*, fix: bool = False) -> tuple[list[dict[str, str | int]], list[dict[str, str]], list[str]]:
    expected: list[dict[str, str | int]] = []
    conflicts: list[dict[str, str]] = []
    revoked_personal: list[str] = []
    address_owner: dict[str, str] = {}

    for profile in wireguard.list_wireguard_profiles():
        address = str(profile.get("address") or "").strip()
        public_key = str(profile.get("public_key") or "").strip()
        if not address or not public_key:
            continue

        address_owner[address] = f"wireguard:{public_key}"
        expected.append(
            {
                "source": "wireguard",
                "user_id": int(profile.get("user_id", 0)),
                "public_key": public_key,
                "address": address,
                "preshared_key": str(profile.get("preshared_key") or "").strip(),
            }
        )

    now = datetime.now(timezone.utc)
    personal_records = sorted(
        list_active_personal_configs(),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )
    for record in personal_records:
        if record.get("revoked_at"):
            continue
        expires_at = _parse_iso_dt(str(record.get("expires_at") or ""))
        if expires_at is not None and expires_at <= now:
            continue

        config_id = str(record.get("config_id") or "").strip()
        address = str(record.get("address") or "").strip()
        public_key = str(record.get("public_key") or "").strip()
        if not address or not public_key:
            continue

        if address in address_owner:
            conflicts.append(
                {
                    "config_id": config_id,
                    "address": address,
                    "public_key": public_key,
                    "owner": address_owner[address],
                }
            )
            if fix and config_id:
                deleted = delete_personal_config(config_id)
                if deleted is not None:
                    revoked_personal.append(config_id)
            continue

        address_owner[address] = f"personal:{public_key}"
        expected.append(
            {
                "source": "personal",
                "user_id": int(record.get("assigned_user_id") or 0),
                "public_key": public_key,
                "address": address,
                "preshared_key": str(record.get("preshared_key") or "").strip(),
                "config_id": config_id,
            }
        )

    dedup: dict[str, dict[str, str | int]] = {}
    for peer in expected:
        public_key = str(peer.get("public_key") or "").strip()
        address = str(peer.get("address") or "").strip()
        if not public_key or not address:
            continue
        dedup[public_key] = peer

    return list(dedup.values()), conflicts, revoked_personal


def _sync_all_sources(*, fix: bool, purge_extras: bool) -> dict:
    expected, conflicts, revoked_personal = _expected_peers_all_sources(fix=fix)
    expected_public_keys = {str(item["public_key"]) for item in expected}

    results: list[dict[str, object]] = []
    if fix:
        for peer in expected:
            ok = wireguard.add_peer_to_server_by_values(
                public_key=str(peer["public_key"]),
                client_address=str(peer["address"]),
                client_preshared_key=str(peer.get("preshared_key") or ""),
                user_id=int(peer.get("user_id") or 0),
            )
            results.append(
                {
                    "ok": ok,
                    "action": "upserted" if ok else "upsert_failed",
                    "source": peer.get("source"),
                    "address": peer.get("address"),
                    "public_key": peer.get("public_key"),
                }
            )

    purged_extras: list[str] = []
    dump = wireguard._get_server_peers_dump()  # noqa: SLF001 - maintenance script
    if dump is None:
        return {
            "ok": False,
            "action": "no_dump",
            "details": "Cannot read server peers",
            "results": results,
            "purged_extras": purged_extras,
        }

    for public_key, _allowed_ips in wireguard._parse_server_peer_dump(dump):  # noqa: SLF001
        if public_key in expected_public_keys:
            continue
        if purge_extras and fix:
            if wireguard.remove_peer_from_server(public_key, user_id=0):
                purged_extras.append(public_key)

    ok = all(bool(item.get("ok", False)) for item in results) if results else True
    return {
        "ok": ok,
        "action": "reconciled_all_sources",
        "details": "Reconciled wireguard + active personal configs",
        "expected": len(expected),
        "conflicts": conflicts,
        "revoked_personal": revoked_personal,
        "results": results,
        "purged_extras": purged_extras,
    }


def _sync_volume(*, reload_container: bool) -> dict:
    exported: list[dict[str, str]] = []

    for profile in wireguard.list_wireguard_profiles():
        filename = str(profile.get("config_filename") or "")
        content = str(profile.get("config_text") or "")
        if not filename:
            continue
        export_config_text("wireguard", filename, content)
        exported.append({"category": "wireguard", "filename": filename})

    for record in list_active_personal_configs():
        if record.get("revoked_at"):
            continue
        filename = str(record.get("config_filename") or "")
        content = str(record.get("config_text") or "")
        if not filename:
            continue
        export_config_text("personal", filename, content)
        exported.append({"category": "personal", "filename": filename})

    manifest_path = write_volume_manifest(exported)
    reload_result = reload_wireguard_container() if reload_container else {"ok": True, "action": "skipped"}

    return {
        "ok": bool(reload_result.get("ok", True)),
        "action": "synced_volume",
        "exported": len(exported),
        "manifest": str(manifest_path),
        "reload": reload_result,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", type=int, help="User ID to reconcile")
    p.add_argument("--all", action="store_true", help="Reconcile all DB profiles")
    p.add_argument("--all-sources", action="store_true", help="Reconcile WireGuard profiles + active personal configs")
    p.add_argument("--sync", action="store_true", help="Deprecated: startup sync is disabled")
    p.add_argument("--fix", action="store_true", help="Apply fixes (remove/add) rather than dry-run")
    p.add_argument("--purge-extras", action="store_true", help="Remove server peers that do not exist in the DB before reconciling")
    p.add_argument("--sync-volume", action="store_true", help="Export configs to the configured volume after reconcile")
    p.add_argument("--reload-container", action="store_true", help="Run WIREGUARD_VOLUME_RELOAD_COMMAND after volume sync")
    args = p.parse_args()

    if args.sync:
        print("Sync mode is disabled")
        return

    if not args.user and not args.all and not args.all_sources:
        p.error("--user, --all, --all-sources, or --sync required")

    if args.user:
        res = wireguard.reconcile_user_peer(args.user, fix=args.fix)
        print(res)
        return

    if args.all_sources:
        res = _sync_all_sources(fix=args.fix, purge_extras=args.purge_extras)
        if args.sync_volume:
            volume_res = _sync_volume(reload_container=args.reload_container)
            res = {"reconcile": res, "volume": volume_res, "ok": bool(res.get("ok", False)) and bool(volume_res.get("ok", False))}
        print(res)
        return

    res = wireguard.reconcile_all_peers(fix=args.fix, purge_extras=args.purge_extras)
    if args.sync_volume:
        volume_res = _sync_volume(reload_container=args.reload_container)
        res = {"reconcile": res, "volume": volume_res, "ok": bool(res.get("ok", False)) and bool(volume_res.get("ok", False))}
    print(res)


if __name__ == "__main__":
    main()
